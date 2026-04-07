#!/usr/bin/env python3
"""
CodeBuddy CLI 动态插件安装脚本 (腾讯云 CodeBuddy Code)

将 hook 配置注入 ~/.codebuddy/settings.json
支持 SessionStart + UserPromptSubmit (9 种 hook 事件)

用法: python3 install.py
      python install.py      (Windows)
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = Path.home() / ".codebuddy" / "settings.json"
PYTHON = sys.executable


def _hook_exists(hooks_config: dict, event: str, script_name: str) -> bool:
    for group in hooks_config.get(event, []):
        for hook in group.get("hooks", []):
            if script_name in hook.get("command", ""):
                return True
    return False


def _add_hook(hooks_config: dict, event: str, command: str, timeout: int = 60):
    hook_entry = {"type": "command", "command": command, "timeout": timeout}
    if event not in hooks_config:
        hooks_config[event] = []
    hooks_config[event].append({"hooks": [hook_entry]})


def main():
    print("=== CodeBuddy CLI Dynamic Plugins Install ===\n")

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "cache").mkdir(parents=True, exist_ok=True)

    print("Building skills cache...")
    subprocess.run([sys.executable, str(SCRIPT_DIR / "build_cache.py")], check=False)
    print()

    if not SETTINGS_FILE.exists():
        print(f"  Creating {SETTINGS_FILE} ...")
        SETTINGS_FILE.write_text("{}\n")

    with open(SETTINGS_FILE, encoding="utf-8") as f:
        settings = json.load(f)

    hooks = settings.setdefault("hooks", {})
    modified = False

    # SessionStart hook
    activate_script = str(SCRIPT_DIR / "hooks" / "activate_plugins.py")
    if not _hook_exists(hooks, "SessionStart", "activate_plugins.py"):
        _add_hook(hooks, "SessionStart", f'"{PYTHON}" "{activate_script}"', 30)
        modified = True
        print("  + SessionStart hook added")
    else:
        print("  SessionStart hook exists, skipped")

    # UserPromptSubmit hook
    inject_script = str(SCRIPT_DIR / "hooks" / "prompt_inject.py")
    if not _hook_exists(hooks, "UserPromptSubmit", "prompt_inject.py"):
        _add_hook(hooks, "UserPromptSubmit", f'"{PYTHON}" "{inject_script}"', 10)
        modified = True
        print("  + UserPromptSubmit hook added")
    else:
        print("  UserPromptSubmit hook exists, skipped")

    if modified:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\n  Updated {SETTINGS_FILE}")
    else:
        print(f"\n  {SETTINGS_FILE} unchanged")

    print(f"""
Installation complete!

Hooks:
  SessionStart:       auto enable/disable plugins per project
  UserPromptSubmit:   keyword matching, inject relevant skill summaries

Usage:
  Preview:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir> --dry
  Apply:         {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir>
  Restore:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} --restore
  Build cache:   {PYTHON} {SCRIPT_DIR / 'build_cache.py'}
""")


if __name__ == "__main__":
    main()
