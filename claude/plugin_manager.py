#!/usr/bin/env python3
"""
插件动态调用管理器

根据项目内容自动启用/禁用 Claude Code 插件。
扫描项目目录中的文件扩展名、配置文件和包依赖来决定需要哪些插件。

用法:
    python3 plugin_manager.py <project_dir>         # 扫描并应用
    python3 plugin_manager.py <project_dir> --dry    # 仅预览，不修改
    python3 plugin_manager.py --restore              # 恢复所有插件为启用
"""

import json
import sys
import os
import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.logger import get_logger

log = get_logger("plugin_manager")

SCRIPT_DIR = Path(__file__).parent
RULES_FILE = SCRIPT_DIR.parent / "rules.json"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
MARKETPLACE_SUFFIX = "@claude-plugins-official"

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
        log.error("加载规则文件失败: %s -> %s", RULES_FILE, e)
        raise


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("加载设置文件失败: %s -> %s", SETTINGS_FILE, e)
        raise


def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")
        log.info("settings.json 已保存")
    except OSError as e:
        log.error("保存设置文件失败: %s", e)
        raise


def scan_project(project_dir: str) -> dict:
    """扫描项目，返回发现的文件扩展名、配置文件和包依赖。"""
    found_extensions = set()
    found_configs = set()
    found_deps = set()
    project = Path(project_dir).resolve()

    log.debug("扫描项目: %s", project)

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

    # 解析 package.json 依赖
    pkg_json = project / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                if key in pkg:
                    found_deps.update(pkg[key].keys())
        except (json.JSONDecodeError, KeyError, OSError) as e:
            log.warning("解析 package.json 失败: %s", e)

    # 解析 requirements.txt
    req_txt = project / "requirements.txt"
    if req_txt.exists():
        try:
            for line in req_txt.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    name = line.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()
                    if name:
                        found_deps.add(name)
        except OSError as e:
            log.warning("解析 requirements.txt 失败: %s", e)

    # 解析 pyproject.toml 中的依赖
    pyproject = project / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            in_deps = False
            for line in content.splitlines():
                if "dependencies" in line and "=" in line:
                    in_deps = True
                    continue
                if in_deps:
                    if line.strip().startswith("]"):
                        in_deps = False
                        continue
                    stripped = line.strip().strip('",').strip("',")
                    name = stripped.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()
                    if name and not name.startswith("#"):
                        found_deps.add(name)
        except OSError as e:
            log.warning("解析 pyproject.toml 失败: %s", e)

    # 解析 Gemfile
    gemfile = project / "Gemfile"
    if gemfile.exists():
        try:
            for line in gemfile.read_text().splitlines():
                line = line.strip()
                if line.startswith("gem "):
                    parts = line.split("'") if "'" in line else line.split('"')
                    if len(parts) >= 2:
                        found_deps.add(parts[1])
        except OSError as e:
            log.warning("解析 Gemfile 失败: %s", e)

    # 检查 glob 模式的配置文件
    glob_configs = set()
    try:
        for item in project.iterdir():
            if item.is_dir() and item.suffix in (".xcodeproj", ".xcworkspace"):
                glob_configs.add(f"*{item.suffix}")
            if item.is_file() and item.suffix in (".csproj", ".sln", ".gemspec"):
                glob_configs.add(f"*{item.suffix}")
    except OSError as e:
        log.warning("扫描项目根目录失败: %s", e)

    found_configs.update(glob_configs)

    log.debug(
        "扫描结果: %d 扩展名, %d 配置, %d 依赖",
        len(found_extensions), len(found_configs), len(found_deps),
    )
    return {
        "extensions": found_extensions,
        "configs": found_configs,
        "deps": found_deps,
    }


def match_config_pattern(pattern: str, found_configs: set) -> bool:
    """检查配置文件是否匹配（支持通配符和路径）。"""
    if "*" in pattern:
        return any(fnmatch.fnmatch(c, pattern) for c in found_configs)
    if "/" in pattern:
        return pattern.split("/")[-1] in found_configs
    return pattern in found_configs


def determine_plugins(project_dir: str, rules: dict) -> set:
    """根据项目扫描结果和规则，确定需要启用的插件。"""
    needed = set(rules["always_on"])
    scan = scan_project(project_dir)

    for rule in rules["conditional"]:
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
                if match_config_pattern(cfg, scan["configs"]):
                    matched = True
                    break

        if not matched:
            for dep in rule.get("package_deps", []):
                if dep in scan["deps"]:
                    matched = True
                    break

        if matched:
            needed.add(plugin)
            log.debug("规则匹配: %s", plugin)

    log.info("需要的插件: %d 个", len(needed))
    return needed


def apply_plugins(needed: set, dry_run: bool = False) -> dict:
    """更新 settings.json，返回变更摘要。"""
    settings = load_settings()
    enabled_plugins = settings.get("enabledPlugins", {})

    changes = {"enabled": [], "disabled": [], "unchanged": []}

    for key, current_value in enabled_plugins.items():
        plugin_name = key.replace(MARKETPLACE_SUFFIX, "")
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
        log.info(
            "已应用变更: 启用 %d, 禁用 %d",
            len(changes["enabled"]), len(changes["disabled"]),
        )

    return changes


def restore_all():
    """恢复所有插件为启用状态。"""
    settings = load_settings()
    count = 0
    for key in settings.get("enabledPlugins", {}):
        if not settings["enabledPlugins"][key]:
            settings["enabledPlugins"][key] = True
            count += 1
    save_settings(settings)
    log.info("已恢复 %d 个插件为启用状态", count)
    return count


def print_report(changes: dict, needed: set, dry_run: bool):
    """输出变更报告。"""
    prefix = "[预览] " if dry_run else ""

    active = len(changes["enabled"]) + len([p for p in changes["unchanged"]
               if p in needed])

    print(f"\n{prefix}插件配置报告")
    print("=" * 50)
    print(f"需要的插件: {len(needed)} 个")
    print(f"将启用: {active} 个")

    if changes["enabled"]:
        print(f"\n  新启用 ({len(changes['enabled'])}):")
        for p in sorted(changes["enabled"]):
            print(f"    + {p}")

    if changes["disabled"]:
        print(f"\n  将禁用 ({len(changes['disabled'])}):")
        for p in sorted(changes["disabled"]):
            print(f"    - {p}")

    total_plugins = len(changes["enabled"]) + len(changes["disabled"]) + len(changes["unchanged"])
    disabled_count = total_plugins - active
    print(f"\n  总计: {active} 启用 / {disabled_count} 禁用 / {total_plugins} 总数")

    if not dry_run and (changes["enabled"] or changes["disabled"]):
        print("\n  settings.json 已更新。重启 Claude Code session 生效。")
    elif dry_run and (changes["enabled"] or changes["disabled"]):
        print(f"\n  这是预览模式，未修改 settings.json。去掉 --dry 参数执行。")
    else:
        print("\n  无需变更。")


def main():
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--restore" in args:
        count = restore_all()
        print(f"已恢复 {count} 个插件为启用状态。")
        sys.exit(0)

    project_dir = args[0]
    dry_run = "--dry" in args

    if not os.path.isdir(project_dir):
        log.error("目录不存在: %s", project_dir)
        print(f"错误: 目录不存在: {project_dir}", file=sys.stderr)
        sys.exit(1)

    rules = load_rules()
    needed = determine_plugins(project_dir, rules)

    # 自动安装缺失的官方插件
    if not dry_run:
        from lib.registry import ensure_plugins_available
        installed = set(
            k.replace(MARKETPLACE_SUFFIX, "")
            for k in load_settings().get("enabledPlugins", {})
        )
        ensure_plugins_available("claude", needed, installed)

    changes = apply_plugins(needed, dry_run=dry_run)
    print_report(changes, needed, dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", __import__("traceback").format_exc())
        raise
