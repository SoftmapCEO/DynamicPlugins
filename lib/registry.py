"""
DynamicPlugins 官方渠道注册表

统一管理各 CLI 工具的官方插件渠道验证、自动安装和缓存重建。

设计原则:
  1. 只允许 rules.json 中声明的官方插件
  2. 缺失的插件自动通过 CLI 原生包管理器安装
  3. 安装后自动重建关键词缓存

支持的安装方式:
  - marketplace: CLI 内置插件市场 (Claude, CodeBuddy)
  - cli_extensions: CLI 扩展命令 (Gemini, Qwen)
  - cli_plugin: CLI 插件命令 (Kimi)
  - skill_stub: 无包管理器，生成 SKILL.md 存根 (Codex, Qoder)
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .logger import get_logger

log = get_logger("registry")

ROOT_DIR = Path(__file__).resolve().parent.parent
RULES_FILE = ROOT_DIR / "rules.json"

# 每个 CLI 的官方渠道配置
CLI_CONFIGS = {
    "claude": {
        "type": "marketplace",
        "install_cmd": ["claude", "plugin", "install", "{name}"],
        "cache_dir": Path.home() / ".claude" / "plugins" / "cache" / "claude-plugins-official",
        "build_cache": ROOT_DIR / "claude" / "build_cache.py",
    },
    "codebuddy": {
        "type": "marketplace",
        "install_cmd": ["codebuddy", "plugin", "install", "{name}"],
        "cache_dir": Path.home() / ".codebuddy" / "plugins" / "cache",
        "build_cache": ROOT_DIR / "codebuddy" / "build_cache.py",
    },
    "gemini": {
        "type": "cli_extensions",
        "install_cmd": ["gemini", "extensions", "install", "{name}"],
        "cache_dir": Path.home() / ".gemini" / "extensions",
        "build_cache": ROOT_DIR / "gemini" / "build_cache.py",
    },
    "qwen": {
        "type": "cli_extensions",
        "install_cmd": ["qwen", "extensions", "install", "{name}"],
        "cache_dir": Path.home() / ".qwen" / "extensions",
        "build_cache": ROOT_DIR / "qwen" / "build_cache.py",
    },
    "kimi": {
        "type": "cli_plugin",
        "install_cmd": ["kimi", "plugin", "install", "{name}"],
        "cache_dir": Path.home() / ".kimi" / "plugins",
        "build_cache": ROOT_DIR / "kimi" / "build_cache.py",
    },
    "codex": {
        "type": "skill_stub",
        "skill_dirs": [Path.home() / ".codex" / "skills", Path.home() / ".agents" / "skills"],
        "build_cache": ROOT_DIR / "codex" / "build_cache.py",
    },
    "qoder": {
        "type": "skill_stub",
        "skill_dirs": [Path.home() / ".qoder" / "skills"],
        "build_cache": ROOT_DIR / "qoder" / "build_cache.py",
    },
}


def _load_rules() -> dict:
    try:
        with open(RULES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"always_on": [], "conditional": []}


def _get_official_set() -> set:
    """返回 rules.json 中声明的所有官方插件名（小写）。"""
    rules = _load_rules()
    names = set(n.lower() for n in rules.get("always_on", []))
    for r in rules.get("conditional", []):
        names.add(r["plugin"].lower())
    return names


def is_official(plugin_name: str) -> bool:
    """检查插件是否在 rules.json 中声明（即官方渠道插件）。"""
    return plugin_name.lower() in _get_official_set()


def auto_install(cli: str, plugin_name: str) -> bool:
    """通过 CLI 原生包管理器自动安装一个插件。

    返回 True 表示安装成功或已存在。
    """
    config = CLI_CONFIGS.get(cli)
    if not config:
        log.warning("未知 CLI: %s", cli)
        return False

    if not is_official(plugin_name):
        log.warning("拒绝安装非官方插件: %s", plugin_name)
        return False

    install_type = config["type"]

    if install_type in ("marketplace", "cli_extensions", "cli_plugin"):
        return _install_via_cli(config, plugin_name)
    elif install_type == "skill_stub":
        return _create_skill_stub(config, plugin_name)

    return False


def _install_via_cli(config: dict, plugin_name: str) -> bool:
    """通过 CLI 命令安装插件。"""
    cmd_template = config["install_cmd"]
    cmd = [part.replace("{name}", plugin_name) for part in cmd_template]

    exe = shutil.which(cmd[0])
    if not exe:
        log.warning("CLI 不可用: %s (请确保已安装并在 PATH 中)", cmd[0])
        return False

    log.info("自动安装: %s -> %s", plugin_name, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log.info("安装成功: %s", plugin_name)
            return True
        else:
            log.warning("安装失败 (exit=%d): %s", result.returncode, result.stderr[:200])
            return False
    except subprocess.TimeoutExpired:
        log.error("安装超时: %s", plugin_name)
        return False
    except FileNotFoundError:
        log.warning("CLI 命令未找到: %s", cmd[0])
        return False


def _create_skill_stub(config: dict, plugin_name: str) -> bool:
    """为无包管理器的 CLI 创建 SKILL.md 存根。"""
    rules = _load_rules()
    description = ""
    for r in rules.get("conditional", []):
        if r["plugin"].lower() == plugin_name.lower():
            description = r.get("_description", f"Auto-provisioned skill for {plugin_name}")
            break

    if not description:
        description = f"Auto-provisioned skill for {plugin_name}"

    skill_dirs = config.get("skill_dirs", [])
    if not skill_dirs:
        return False

    target_dir = skill_dirs[0] / plugin_name
    skill_file = target_dir / "SKILL.md"

    if skill_file.exists():
        return True  # 已存在

    target_dir.mkdir(parents=True, exist_ok=True)
    content = f"""---
name: {plugin_name}
description: >
  {description}
---

# {plugin_name}

This skill was auto-provisioned by DynamicPlugins.
It provides context hints for {plugin_name}-related tasks.
"""
    skill_file.write_text(content, encoding="utf-8")
    log.info("创建 skill 存根: %s", skill_file)
    return True


def ensure_plugins_available(cli: str, needed: set, installed: set) -> set:
    """确保所需插件都已安装。

    对 needed 中存在但 installed 中缺失的官方插件，自动安装。
    返回新安装的插件集合。
    """
    missing = set()
    for name in needed:
        if name.lower() not in {n.lower() for n in installed}:
            missing.add(name)

    if not missing:
        return set()

    newly_installed = set()
    for name in sorted(missing):
        if is_official(name):
            log.info("检测到缺失的官方插件: %s, 尝试自动安装...", name)
            if auto_install(cli, name):
                newly_installed.add(name)
        else:
            log.debug("跳过非官方插件: %s", name)

    if newly_installed:
        log.info("新安装 %d 个插件: %s", len(newly_installed), sorted(newly_installed))
        auto_rebuild_cache(cli)

    return newly_installed


def auto_rebuild_cache(cli: str):
    """安装后自动重建关键词缓存。"""
    config = CLI_CONFIGS.get(cli)
    if not config:
        return

    build_script = config.get("build_cache")
    if not build_script or not build_script.exists():
        return

    log.info("重建缓存: %s", build_script)
    try:
        subprocess.run(
            [sys.executable, str(build_script)],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning("缓存重建失败: %s", e)
