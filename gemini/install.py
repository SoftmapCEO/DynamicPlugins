#!/usr/bin/env python3
"""
Gemini CLI 动态插件安装脚本

将 hook 配置注入 ~/.gemini/settings.json
Gemini 支持 SessionStart 和 BeforeAgent 生命周期 hooks

用法: python3 install.py
      python install.py      (Windows)
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = Path.home() / ".gemini" / "settings.json"
PYTHON = sys.executable


def main():
    print("=== Gemini CLI Dynamic Plugins Install ===\n")

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
    session_cmd = f'"{PYTHON}" "{activate_script}"'
    session_hooks = hooks.get("SessionStart", [])
    if session_cmd not in session_hooks:
        session_hooks.append(session_cmd)
        hooks["SessionStart"] = session_hooks
        modified = True
        print("  + SessionStart hook added")
    else:
        print("  SessionStart hook exists, skipped")

    # BeforeAgent hook
    inject_script = str(SCRIPT_DIR / "hooks" / "prompt_inject.py")
    agent_cmd = f'"{PYTHON}" "{inject_script}"'
    agent_hooks = hooks.get("BeforeAgent", [])
    if agent_cmd not in agent_hooks:
        agent_hooks.append(agent_cmd)
        hooks["BeforeAgent"] = agent_hooks
        modified = True
        print("  + BeforeAgent hook added")
    else:
        print("  BeforeAgent hook exists, skipped")

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
  SessionStart:  auto enable/disable extensions per project
  BeforeAgent:   keyword matching, inject relevant skill summaries

Usage:
  Preview:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir> --dry
  Apply:         {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} <project_dir>
  Restore:       {PYTHON} {SCRIPT_DIR / 'plugin_manager.py'} --restore
  Build cache:   {PYTHON} {SCRIPT_DIR / 'build_cache.py'}
""")


if __name__ == "__main__":
    main()
