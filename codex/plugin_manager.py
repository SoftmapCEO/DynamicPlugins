#!/usr/bin/env python3
"""
Codex CLI 插件动态管理器

根据项目内容自动启用/禁用 Codex skills。
扫描项目目录中的文件扩展名、配置文件和包依赖来决定需要哪些 skills。

Codex skills 位于:
  1. 项目: .agents/skills/
  2. 用户: ~/.agents/skills/
  3. 系统: /etc/codex/skills/
  4. 用户配置目录: ~/.codex/skills/

配置: ~/.codex/config.toml (TOML 格式)

用法:
    python3 plugin_manager.py <project_dir>         # 扫描并应用
    python3 plugin_manager.py <project_dir> --dry    # 仅预览
    python3 plugin_manager.py --restore              # 恢复全部启用
"""

import json
import sys
import os
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.logger import get_logger

log = get_logger("codex_plugin_manager")

SCRIPT_DIR = Path(__file__).parent
RULES_FILE = SCRIPT_DIR.parent / "rules.json"
CONFIG_FILE = Path.home() / ".codex" / "config.toml"

# Codex skills 扫描路径
SKILLS_DIRS = [
    Path.home() / ".agents" / "skills",
    Path.home() / ".codex" / "skills",
]
if sys.platform != "win32":
    SKILLS_DIRS.append(Path("/etc/codex/skills"))

MAX_DEPTH = 4
SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target",
    ".gradle", ".idea", ".vscode", "vendor", "Pods", ".build",
}


def load_config() -> str:
    """读取 config.toml 原始内容。"""
    if not CONFIG_FILE.exists():
        return ""
    return CONFIG_FILE.read_text()


def save_config(content: str):
    """保存 config.toml。"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(content)
    log.info("config.toml 已保存")


def parse_skills_config(content: str) -> dict:
    """从 config.toml 中解析 skills.config 段。

    返回 {path: enabled} 映射。
    """
    skills = {}
    # 匹配 [[skills.config]] 段
    blocks = re.findall(
        r'\[\[skills\.config\]\]\s*\n((?:[^\[]*?)?)(?=\n\[|\Z)',
        content, re.DOTALL
    )
    for block in blocks:
        path_match = re.search(r'path\s*=\s*"([^"]*)"', block)
        enabled_match = re.search(r'enabled\s*=\s*(true|false)', block)
        if path_match:
            path = path_match.group(1)
            enabled = enabled_match.group(1) == "true" if enabled_match else True
            skills[path] = enabled
    return skills


def discover_all_skills(project_dir: str) -> list:
    """发现所有可用的 Codex skills。"""
    skill_files = []

    # 项目级 skills
    project = Path(project_dir).resolve()
    p = project
    while True:
        agents_dir = p / ".agents" / "skills"
        if agents_dir.exists():
            for item in agents_dir.iterdir():
                md = None
                if item.is_file() and item.name == "SKILL.md":
                    md = item
                elif item.is_dir():
                    candidate = item / "SKILL.md"
                    if candidate.exists():
                        md = candidate
                if md:
                    skill_files.append(str(md))
        if p == p.parent or (p / ".git").exists():
            break
        p = p.parent

    # 用户级和系统级 skills
    for skills_dir in SKILLS_DIRS:
        if not skills_dir.exists():
            continue
        for item in skills_dir.iterdir():
            md = None
            if item.is_file() and item.name == "SKILL.md":
                md = item
            elif item.is_dir():
                candidate = item / "SKILL.md"
                if candidate.exists():
                    md = candidate
            if md:
                skill_files.append(str(md))

    return skill_files


def scan_project(project_dir: str) -> dict:
    """扫描项目，返回发现的文件扩展名、配置文件和包依赖。"""
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


def update_config(skills_to_disable: set, skills_to_enable: set, dry_run: bool = False):
    """更新 config.toml 中的 skills.config。"""
    content = load_config()

    # 移除已有的 skills.config 段
    content = re.sub(
        r'\[\[skills\.config\]\]\s*\n(?:[^\[]*?)(?=\n\[|\Z)',
        '', content
    ).rstrip()

    # 添加新的 skills.config 段
    new_blocks = []
    for path in sorted(skills_to_disable):
        new_blocks.append(f'[[skills.config]]\npath = "{path}"\nenabled = false\n')
    for path in sorted(skills_to_enable):
        new_blocks.append(f'[[skills.config]]\npath = "{path}"\nenabled = true\n')

    if new_blocks:
        content = content + "\n\n" + "\n".join(new_blocks)

    if not dry_run:
        save_config(content)

    return len(skills_to_enable), len(skills_to_disable)


def main():
    args = sys.argv[1:]
    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    if "--restore" in args:
        content = load_config()
        content = re.sub(
            r'\[\[skills\.config\]\]\s*\n(?:[^\[]*?)(?=\n\[|\Z)',
            '', content
        ).rstrip()
        save_config(content)
        print("已移除所有 skills.config 配置（恢复默认）。")
        sys.exit(0)

    project_dir = args[0]
    dry_run = "--dry" in args

    if not os.path.isdir(project_dir):
        print(f"错误: 目录不存在: {project_dir}", file=sys.stderr)
        sys.exit(1)

    all_skills = discover_all_skills(project_dir)
    log.info("发现 %d 个 skills", len(all_skills))

    # 自动安装缺失的官方 skills (Codex 使用 skill_stub 模式)
    if not dry_run:
        from lib.registry import ensure_plugins_available
        installed = {Path(s).parent.name for s in all_skills}
        scan = scan_project(project_dir)
        # 简单检测项目需要的插件名
        try:
            with open(RULES_FILE, encoding="utf-8") as f:
                rules = json.load(f)
            needed_names = set()
            for rule in rules.get("conditional", []):
                if rule.get("_manual"):
                    continue
                matched = any(e in scan["extensions"] for e in rule.get("file_extensions", []))
                if not matched:
                    matched = any(c in scan["configs"] for c in rule.get("config_files", []))
                if not matched:
                    matched = any(d in scan["deps"] for d in rule.get("package_deps", []))
                if matched:
                    needed_names.add(rule["plugin"])
            ensure_plugins_available("codex", needed_names, installed)
            all_skills = discover_all_skills(project_dir)
        except (json.JSONDecodeError, OSError):
            pass

    # 简单策略: 项目级 skills 始终启用，其余根据项目内容判断
    project = Path(project_dir).resolve()
    project_skills = {s for s in all_skills if s.startswith(str(project))}
    other_skills = set(all_skills) - project_skills

    prefix = "[预览] " if dry_run else ""
    print(f"\n{prefix}Codex Skills 配置")
    print("=" * 50)
    print(f"  项目 skills (始终启用): {len(project_skills)}")
    print(f"  用户/系统 skills: {len(other_skills)}")

    # 禁用非项目 skills 中与当前项目无关的
    # (简化实现: 保持全部启用，用户可手动配置)
    enabled, disabled = update_config(set(), project_skills, dry_run=dry_run)
    print(f"  启用: {enabled}, 禁用: {disabled}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
