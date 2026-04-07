"""
DynamicPlugins 统一核心逻辑

所有 CLI 共享的: 项目扫描、插件发现、启禁管理、缓存构建、关键词注入。
运行时通过 cli_config 按需加载单个 CLI 配置，不加载其他 CLI。

用法 (通过命令行):
    python3 -m lib.core manage --cli claude /path/to/project [--dry]
    python3 -m lib.core cache  --cli claude
    python3 -m lib.core inject --cli claude   # stdin: hook JSON, stdout: inject JSON
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from .logger import get_logger
from .skill_parser import parse_frontmatter, extract_keywords, get_body_without_frontmatter

log = get_logger("core")

ROOT_DIR = Path(__file__).resolve().parent.parent
RULES_FILE = ROOT_DIR / "rules.json"

MAX_DEPTH = 4
SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target",
    ".gradle", ".idea", ".vscode", "vendor", "Pods", ".build",
}

# ─── 项目扫描 ───────────────────────────────────────────

def scan_project(project_dir: str) -> dict:
    """扫描项目，返回文件扩展名、配置文件名和包依赖。"""
    found_exts = set()
    found_configs = set()
    found_deps = set()
    project = Path(project_dir).resolve()

    for root, dirs, files in os.walk(project):
        depth = len(Path(root).relative_to(project).parts)
        if depth >= MAX_DEPTH:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            ext = Path(f).suffix
            if ext:
                found_exts.add(ext)
            found_configs.add(f)

    pkg_json = project / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                if key in pkg:
                    found_deps.update(pkg[key].keys())
        except (json.JSONDecodeError, OSError):
            pass

    return {"extensions": found_exts, "configs": found_configs, "deps": found_deps}


def match_rules(scan: dict) -> set:
    """根据 rules.json 匹配项目需要的插件名。"""
    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            rules = json.load(f)
    except (json.JSONDecodeError, OSError):
        return set()

    needed = set(rules.get("always_on", []))

    for rule in rules.get("conditional", []):
        if rule.get("_manual"):
            continue
        matched = False
        for ext in rule.get("file_extensions", []):
            if ext in scan["extensions"]:
                matched = True
                break
        if not matched:
            for cfg in rule.get("config_files", []):
                if cfg in scan["configs"]:
                    matched = True
                    break
        if not matched:
            for dep in rule.get("package_deps", []):
                if dep in scan["deps"]:
                    matched = True
                    break
        if matched:
            needed.add(rule["plugin"])

    return needed


# ─── 插件发现 (按 disable_mechanism 分流) ──────────────

def discover_plugins(cfg: dict) -> dict:
    """发现已安装插件。返回 {name: {"enabled": bool, ...}}。"""
    mechanism = cfg["disable_mechanism"]

    if mechanism == "enabledPlugins":
        return _discover_marketplace(cfg)
    elif mechanism == "disabledExtensions":
        return _discover_extensions(cfg)
    elif mechanism in ("plugin_rename", "skill_rename"):
        return _discover_file_based(cfg)
    return {}


def _discover_marketplace(cfg: dict) -> dict:
    """Claude / CodeBuddy: enabledPlugins in settings.json。"""
    settings_file = cfg["settings_file"]
    if not settings_file.exists():
        return {}
    try:
        with open(settings_file, encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    suffix = cfg.get("marketplace_suffix", "")
    plugins = {}
    for key, enabled in settings.get("enabledPlugins", {}).items():
        name = key.replace(suffix, "") if suffix else key.split("@")[0]
        plugins[name] = {"enabled": enabled, "key": key}
    return plugins


def _discover_extensions(cfg: dict) -> dict:
    """Gemini / Qwen: extensions dir + disabledExtensions list。"""
    ext_dir = cfg.get("extensions_dir")
    if not ext_dir or not ext_dir.exists():
        return {}

    settings_file = cfg["settings_file"]
    disabled = set()
    if settings_file.exists():
        try:
            with open(settings_file, encoding="utf-8") as f:
                disabled = set(json.load(f).get("disabledExtensions", []))
        except (json.JSONDecodeError, OSError):
            pass

    manifest_name = cfg.get("extension_manifest", "")
    plugins = {}
    for d in sorted(ext_dir.iterdir()):
        if not d.is_dir():
            continue
        if manifest_name and not (d / manifest_name).exists():
            continue
        plugins[d.name] = {"enabled": d.name not in disabled, "dir": d}
    return plugins


def _discover_file_based(cfg: dict) -> dict:
    """Kimi / Codex / Qoder: file rename based。"""
    plugins = {}

    # Kimi plugins
    plugins_dir = cfg.get("plugins_dir")
    if plugins_dir and plugins_dir.exists():
        for d in sorted(plugins_dir.iterdir()):
            if not d.is_dir():
                continue
            if (d / "plugin.json").exists():
                plugins[d.name] = {"enabled": True, "dir": d}
            elif (d / "plugin.json.disabled").exists():
                plugins[d.name] = {"enabled": False, "dir": d}

    # Skills dirs
    for skills_dir in cfg.get("skills_dirs", []):
        if not skills_dir.exists():
            continue
        for d in sorted(skills_dir.iterdir()):
            if not d.is_dir():
                continue
            if (d / "SKILL.md").exists():
                plugins[d.name] = {"enabled": True, "dir": d}
            elif (d / "SKILL.md.disabled").exists():
                plugins[d.name] = {"enabled": False, "dir": d}

    return plugins


# ─── 启禁管理 ──────────────────────────────────────────

def apply_changes(cfg: dict, needed: set, plugins: dict, dry_run: bool = False) -> dict:
    """根据 needed 集合启禁插件。返回 changes dict。"""
    mechanism = cfg["disable_mechanism"]
    changes = {"enabled": [], "disabled": [], "unchanged": []}

    if mechanism == "enabledPlugins":
        _apply_marketplace(cfg, needed, plugins, changes, dry_run)
    elif mechanism == "disabledExtensions":
        _apply_extensions(cfg, needed, plugins, changes, dry_run)
    elif mechanism in ("plugin_rename", "skill_rename"):
        _apply_file_rename(cfg, needed, plugins, changes, dry_run)

    return changes


def _apply_marketplace(cfg, needed, plugins, changes, dry_run):
    settings_file = cfg["settings_file"]
    if not settings_file.exists():
        return
    with open(settings_file, encoding="utf-8") as f:
        settings = json.load(f)

    ep = settings.get("enabledPlugins", {})
    modified = False
    for name, info in plugins.items():
        key = info.get("key", name)
        should = name in needed
        current = ep.get(key, False)

        if should and not current:
            changes["enabled"].append(name)
            if not dry_run:
                ep[key] = True
                modified = True
        elif not should and current:
            changes["disabled"].append(name)
            if not dry_run:
                ep[key] = False
                modified = True
        else:
            changes["unchanged"].append(name)

    if not dry_run and modified:
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")


def _apply_extensions(cfg, needed, plugins, changes, dry_run):
    settings_file = cfg["settings_file"]
    settings = {}
    if settings_file.exists():
        with open(settings_file, encoding="utf-8") as f:
            settings = json.load(f)

    disabled = set(settings.get("disabledExtensions", []))
    modified = False
    for name in plugins:
        should = name in needed
        is_disabled = name in disabled

        if should and is_disabled:
            changes["enabled"].append(name)
            if not dry_run:
                disabled.discard(name)
                modified = True
        elif not should and not is_disabled:
            changes["disabled"].append(name)
            if not dry_run:
                disabled.add(name)
                modified = True
        else:
            changes["unchanged"].append(name)

    if not dry_run and modified:
        settings["disabledExtensions"] = sorted(disabled)
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")


def _apply_file_rename(cfg, needed, plugins, changes, dry_run):
    mechanism = cfg["disable_mechanism"]
    for name, info in plugins.items():
        d = info.get("dir")
        if not d:
            changes["unchanged"].append(name)
            continue

        should = name in needed
        is_enabled = info["enabled"]

        if mechanism == "plugin_rename":
            active, inactive = d / "plugin.json", d / "plugin.json.disabled"
        else:
            active, inactive = d / "SKILL.md", d / "SKILL.md.disabled"

        if should and not is_enabled:
            changes["enabled"].append(name)
            if not dry_run and inactive.exists():
                inactive.rename(active)
        elif not should and is_enabled:
            changes["disabled"].append(name)
            if not dry_run and active.exists():
                active.rename(inactive)
        else:
            changes["unchanged"].append(name)


# ─── 缓存构建 ──────────────────────────────────────────

def build_cache(cfg: dict) -> dict:
    """为指定 CLI 构建反向索引缓存。只索引禁用插件。"""
    plugins = discover_plugins(cfg)
    mechanism = cfg["disable_mechanism"]

    skills_table = []
    skill_keywords = []
    skipped = 0

    if mechanism == "enabledPlugins":
        skipped = _scan_marketplace_skills(cfg, plugins, skills_table, skill_keywords, skipped)
    elif mechanism == "disabledExtensions":
        skipped = _scan_extension_skills(cfg, plugins, skills_table, skill_keywords)
    elif mechanism in ("plugin_rename", "skill_rename"):
        skipped = _scan_file_skills(plugins, skills_table, skill_keywords)

    # 路径前缀压缩
    if skills_table:
        all_paths = [s[2] for s in skills_table]
        base = os.path.commonpath(all_paths) if len(all_paths) > 1 else str(Path(all_paths[0]).parent)
        plen = len(base) + 1
        short = [[s[0], s[1], s[2][plen:], s[3]] for s in skills_table]
    else:
        base, short = "", []

    inverted = {}
    for sid, kws in enumerate(skill_keywords):
        for kw in kws:
            inverted.setdefault(kw, []).append(sid)

    index = {"v": 2, "b": base, "s": short, "i": inverted}

    out = cfg["cache_dir"] / "skills_index.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    return {"index": index, "total": len(skills_table), "skipped": skipped, "path": out}


def _parse_skill_md(path: Path, group: str, name_fallback: str):
    try:
        content = path.read_text(errors="replace", encoding="utf-8")
    except OSError:
        return None
    fm = parse_frontmatter(content)
    name = fm.get("name", name_fallback)
    desc = fm.get("description", "")
    body = get_body_without_frontmatter(content)
    kws = extract_keywords(name, desc, body)[:10]
    summary = desc[:120].strip()
    if desc and len(desc) > 120:
        summary += "..."
    return [group, name, str(path), summary], kws


def _find_skill_md(item: Path):
    if item.is_file() and item.suffix == ".md":
        return item
    if item.is_dir() and (item / "SKILL.md").exists():
        return item / "SKILL.md"
    return None


def _scan_marketplace_skills(cfg, plugins, table, kws_list, skipped):
    cache_dir = cfg.get("plugin_cache")
    if not cache_dir or not cache_dir.exists():
        return skipped

    for plugin_dir in sorted(cache_dir.iterdir()):
        if not plugin_dir.is_dir():
            continue
        name = plugin_dir.name
        if plugins.get(name, {}).get("enabled", True):
            skipped += 1
            continue
        # find version dir
        versions = [d for d in plugin_dir.iterdir() if d.is_dir()]
        vdir = ([v for v in versions if v.name != "unknown"] or versions or [None])[0]
        if not vdir:
            continue
        skills = vdir / "skills"
        if not skills.exists():
            continue
        for item in sorted(skills.iterdir()):
            md = _find_skill_md(item)
            if not md:
                continue
            entry = _parse_skill_md(md, name, item.stem if item.is_file() else item.name)
            if entry:
                table.append(entry[0])
                kws_list.append(entry[1])
    return skipped


def _scan_extension_skills(cfg, plugins, table, kws_list):
    skipped = 0
    ext_dir = cfg.get("extensions_dir")
    if not ext_dir or not ext_dir.exists():
        return skipped
    for d in sorted(ext_dir.iterdir()):
        if not d.is_dir():
            continue
        if plugins.get(d.name, {}).get("enabled", True):
            skipped += 1
            continue
        skills = d / "skills"
        if not skills.exists():
            continue
        for item in sorted(skills.iterdir()):
            md = _find_skill_md(item)
            if not md:
                continue
            entry = _parse_skill_md(md, d.name, item.stem if item.is_file() else item.name)
            if entry:
                table.append(entry[0])
                kws_list.append(entry[1])
    return skipped


def _scan_file_skills(plugins, table, kws_list):
    skipped = 0
    for name, info in plugins.items():
        if info["enabled"]:
            skipped += 1
            continue
        d = info.get("dir")
        if not d:
            continue
        for candidate in [d / "SKILL.md.disabled", d / "SKILL.md"]:
            if candidate.exists():
                entry = _parse_skill_md(candidate, name, name)
                if entry:
                    table.append(entry[0])
                    kws_list.append(entry[1])
                break
    return skipped


# ─── 关键词注入 (prompt_inject) ────────────────────────

PLUGIN_NAME_STOPWORDS = {
    "data", "code", "dev", "app", "test", "set", "run", "get",
    "add", "use", "new", "the", "for", "and", "not", "but",
    "all", "can", "has", "its", "let", "may", "own", "say",
}

PROMPT_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into",
    "this", "that", "these", "those", "it", "its", "and", "or",
    "but", "not", "if", "then", "else", "when", "where", "how",
    "what", "which", "who", "why", "all", "some", "any", "no",
    "so", "than", "too", "very", "just", "use", "using", "used",
    "your", "you", "they", "them", "their", "about", "need",
    "want", "like", "make", "get", "set", "run", "add", "new",
    "one", "two", "also", "been", "more", "most", "only", "each",
    "now", "way", "own", "here", "there",
}

MIN_MATCH_SCORE = 3
MAX_SKILLS = 2


def extract_prompt_words(prompt: str) -> set:
    text = prompt.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    words = set(text.split())
    words.update(re.sub(r"[^\w\s]", " ", prompt).split())
    return {w for w in words if len(w) >= 3 and w.lower() not in PROMPT_STOPWORDS}


def find_matching_skills(prompt: str, index: dict) -> list:
    prompt_words = extract_prompt_words(prompt)
    inverted = index.get("i", {})
    skills_table = index.get("s", [])
    base = index.get("b", "")

    hit_counts = {}
    for word in prompt_words:
        sids = inverted.get(word.lower())
        if sids:
            for sid in sids:
                hit_counts[sid] = hit_counts.get(sid, 0) + 1

    if not hit_counts:
        return []

    candidates = []
    for sid, kw_hits in hit_counts.items():
        if sid >= len(skills_table):
            continue
        entry = skills_table[sid]
        pname, sname, rel_path = entry[0], entry[1], entry[2]
        summary = entry[3] if len(entry) > 3 else ""
        score = kw_hits * 2

        # 插件名匹配加分
        pl = pname.lower().replace("-", " ").replace("_", " ")
        meaningful = set(pl.split()) - PLUGIN_NAME_STOPWORDS
        if meaningful:
            for w in prompt_words:
                wl = w.lower()
                if wl == pl.replace(" ", ""):
                    score += 5
                    break
                if len(wl) >= 4:
                    for part in meaningful:
                        if len(part) >= 4 and (wl == part or wl.startswith(part) or part.startswith(wl)):
                            score += 4
                            break

        if score >= MIN_MATCH_SCORE:
            full_path = os.path.join(base, rel_path) if base else rel_path
            candidates.append({
                "plugin": pname, "skill": sname,
                "score": score, "file": full_path, "summary": summary,
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:MAX_SKILLS]


def format_inject_output(matches: list, cfg: dict) -> dict:
    """按 CLI 的 hook 输出格式生成 JSON。"""
    parts = []
    for m in matches:
        desc = f": {m['summary']}" if m.get("summary") else ""
        parts.append(f"- {m['plugin']}:{m['skill']}{desc}\n  File: {m['file']}")

    text = (
        "[Skill hint] The following disabled plugin skills match your query. "
        "Read the file if needed:\n" + "\n".join(parts)
    )

    output_type = cfg.get("hook_output", "additionalContext")
    if output_type == "hookSpecificOutput":
        event = cfg["hooks"].get("prompt_submit", "UserPromptSubmit")
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    else:
        return {"additionalContext": text}
