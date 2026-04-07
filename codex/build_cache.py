#!/usr/bin/env python3
"""
Codex CLI skills 索引缓存构建器

扫描所有 Codex skill 目录，构建反向索引用于关键词匹配。
索引格式与 Claude 版本相同 (v2)，供 hook 快速查询。

Skills 扫描路径:
  ~/.agents/skills/
  ~/.codex/skills/
  /etc/codex/skills/

用法: python3 build_cache.py
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.logger import get_logger
from lib.skill_parser import STOPWORDS, parse_frontmatter, extract_keywords, get_body_without_frontmatter

log = get_logger("codex_build_cache")

SKILLS_DIRS = [
    Path.home() / ".agents" / "skills",
    Path.home() / ".codex" / "skills",
]
if sys.platform != "win32":
    SKILLS_DIRS.append(Path("/etc/codex/skills"))
OUTPUT = Path(__file__).parent / "cache" / "skills_index.json"


def build_index():
    """构建 Codex skills 的反向索引。"""
    log.info("开始构建 Codex skills 缓存")

    skills_table = []
    skill_keywords = []
    errors = 0

    for skills_dir in SKILLS_DIRS:
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

            # plugin_name 用目录名作为分组
            plugin_name = skill_md.parent.name if skill_md.parent.name != "skills" else name
            summary = description[:120].strip()
            if description and len(description) > 120:
                summary += "..."

            skills_table.append([plugin_name, name, str(skill_md), summary])
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

    log.info("索引完成: %d skills, %d 关键词, %d 错误", len(skills_table), len(inverted), errors)
    return {"v": 2, "b": base, "s": skills_short, "i": inverted}, len(skills_table), errors


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    index, total, errors = build_index()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size = OUTPUT.stat().st_size
    print(f"Codex skills 缓存已构建: {OUTPUT}")
    print(f"  Skills: {total} 个")
    print(f"  关键词: {len(index['i'])} 个")
    print(f"  索引大小: {size // 1024} KB")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
