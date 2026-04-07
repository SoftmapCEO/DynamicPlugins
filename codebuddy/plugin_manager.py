#!/usr/bin/env python3
"""
CodeBuddy CLI 插件动态管理器 (腾讯云 CodeBuddy Code)

根据项目内容自动启用/禁用 CodeBuddy 插件。
架构与 Claude Code 几乎一致: enabledPlugins map in settings.json。

配置: ~/.codebuddy/settings.json
插件缓存: ~/.codebuddy/plugins/cache/

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

log = get_logger("codebuddy_plugin_manager")

SCRIPT_DIR = Path(__file__).resolve().parent
RULES_FILE = SCRIPT_DIR.parent / "rules.json"
SETTINGS_FILE = Path.home() / ".codebuddy" / "settings.json"
PLUGIN_CACHE = Path.home() / ".codebuddy" / "plugins" / "cache"

MAX_DEPTH = 4
SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target",
    ".gradle", ".idea", ".vscode", "vendor", "Pods", ".build",
}


def load_rules() -> dict:
    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("加载规则文件失败: %s", e)
        raise


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


def determine_plugins(project_dir: str, rules: dict) -> set:
    """根据项目扫描结果和规则确定需要启用的插件。"""
    needed = set(rules.get("always_on", []))
    scan = scan_project(project_dir)

    for rule in rules.get("conditional", []):
        plugin = rule["plugin"]
        if rule.get("_manual"):
            continue

        matched = False
        for ext in rule.get("file_extensions", []):
            if ext in scan["extensions"]:
                matched = True
                break
        if not matched:
            for cfg in rule.get("config_files", []):
                if "*" in cfg:
                    if any(fnmatch.fnmatch(c, cfg) for c in scan["configs"]):
                        matched = True
                        break
                elif cfg in scan["configs"]:
                    matched = True
                    break
        if not matched:
            for dep in rule.get("package_deps", []):
                if dep in scan["deps"]:
                    matched = True
                    break

        if matched:
            needed.add(plugin)

    return needed


def apply_plugins(needed: set, dry_run: bool = False) -> dict:
    """更新 settings.json 中的 enabledPlugins。"""
    settings = load_settings()
    enabled_plugins = settings.get("enabledPlugins", {})
    changes = {"enabled": [], "disabled": [], "unchanged": []}

    for key, current_value in enabled_plugins.items():
        # 从 key 中提取插件名 (去掉 marketplace 后缀)
        plugin_name = key.split("@")[0] if "@" in key else key
        should_enable = plugin_name in needed

        if should_enable and not current_value:
            changes["enabled"].append(plugin_name)
            if not dry_run:
                enabled_plugins[key] = True
        elif not should_enable and current_value:
            changes["disabled"].append(plugin_name)
            if not dry_run:
                enabled_plugins[key] = False
        else:
            changes["unchanged"].append(plugin_name)

    if not dry_run and (changes["enabled"] or changes["disabled"]):
        save_settings(settings)

    return changes


def restore_all():
    """恢复所有插件为启用状态。"""
    settings = load_settings()
    count = 0
    for key in settings.get("enabledPlugins", {}):
        if not settings["enabledPlugins"][key]:
            settings["enabledPlugins"][key] = True
            count += 1
    if count:
        save_settings(settings)
    return count


def main():
    args = sys.argv[1:]
    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    if "--restore" in args:
        count = restore_all()
        print(f"已恢复 {count} 个插件为启用状态。")
        sys.exit(0)

    project_dir = args[0]
    dry_run = "--dry" in args

    if not os.path.isdir(project_dir):
        print(f"错误: 目录不存在: {project_dir}", file=sys.stderr)
        sys.exit(1)

    rules = load_rules()
    needed = determine_plugins(project_dir, rules)

    if not dry_run:
        from lib.registry import ensure_plugins_available
        installed = set(
            k.split("@")[0] for k in load_settings().get("enabledPlugins", {})
        )
        ensure_plugins_available("codebuddy", needed, installed)

    changes = apply_plugins(needed, dry_run=dry_run)

    prefix = "[预览] " if dry_run else ""
    print(f"\n{prefix}CodeBuddy 插件配置")
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
    active = len(changes["enabled"]) + len([p for p in changes["unchanged"] if p in needed])
    print(f"\n  总计: {active} 启用 / {total - active} 禁用 / {total} 总数")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
