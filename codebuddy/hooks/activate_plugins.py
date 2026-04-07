#!/usr/bin/env python3
"""
CodeBuddy CLI SessionStart hook -- 自动启禁插件

环境变量: CODEBUDDY_PROJECT_DIR
Stdin: {"session_id", "cwd", "source", ...}
Stdout: {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CB_DIR = SCRIPT_DIR.parent
ROOT_DIR = CB_DIR.parent
MANAGER = CB_DIR / "plugin_manager.py"

sys.path.insert(0, str(ROOT_DIR))
from lib.logger import get_logger

log = get_logger("codebuddy_activate_plugins")


def main():
    project = os.environ.get("CODEBUDDY_PROJECT_DIR", os.getcwd())
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            data = json.loads(raw)
            project = data.get("cwd", project)
    except Exception:
        pass

    if not MANAGER.exists():
        log.warning("Manager not found: %s", MANAGER)
        return

    log.info("SessionStart hook triggered, project=%s", project)

    try:
        result = subprocess.run(
            [sys.executable, str(MANAGER), project],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        log.error("Manager timed out")
        return

    output = result.stdout + result.stderr
    if result.returncode != 0:
        log.error("Manager failed (exit=%d): %s", result.returncode, output)
        return

    if "新启用" in output or "将禁用" in output:
        log.info("Plugin changes detected")
        out = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "插件管理器已自动调整:\n" + output.strip(),
            }
        }
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("Uncaught exception:\n%s", __import__("traceback").format_exc())
    sys.exit(0)
