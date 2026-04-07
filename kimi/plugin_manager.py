#!/usr/bin/env python3
"""
Kimi Code CLI 插件动态管理器

根据项目内容自动启用/禁用 Kimi plugins 和 skills。
扫描项目目录中的文件扩展名、配置文件和包依赖来决定需要哪些插件。

Kimi plugins:  ~/.kimi/plugins/<name>/plugin.json
Kimi skills:   ~/.kimi/skills/
配置:          ~/.kimi/config.toml (TOML 格式)

禁用机制: 将 plugin.json 重命名为 plugin.json.disabled

用法:
    python3 plugin_manager.py <project_dir>         # 扫描并应用
    python3 plugin_manager.py <project_dir> --dry    # 仅预览
    python3 plugin_manager.py --restore              # 恢复全部启用
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.logger import get_logger

log = get_logger("kimi_plugin_manager")

SCRIPT_DIR = Path(__file__).resolve().parent
RULES_FILE = SCRIPT_DIR.parent / "rules.json"
PLUGINS_DIR = Path.home() / ".kimi" / "plugins"
SKILLS_DIRS = [
    Path.home() / ".kimi" / "skills",
    Path.home() / ".agents" / "skills",
]

MAX_DEPTH = 4
SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target",
    ".gradle", ".idea", ".vscode", "vendor", "Pods", ".build",
}


def discover_plugins() -> dict:
    """发现所有已安装的 Kimi plugins。

    返回 {name: {"enabled": bool, "dir": Path, "manifest": dict}}。
    """
    plugins = {}
    if not PLUGINS_DIR.exists():
        return plugins

    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue

        manifest_active = plugin_dir / "plugin.json"
        manifest_disabled = plugin_dir / "plugin.json.disabled"

        if manifest_active.exists():
            try:
                data = json.loads(manifest_active.read_text())
                plugins[plugin_dir.name] = {
                    "enabled": True, "dir": plugin_dir, "manifest": data,
                }
            except (json.JSONDecodeError, OSError) as e:
                log.warning("读取 plugin manifest 失败: %s -> %s", manifest_active, e)
        elif manifest_disabled.exists():
            try:
                data = json.loads(manifest_disabled.read_text())
                plugins[plugin_dir.name] = {
                    "enabled": False, "dir": plugin_dir, "manifest": data,
                }
            except (json.JSONDecodeError, OSError) as e:
                log.warning("读取 disabled manifest 失败: %s -> %s", manifest_disabled, e)

    return plugins


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


def determine_needed_plugins(project_dir: str, plugins: dict) -> set:
    """根据项目内容确定需要的 plugins。"""
    scan = scan_project(project_dir)
    needed = set()

    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            rules = json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("无法加载 rules.json, 使用名称匹配")
        rules = {"always_on": [], "conditional": []}

    plugin_name_map = {name.lower(): name for name in plugins}

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

        if matched and plugin in plugin_name_map:
            needed.add(plugin_name_map[plugin])

    return needed


def apply_plugins(needed: set, plugins: dict, dry_run: bool = False) -> dict:
    """启用/禁用 plugins。通过重命名 plugin.json 实现。"""
    changes = {"enabled": [], "disabled": [], "unchanged": []}

    for name, info in plugins.items():
        should_enable = name in needed
        is_enabled = info["enabled"]
        plugin_dir = info["dir"]

        if should_enable and not is_enabled:
            changes["enabled"].append(name)
            if not dry_run:
                src = plugin_dir / "plugin.json.disabled"
                dst = plugin_dir / "plugin.json"
                if src.exists():
                    src.rename(dst)
                    log.info("启用: %s", name)
        elif not should_enable and is_enabled:
            changes["disabled"].append(name)
            if not dry_run:
                src = plugin_dir / "plugin.json"
                dst = plugin_dir / "plugin.json.disabled"
                if src.exists():
                    src.rename(dst)
                    log.info("禁用: %s", name)
        else:
            changes["unchanged"].append(name)

    if not dry_run and (changes["enabled"] or changes["disabled"]):
        log.info("已应用: 启用 %d, 禁用 %d", len(changes["enabled"]), len(changes["disabled"]))

    return changes


def restore_all():
    """恢复所有 plugins 为启用。"""
    if not PLUGINS_DIR.exists():
        return 0

    count = 0
    for plugin_dir in PLUGINS_DIR.iterdir():
        if not plugin_dir.is_dir():
            continue
        disabled = plugin_dir / "plugin.json.disabled"
        active = plugin_dir / "plugin.json"
        if disabled.exists() and not active.exists():
            disabled.rename(active)
            count += 1
            log.info("恢复: %s", plugin_dir.name)

    log.info("已恢复 %d 个 plugins", count)
    return count


def main():
    args = sys.argv[1:]
    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    if "--restore" in args:
        count = restore_all()
        print(f"已恢复 {count} 个 plugins 为启用。")
        sys.exit(0)

    project_dir = args[0]
    dry_run = "--dry" in args

    if not os.path.isdir(project_dir):
        print(f"错误: 目录不存在: {project_dir}", file=sys.stderr)
        sys.exit(1)

    plugins = discover_plugins()
    log.info("发现 %d 个 plugins", len(plugins))

    needed = determine_needed_plugins(project_dir, plugins)

    if not dry_run:
        from lib.registry import ensure_plugins_available
        ensure_plugins_available("kimi", needed, set(plugins.keys()))
        plugins = discover_plugins()

    changes = apply_plugins(needed, plugins, dry_run=dry_run)

    prefix = "[预览] " if dry_run else ""
    print(f"\n{prefix}Kimi Plugins 配置")
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
