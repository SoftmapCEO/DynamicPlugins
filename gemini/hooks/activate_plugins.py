#!/usr/bin/env python3
"""
Gemini CLI SessionStart hook -- 自动启禁 extensions

扫描项目，根据 rules.json 启禁 extensions，输出 Gemini hook 格式 JSON。

环境变量:
  GEMINI_PROJECT_DIR - 当前项目目录
  GEMINI_SESSION_ID  - 会话 ID

输出格式:
  {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GEMINI_DIR = SCRIPT_DIR.parent
ROOT_DIR = GEMINI_DIR.parent
MANAGER = GEMINI_DIR / "plugin_manager.py"

sys.path.insert(0, str(ROOT_DIR))
from lib.logger import get_logger

log = get_logger("gemini_activate_plugins")


def main():
    project = os.environ.get("GEMINI_PROJECT_DIR", ".")
    session = os.environ.get("GEMINI_SESSION_ID", "")

    if not MANAGER.exists():
        log.warning("Manager not found: %s", MANAGER)
        return

    log.info("SessionStart hook triggered, project=%s, session=%s", project, session)

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

    log.debug("Manager output: %s", output)

    if "新启用" in output or "将禁用" in output:
        log.info("Extension changes detected")
        msg = "Extensions 已根据项目自动调整:\n" + output.strip()
        out = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": msg,
            }
        }
        print(json.dumps(out, ensure_ascii=False))
    else:
        log.info("No extension changes")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("Uncaught exception:\n%s", __import__("traceback").format_exc())
    sys.exit(0)
