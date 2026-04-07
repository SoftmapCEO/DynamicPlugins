#!/usr/bin/env python3
"""
从所有已安装插件中提取 skill 元数据，构建可搜索的索引缓存。
索引用于 UserPromptSubmit hook 快速匹配用户意图。

用法: python3 build_cache.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.logger import get_logger
from lib.skill_parser import STOPWORDS, parse_frontmatter, extract_keywords, get_body_without_frontmatter

log = get_logger("build_cache")

PLUGIN_CACHE = Path.home() / ".claude/plugins/cache/claude-plugins-official"
OUTPUT = Path(__file__).parent / "cache" / "skills_index.json"
SETTINGS_FILE = Path.home() / ".claude/settings.json"


def find_latest_version(plugin_dir: Path) :
    """找到插件的最新版本目录。"""
    versions = [d for d in plugin_dir.iterdir() if d.is_dir()]
    if not versions:
        return None
    named = [v for v in versions if v.name != "unknown"]
    return named[0] if named else versions[0]


def build_index():
    """构建反向索引 + 路径前缀压缩。

    输出格式:
      v: 版本号
      b: 文件路径公共前缀
      s: skills 表 [[plugin, skill, relative_path], ...]  下标即 skill_id
      i: 反向索引 {keyword: [skill_id, ...]}
    """
    log.info("开始构建缓存索引")

    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("读取 settings.json 失败: %s", e)
        raise

    enabled_plugins = settings.get("enabledPlugins", {})

    if not PLUGIN_CACHE.exists():
        log.error("插件缓存目录不存在: %s", PLUGIN_CACHE)
        return {"v": 2, "b": "", "s": [], "i": {}}, 0, 0, 0

    # 第一遍: 收集所有 skill 及其关键词
    skills_table = []  # [[plugin, skill, full_path], ...]
    skill_keywords = []  # [["kw1","kw2",...], ...]  与 skills_table 一一对应
    skipped_enabled = 0
    errors = 0

    for plugin_dir in sorted(PLUGIN_CACHE.iterdir()):
        if not plugin_dir.is_dir():
            continue

        plugin_name = plugin_dir.name
        version_dir = find_latest_version(plugin_dir)
        if not version_dir:
            continue

        skills_dir = version_dir / "skills"
        if not skills_dir.exists():
            continue

        key = f"{plugin_name}@claude-plugins-official"
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
                log.warning("读取 skill 文件失败: %s -> %s", skill_md, e)
                errors += 1
                continue

            fm = parse_frontmatter(content)
            name = fm.get("name", skill_path.stem)
            description = fm.get("description", "")
            body = get_body_without_frontmatter(content)
            keywords = extract_keywords(name, description, body)[:10]

            # 摘要: 描述截取前 120 字符
            summary = description[:120].strip()
            if description and len(description) > 120:
                summary += "..."

            skills_table.append([plugin_name, name, str(skill_md), summary])
            skill_keywords.append(keywords)

    # 路径前缀压缩
    if skills_table:
        all_paths = [s[2] for s in skills_table]
        base = os.path.commonpath(all_paths)
        prefix_len = len(base) + 1  # +1 for trailing separator
        # s: [plugin, skill, rel_path, summary]
        skills_short = [[s[0], s[1], s[2][prefix_len:], s[3]] for s in skills_table]
    else:
        base = ""
        skills_short = []

    # 构建反向索引: keyword -> [skill_id, ...]
    inverted = {}
    for sid, kws in enumerate(skill_keywords):
        for kw in kws:
            if kw not in inverted:
                inverted[kw] = []
            inverted[kw].append(sid)

    total_skills = len(skills_table)
    plugin_count = len(set(s[0] for s in skills_table))

    log.info(
        "索引构建完成: %d 禁用插件, %d skills, %d 关键词, %d 启用跳过, %d 错误",
        plugin_count, total_skills, len(inverted), skipped_enabled, errors,
    )
    return {"v": 2, "b": base, "s": skills_short, "i": inverted}, total_skills, skipped_enabled, errors


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    index, total, skipped, errors = build_index()

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    index_size = OUTPUT.stat().st_size
    plugin_count = len(set(s[0] for s in index["s"]))

    summary = (
        f"缓存已构建: {OUTPUT}\n"
        f"  禁用插件(可热加载): {plugin_count} 个\n"
        f"  Skills: {total} 个\n"
        f"  唯一关键词: {len(index['i'])} 个\n"
        f"  启用插件(已跳过): {skipped} 个\n"
        f"  索引大小: {index_size // 1024} KB"
    )
    print(summary)
    log.info(summary.replace("\n", " | "))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
