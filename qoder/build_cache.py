#!/usr/bin/env python3
"""
Qoder CLI skills 索引缓存构建器

扫描禁用的 Qoder skills，构建反向索引用于关键词匹配。
只索引 SKILL.md.disabled（已启用的无需热加载）。

Skills: ~/.qoder/skills/

用法: python3 build_cache.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.logger import get_logger
from lib.skill_parser import parse_frontmatter, extract_keywords, get_body_without_frontmatter

log = get_logger("qoder_build_cache")

SKILLS_DIR = Path.home() / ".qoder" / "skills"
OUTPUT = Path(__file__).resolve().parent / "cache" / "skills_index.json"


def build_index():
    """构建 Qoder skills 的反向索引。"""
    log.info("开始构建 Qoder skills 缓存")

    skills_table = []
    skill_keywords = []
    skipped_enabled = 0
    errors = 0

    if not SKILLS_DIR.exists():
        log.warning("skills 目录不存在: %s", SKILLS_DIR)
        return {"v": 2, "b": "", "s": [], "i": {}}, 0, 0, 0

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue

        active = skill_dir / "SKILL.md"
        disabled = skill_dir / "SKILL.md.disabled"

        # 跳过启用的 skills
        if active.exists():
            skipped_enabled += 1
            continue

        # 只索引禁用的
        if not disabled.exists():
            continue

        try:
            content = disabled.read_text(errors="replace")
        except OSError as e:
            log.warning("读取 skill 失败: %s -> %s", disabled, e)
            errors += 1
            continue

        fm = parse_frontmatter(content)
        name = fm.get("name", skill_dir.name)
        description = fm.get("description", "")
        body = get_body_without_frontmatter(content)
        keywords = extract_keywords(name, description, body)[:10]

        summary = description[:120].strip()
        if description and len(description) > 120:
            summary += "..."

        skills_table.append([skill_dir.name, name, str(disabled), summary])
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

    log.info("索引完成: %d skills, %d 关键词, %d 启用跳过, %d 错误",
             len(skills_table), len(inverted), skipped_enabled, errors)
    return {"v": 2, "b": base, "s": skills_short, "i": inverted}, len(skills_table), skipped_enabled, errors


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    index, total, skipped, errors = build_index()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size = OUTPUT.stat().st_size
    print(f"Qoder skills 缓存已构建: {OUTPUT}")
    print(f"  禁用 skills (可热加载): {total} 个")
    print(f"  关键词: {len(index['i'])} 个")
    print(f"  启用 skills (已跳过): {skipped} 个")
    print(f"  索引大小: {size // 1024} KB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
