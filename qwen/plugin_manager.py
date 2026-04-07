#!/usr/bin/env python3
"""
Qwen Code CLI 插件动态管理器

根据项目内容自动启用/禁用 Qwen extensions。
扫描项目目录中的文件扩展名、配置文件和包依赖来决定需要哪些 extensions。

Extensions:  ~/.qwen/extensions/<name>/qwen-extension.json
Skills:      ~/.qwen/skills/
配置:        ~/.qwen/settings.json

用法:
    python3 plugin_manager.py <project_dir>         # 扫描并应用
    python3 plugin_manager.py <project_dir> --dry    # 仅预览
    python3 plugin_manager.py --restore              # 恢复全部启用
"""

import json
import sys
import os
import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.logger import get_logger

log = get_logger("qwen_plugin_manager")

SCRIPT_DIR = Path(__file__).resolve().parent
RULES_FILE = SCRIPT_DIR.parent / "rules.json"
SETTINGS_FILE = Path.home() / ".qwen" / "settings.json"
EXTENSIONS_DIR = Path.home() / ".qwen" / "extensions"

MAX_DEPTH = 4
SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target",
    ".gradle", ".idea", ".vscode", "vendor", "Pods", ".build",
}


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("加载 settings.json 失败: %s", e)
        return {}


def save_settings(settings: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    log.info("settings.json 已保存")


def discover_extensions() -> dict:
    """发现所有已安装的 Qwen extensions。

    返回 {name: manifest_dict}。
    """
    extensions = {}
    if not EXTENSIONS_DIR.exists():
        return extensions

    for ext_dir in sorted(EXTENSIONS_DIR.iterdir()):
        if not ext_dir.is_dir():
            continue
        manifest = ext_dir / "qwen-extension.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
            extensions[ext_dir.name] = data
        except (json.JSONDecodeError, OSError) as e:
            log.warning("读取 extension manifest 失败: %s -> %s", manifest, e)

    return extensions


def scan_project(project_dir: str) -> dict:
    """扫描项目，返回文件扩展名、配置和依赖。"""
    found_extensions = set()
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
                found_extensions.add(ext)
            found_configs.add(f)

    pkg_json = project / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                if key in pkg:
                    found_deps.update(pkg[key].keys())
        except (json.JSONDecodeError, OSError):
            pass

    return {"extensions": found_extensions, "configs": found_configs, "deps": found_deps}


def determine_needed_extensions(project_dir: str, extensions: dict) -> set:
    """根据项目内容确定需要的 extensions。"""
    scan = scan_project(project_dir)
    needed = set()

    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            rules = json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("无法加载 rules.json, 使用名称匹配")
        rules = {"always_on": [], "conditional": []}

    ext_name_map = {name.lower(): name for name in extensions}

    for rule in rules.get("conditional", []):
        plugin = rule["plugin"].lower()
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

        if matched and plugin in ext_name_map:
            needed.add(ext_name_map[plugin])

    return needed


def apply_extensions(needed: set, extensions: dict, dry_run: bool = False) -> dict:
    """更新 settings.json 中的 disabledExtensions。"""
    settings = load_settings()
    disabled = set(settings.get("disabledExtensions", []))
    changes = {"enabled": [], "disabled": [], "unchanged": []}

    for name in extensions:
        should_enable = name in needed
        is_disabled = name in disabled

        if should_enable and is_disabled:
            changes["enabled"].append(name)
            if not dry_run:
                disabled.discard(name)
        elif not should_enable and not is_disabled:
            changes["disabled"].append(name)
            if not dry_run:
                disabled.add(name)
        else:
            changes["unchanged"].append(name)

    if not dry_run and (changes["enabled"] or changes["disabled"]):
        settings["disabledExtensions"] = sorted(disabled)
        save_settings(settings)
        log.info("已应用: 启用 %d, 禁用 %d", len(changes["enabled"]), len(changes["disabled"]))

    return changes


def restore_all():
    """恢复所有 extensions 为启用。"""
    settings = load_settings()
    count = len(settings.get("disabledExtensions", []))
    settings["disabledExtensions"] = []
    save_settings(settings)
    log.info("已恢复 %d 个 extensions", count)
    return count


def main():
    args = sys.argv[1:]
    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    if "--restore" in args:
        count = restore_all()
        print(f"已恢复 {count} 个 extensions 为启用。")
        sys.exit(0)

    project_dir = args[0]
    dry_run = "--dry" in args

    if not os.path.isdir(project_dir):
        print(f"错误: 目录不存在: {project_dir}", file=sys.stderr)
        sys.exit(1)

    extensions = discover_extensions()
    log.info("发现 %d 个 extensions", len(extensions))

    needed = determine_needed_extensions(project_dir, extensions)

    if not dry_run:
        from lib.registry import ensure_plugins_available
        ensure_plugins_available("qwen", needed, set(extensions.keys()))
        extensions = discover_extensions()

    changes = apply_extensions(needed, extensions, dry_run=dry_run)

    prefix = "[预览] " if dry_run else ""
    print(f"\n{prefix}Qwen Extensions 配置")
    print("=" * 50)
    if changes["enabled"]:
        print(f"\n  新启用 ({len(changes['enabled'])}):")
        for p in sorted(changes["enabled"]):
            print(f"    + {p}")
    if changes["disabled"]:
        print(f"\n  将禁用 ({len(changes['disabled'])}):")
        for p in sorted(changes["disabled"]):
            print(f"    - {p}")
    total = len(changes["enabled"]) + len(changes["disabled"]) + len(changes["unchanged"])
    enabled_count = len(changes["enabled"]) + len([p for p in changes["unchanged"] if p in needed])
    print(f"\n  总计: {enabled_count} 启用 / {total - enabled_count} 禁用 / {total} 总数")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
