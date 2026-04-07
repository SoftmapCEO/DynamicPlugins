#!/usr/bin/env python3
"""
Claude Code 动态插件安装脚本

将 hook 配置注入 ~/.claude/settings.json
支持 SessionStart (自动启禁插件) 和 UserPromptSubmit (关键词注入)

用法: python3 install.py
      python install.py      (Windows)
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"
PYTHON = sys.executable


def main():
    print("=== Claude Code Dynamic Plugins Install ===\n")

    # 确保配置目录和缓存目录存在
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "cache").mkdir(parents=True, exist_ok=True)

    # 创建默认 settings.json
    if not SETTINGS_FILE.exists():
        print(f"  Creating {SETTINGS_FILE} ...")
        SETTINGS_FILE.write_text("{}\n")

    with open(SETTINGS_FILE, encoding="utf-8") as f:
        settings = json.load(f)

    hooks = settings.setdefault("hooks", {})
    modified = False

    # SessionStart hook
    activate_script = str(SCRIPT_DIR / "hooks" / "activate_plugins.py")
    session_cmd = f'"{PYTHON}" "{activate_script}"'
    session_hook = {"type": "command", "command": session_cmd}
    session_hooks = hooks.get("SessionStart", [])
    existing = [h.get("command", "") if isinstance(h, dict) else h for h in session_hooks]
    if session_cmd not in existing:
        session_hooks.append(session_hook)
        hooks["SessionStart"] = session_hooks
        modified = True
        print("  + SessionStart hook added")
    else:
        print("  SessionStart hook exists, skipped")

    # UserPromptSubmit hook
    inject_script = str(SCRIPT_DIR / "hooks" / "prompt_inject.py")
    prompt_cmd = f'"{PYTHON}" "{inject_script}"'
    prompt_hook = {"type": "command", "command": prompt_cmd}
    prompt_hooks = hooks.get("UserPromptSubmit", [])
    existing = [h.get("command", "") if isinstance(h, dict) else h for h in prompt_hooks]
    if prompt_cmd not in existing:
        prompt_hooks.append(prompt_hook)
        hooks["UserPromptSubmit"] = prompt_hooks
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
  SessionStart:      auto enable/disable plugins per project
  UserPromptSubmit:  keyword matching, inject relevant skill summaries

Usage:
  Preview:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir> --dry
  Apply:         {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir>
  Restore:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} --restore
  Build cache:   {PYTHON} {SCRIPT_DIR / 'build_cache.py'}

Note: Run plugin_manager.py on your project first, then build_cache.py
      to build the keyword index for disabled plugins.
""")


if __name__ == "__main__":
    main()
