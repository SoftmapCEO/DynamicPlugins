#!/usr/bin/env python3
"""
Gemini CLI skills 索引缓存构建器

扫描所有 Gemini extensions 中的 skills，构建反向索引用于关键词匹配。
索引格式与 Claude 版本相同 (v2)，供 hook 快速查询。

Extensions 扫描路径: ~/.gemini/extensions/

用法: python3 build_cache.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.logger import get_logger
from lib.skill_parser import STOPWORDS, parse_frontmatter, extract_keywords, get_body_without_frontmatter

log = get_logger("gemini_build_cache")

EXTENSIONS_DIR = Path.home() / ".gemini" / "extensions"
SETTINGS_FILE = Path.home() / ".gemini" / "settings.json"
OUTPUT = Path(__file__).parent / "cache" / "skills_index.json"


def get_disabled_extensions() -> set:
    """读取 settings.json 中的 disabledExtensions 列表。"""
    if not SETTINGS_FILE.exists():
        return set()
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            settings = json.load(f)
        return set(settings.get("disabledExtensions", []))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("读取 settings.json 失败: %s", e)
        return set()


def build_index():
    """构建 Gemini extensions 的反向索引。

    只索引禁用的 extensions（已启用的无需热加载）。
    """
    log.info("开始构建 Gemini extensions 缓存")

    disabled = get_disabled_extensions()
    log.info("禁用 extensions: %s", sorted(disabled) if disabled else "(无)")

    skills_table = []
    skill_keywords = []
    skipped_enabled = 0
    errors = 0

    if not EXTENSIONS_DIR.exists():
        log.warning("extensions 目录不存在: %s", EXTENSIONS_DIR)
        return {"v": 2, "b": "", "s": [], "i": {}}, 0, 0, 0

    for ext_dir in sorted(EXTENSIONS_DIR.iterdir()):
        if not ext_dir.is_dir():
            continue

        ext_name = ext_dir.name

        # 只索引禁用的 extensions
        if ext_name not in disabled:
            skipped_enabled += 1
            continue

        # 扫描 extension 中的 skills
        skills_dir = ext_dir / "skills"
        if not skills_dir.exists():
            continue

        for item in sorted(skills_dir.iterdir()):
            skill_md = None
            skill_name_fallback = item.stem

            if item.is_file() and item.suffix == ".md":
                skill_md = item
            elif item.is_dir():
                candidate = item / "SKILL.md"
                if candidate.exists():
                    skill_md = candidate
                    skill_name_fallback = item.name

            if not skill_md:
                continue

            try:
                content = skill_md.read_text(errors="replace")
            except OSError as e:
                log.warning("读取 skill 失败: %s -> %s", skill_md, e)
                errors += 1
                continue

            fm = parse_frontmatter(content)
            name = fm.get("name", skill_name_fallback)
            description = fm.get("description", "")
            body = get_body_without_frontmatter(content)
            keywords = extract_keywords(name, description, body)[:10]

            summary = description[:120].strip()
            if description and len(description) > 120:
                summary += "..."

            skills_table.append([ext_name, name, str(skill_md), summary])
            skill_keywords.append(keywords)

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

    total = len(skills_table)
    log.info("索引完成: %d skills, %d 关键词, %d 启用跳过, %d 错误",
             total, len(inverted), skipped_enabled, errors)
    return {"v": 2, "b": base, "s": skills_short, "i": inverted}, total, skipped_enabled, errors


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    index, total, skipped, errors = build_index()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size = OUTPUT.stat().st_size
    plugin_count = len(set(s[0] for s in index["s"]))

    print(f"Gemini extensions 缓存已构建: {OUTPUT}")
    print(f"  禁用 extensions (可热加载): {plugin_count} 个")
    print(f"  Skills: {total} 个")
    print(f"  关键词: {len(index['i'])} 个")
    print(f"  启用 extensions (已跳过): {skipped} 个")
    print(f"  索引大小: {size // 1024} KB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
