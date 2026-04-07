#!/usr/bin/env python3
"""
CodeBuddy CLI skills 索引缓存构建器

扫描禁用的 CodeBuddy 插件的 skills，构建反向索引。
插件缓存目录结构与 Claude Code 一致。

用法: python3 build_cache.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.logger import get_logger
from lib.skill_parser import parse_frontmatter, extract_keywords, get_body_without_frontmatter

log = get_logger("codebuddy_build_cache")

PLUGIN_CACHE = Path.home() / ".codebuddy" / "plugins" / "cache"
SETTINGS_FILE = Path.home() / ".codebuddy" / "settings.json"
OUTPUT = Path(__file__).resolve().parent / "cache" / "skills_index.json"


def find_latest_version(plugin_dir: Path):
    versions = [d for d in plugin_dir.iterdir() if d.is_dir()]
    if not versions:
        return None
    named = [v for v in versions if v.name != "unknown"]
    return named[0] if named else versions[0]


def build_index():
    log.info("开始构建 CodeBuddy skills 缓存")

    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        settings = {}

    enabled_plugins = settings.get("enabledPlugins", {})

    skills_table = []
    skill_keywords = []
    skipped_enabled = 0
    errors = 0

    # 扫描所有 marketplace 目录
    if PLUGIN_CACHE.exists():
        for marketplace_dir in sorted(PLUGIN_CACHE.iterdir()):
            if not marketplace_dir.is_dir():
                continue
            marketplace = marketplace_dir.name

            for plugin_dir in sorted(marketplace_dir.iterdir()):
                if not plugin_dir.is_dir():
                    continue

                plugin_name = plugin_dir.name
                version_dir = find_latest_version(plugin_dir)
                if not version_dir:
                    continue

                skills_dir = version_dir / "skills"
                if not skills_dir.exists():
                    continue

                key = f"{plugin_name}@{marketplace}"
                if enabled_plugins.get(key, False):
                    skipped_enabled += 1
                    continue

                for skill_path in sorted(skills_dir.iterdir()):
                    skill_md = None
                    if skill_path.is_file() and skill_path.suffix == ".md":
                        skill_md = skill_path
                    elif skill_path.is_dir():
                        candidate = skill_path / "SKILL.md"
                        if candidate.exists():
                            skill_md = candidate

                    if not skill_md:
                        continue

                    try:
                        content = skill_md.read_text(errors="replace")
                    except OSError as e:
                        log.warning("读取 skill 失败: %s -> %s", skill_md, e)
                        errors += 1
                        continue

                    fm = parse_frontmatter(content)
                    name = fm.get("name", skill_path.stem)
                    description = fm.get("description", "")
                    body = get_body_without_frontmatter(content)
                    keywords = extract_keywords(name, description, body)[:10]

                    summary = description[:120].strip()
                    if description and len(description) > 120:
                        summary += "..."

                    skills_table.append([plugin_name, name, str(skill_md), summary])
                    skill_keywords.append(keywords)

    # 路径前缀压缩
    if skills_table:
        all_paths = [s[2] for s in skills_table]
        base = os.path.commonpath(all_paths)
        prefix_len = len(base) + 1
        skills_short = [[s[0], s[1], s[2][prefix_len:], s[3]] for s in skills_table]
    else:
        base = ""
        skills_short = []

    # 反向索引
    inverted = {}
    for sid, kws in enumerate(skill_keywords):
        for kw in kws:
            if kw not in inverted:
                inverted[kw] = []
            inverted[kw].append(sid)

    log.info("索引完成: %d skills, %d 关键词, %d 启用跳过, %d 错误",
             len(skills_table), len(inverted), skipped_enabled, errors)
    return {"v": 2, "b": base, "s": skills_short, "i": inverted}, len(skills_table), skipped_enabled, errors


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    index, total, skipped, errors = build_index()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size = OUTPUT.stat().st_size
    print(f"CodeBuddy skills 缓存已构建: {OUTPUT}")
    print(f"  Skills: {total} 个")
    print(f"  关键词: {len(index['i'])} 个")
    print(f"  启用插件 (已跳过): {skipped} 个")
    print(f"  索引大小: {size // 1024} KB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
