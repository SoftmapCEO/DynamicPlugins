#!/usr/bin/env python3
"""
Kimi Code CLI skills 索引缓存构建器

扫描 Kimi plugins 和 skills 目录，构建反向索引用于关键词匹配。
只索引被禁用的 plugins（已启用的无需热加载）。

Plugins:  ~/.kimi/plugins/
Skills:   ~/.kimi/skills/, ~/.agents/skills/

用法: python3 build_cache.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.logger import get_logger
from lib.skill_parser import parse_frontmatter, extract_keywords, get_body_without_frontmatter

log = get_logger("kimi_build_cache")

PLUGINS_DIR = Path.home() / ".kimi" / "plugins"
SKILLS_DIRS = [
    Path.home() / ".kimi" / "skills",
    Path.home() / ".agents" / "skills",
]
OUTPUT = Path(__file__).resolve().parent / "cache" / "skills_index.json"


def build_index():
    """构建 Kimi skills 的反向索引。"""
    log.info("开始构建 Kimi skills 缓存")

    skills_table = []
    skill_keywords = []
    skipped_enabled = 0
    errors = 0

    # 1. 扫描禁用 plugins 中的 skills
    if PLUGINS_DIR.exists():
        for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
            if not plugin_dir.is_dir():
                continue

            # 只索引禁用的 plugins
            if (plugin_dir / "plugin.json").exists():
                skipped_enabled += 1
                continue
            if not (plugin_dir / "plugin.json.disabled").exists():
                continue

            plugin_name = plugin_dir.name

            # 扫描 plugin 内的 skills 和脚本
            for skill_dir in [plugin_dir / "skills", plugin_dir / "scripts", plugin_dir]:
                if not skill_dir.exists():
                    continue
                for item in sorted(skill_dir.iterdir()):
                    skill_md = _find_skill_md(item)
                    if not skill_md:
                        continue
                    entry = _parse_skill(skill_md, plugin_name, item)
                    if entry:
                        skills_table.append(entry[0])
                        skill_keywords.append(entry[1])
                    else:
                        errors += 1

    # 2. 扫描独立 skills 目录
    for skills_dir in SKILLS_DIRS:
        if not skills_dir.exists():
            continue
        for item in sorted(skills_dir.iterdir()):
            skill_md = _find_skill_md(item)
            if not skill_md:
                continue
            group = skill_md.parent.name if skill_md.parent.name != "skills" else item.stem
            entry = _parse_skill(skill_md, group, item)
            if entry:
                skills_table.append(entry[0])
                skill_keywords.append(entry[1])
            else:
                errors += 1

    # 路径前缀压缩
    if skills_table:
        all_paths = [s[2] for s in skills_table]
        base = os.path.commonpath(all_paths) if len(all_paths) > 1 else str(Path(all_paths[0]).parent)
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


def _find_skill_md(item: Path):
    """查找 SKILL.md 文件。"""
    if item.is_file() and item.suffix == ".md":
        return item
    if item.is_dir():
        candidate = item / "SKILL.md"
        if candidate.exists():
            return candidate
    return None


def _parse_skill(skill_md: Path, plugin_name: str, item: Path):
    """解析一个 skill 文件，返回 (table_entry, keywords) 或 None。"""
    try:
        content = skill_md.read_text(errors="replace")
    except OSError as e:
        log.warning("读取 skill 失败: %s -> %s", skill_md, e)
        return None

    fm = parse_frontmatter(content)
    name = fm.get("name", item.stem if item.is_file() else item.name)
    description = fm.get("description", "")
    body = get_body_without_frontmatter(content)
    keywords = extract_keywords(name, description, body)[:10]

    summary = description[:120].strip()
    if description and len(description) > 120:
        summary += "..."

    return ([plugin_name, name, str(skill_md), summary], keywords)


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    index, total, skipped, errors = build_index()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size = OUTPUT.stat().st_size
    print(f"Kimi skills 缓存已构建: {OUTPUT}")
    print(f"  Skills: {total} 个")
    print(f"  关键词: {len(index['i'])} 个")
    print(f"  启用 plugins (已跳过): {skipped} 个")
    print(f"  索引大小: {size // 1024} KB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
