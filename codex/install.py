#!/usr/bin/env python3
"""
Codex CLI 动态插件安装脚本

将 hook 配置注入 ~/.codex/config.toml
Codex 的 hook 系统是实验性的，需要启用 codex_hooks feature flag

用法: python3 install.py
      python install.py      (Windows)
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = Path.home() / ".codex" / "config.toml"
PYTHON = sys.executable


def main():
    print("=== Codex CLI Dynamic Plugins Install ===\n")

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "cache").mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        print(f"  Creating {CONFIG_FILE} ...")
        CONFIG_FILE.write_text("")

    content = CONFIG_FILE.read_text()

    inject_script = str(SCRIPT_DIR / "hooks" / "prompt_inject.py")

    if inject_script not in content and "prompt_inject.py" not in content:
        addition = f"""
# DynamicPlugins: dynamic skill injection
# notify = ["{PYTHON} {inject_script}"]

[features]
# Enable experimental hooks support
# codex_hooks = true
"""
        CONFIG_FILE.write_text(content.rstrip() + "\n" + addition)
        print(f"  + Hook config added to {CONFIG_FILE}")
        print("  Note: notify and codex_hooks are commented out, uncomment to enable")
    else:
        print("  Hook config already exists, skipped")

    # Build cache
    print("\nBuilding skills cache...")
    subprocess.run([sys.executable, str(SCRIPT_DIR / "build_cache.py")], check=False)

    print(f"""
Installation complete!

Usage:
  1. Uncomment notify in {CONFIG_FILE}
  2. Or run manually:
     echo '{{"user_prompt": "..."}}' | {PYTHON} {inject_script}
  3. Rebuild cache: {PYTHON} {SCRIPT_DIR / 'build_cache.py'}
""")


if __name__ == "__main__":
    main()
