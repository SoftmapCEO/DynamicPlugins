#!/usr/bin/env python3
"""
Qwen Code CLI 动态插件安装脚本

将 hook 配置注入 ~/.qwen/settings.json
支持 SessionStart (自动启禁 extensions) 和 UserPromptSubmit (关键词注入)

Qwen hooks 格式:
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "..."}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "..."}]}]
  }

用法: python3 install.py
      python install.py      (Windows)
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = Path.home() / ".qwen" / "settings.json"
PYTHON = sys.executable


def _hook_exists(hooks_config: dict, event: str, script_name: str) -> bool:
    """检查某事件下是否已有指向某脚本的 hook。"""
    for group in hooks_config.get(event, []):
        for hook in group.get("hooks", []):
            if script_name in hook.get("command", ""):
                return True
    return False


def _add_hook(hooks_config: dict, event: str, command: str, timeout: int = 30000):
    """添加一个 hook 到事件组。"""
    hook_entry = {
        "type": "command",
        "command": command,
        "timeout": timeout,
    }
    if event not in hooks_config:
        hooks_config[event] = []
    hooks_config[event].append({"hooks": [hook_entry]})


def main():
    print("=== Qwen Code CLI Dynamic Plugins Install ===\n")

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "cache").mkdir(parents=True, exist_ok=True)

    # Build cache
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
        _add_hook(hooks, "SessionStart", f'"{PYTHON}" "{activate_script}"', 30000)
        modified = True
        print("  + SessionStart hook added")
    else:
        print("  SessionStart hook exists, skipped")

    # UserPromptSubmit hook
    inject_script = str(SCRIPT_DIR / "hooks" / "prompt_inject.py")
    if not _hook_exists(hooks, "UserPromptSubmit", "prompt_inject.py"):
        _add_hook(hooks, "UserPromptSubmit", f'"{PYTHON}" "{inject_script}"', 10000)
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
  SessionStart:       auto enable/disable extensions per project
  UserPromptSubmit:   keyword matching, inject relevant skill summaries

Usage:
  Preview:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir> --dry
  Apply:         {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir>
  Restore:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} --restore
  Build cache:   {PYTHON} {SCRIPT_DIR / 'build_cache.py'}
""")


if __name__ == "__main__":
    main()
