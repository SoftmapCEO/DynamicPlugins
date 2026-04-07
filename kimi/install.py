#!/usr/bin/env python3
"""
Kimi Code CLI 动态插件安装脚本

将 hook 配置注入 ~/.kimi/config.toml
支持 SessionStart (自动启禁 plugins) 和 PreToolUse (关键词注入)

Kimi hooks 使用 [[hooks]] TOML 数组格式:
  [[hooks]]
  event = "SessionStart"
  command = "python3 /path/to/script.py"
  timeout = 30

用法: python3 install.py
      python install.py      (Windows)
"""

import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = Path.home() / ".kimi" / "config.toml"
PYTHON = sys.executable


def _hook_exists(content: str, script_name: str) -> bool:
    """检查 config.toml 中是否已有指向某脚本的 hook。"""
    return script_name in content


def _append_hook(content: str, event: str, command: str, timeout: int = 30) -> str:
    """追加一个 [[hooks]] 段到 TOML 内容末尾。"""
    block = f'''
[[hooks]]
event = "{event}"
command = "{command}"
timeout = {timeout}
'''
    return content.rstrip() + "\n" + block


def main():
    print("=== Kimi Code CLI Dynamic Plugins Install ===\n")

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "cache").mkdir(parents=True, exist_ok=True)

    # Build cache
    print("Building skills cache...")
    subprocess.run([sys.executable, str(SCRIPT_DIR / "build_cache.py")], check=False)
    print()

    if not CONFIG_FILE.exists():
        print(f"  Creating {CONFIG_FILE} ...")
        CONFIG_FILE.write_text("")

    content = CONFIG_FILE.read_text()
    modified = False

    # SessionStart hook
    activate_script = str(SCRIPT_DIR / "hooks" / "activate_plugins.py")
    if not _hook_exists(content, "activate_plugins.py"):
        content = _append_hook(content, "SessionStart", f'"{PYTHON}" "{activate_script}"', 30)
        modified = True
        print("  + SessionStart hook added")
    else:
        print("  SessionStart hook exists, skipped")

    # PreToolUse hook (prompt injection)
    inject_script = str(SCRIPT_DIR / "hooks" / "prompt_inject.py")
    if not _hook_exists(content, "prompt_inject.py"):
        content = _append_hook(content, "PreToolUse", f'"{PYTHON}" "{inject_script}"', 10)
        modified = True
        print("  + PreToolUse hook added")
    else:
        print("  PreToolUse hook exists, skipped")

    if modified:
        CONFIG_FILE.write_text(content)
        print(f"\n  Updated {CONFIG_FILE}")
    else:
        print(f"\n  {CONFIG_FILE} unchanged")

    print(f"""
Installation complete!

Hooks:
  SessionStart:  auto enable/disable plugins per project
  PreToolUse:    keyword matching, inject relevant skill summaries

Usage:
  Preview:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir> --dry
  Apply:         {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir>
  Restore:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} --restore
  Build cache:   {PYTHON} {SCRIPT_DIR / 'build_cache.py'}

Verify hooks:  Run /hooks inside a Kimi session
""")


if __name__ == "__main__":
    main()
