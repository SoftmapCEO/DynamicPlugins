#!/usr/bin/env python3
"""
Kimi Code CLI SessionStart hook -- 自动启禁 plugins

扫描项目，根据 rules.json 启禁 plugins，输出 JSON。

环境变量:
  KIMI_WORK_DIR - 工作目录 (Kimi 内置)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
KIMI_DIR = SCRIPT_DIR.parent
ROOT_DIR = KIMI_DIR.parent
MANAGER = KIMI_DIR / "plugin_manager.py"

sys.path.insert(0, str(ROOT_DIR))
from lib.logger import get_logger

log = get_logger("kimi_activate_plugins")


def main():
    project = os.environ.get("KIMI_WORK_DIR", os.getcwd())

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

    log.debug("Manager output: %s", output)

    if "新启用" in output or "将禁用" in output:
        log.info("Plugin changes detected")
        msg = (
            "插件管理器已根据当前项目自动调整 Kimi plugins:\n"
            + output.strip()
        )
        print(json.dumps({"additionalContext": msg}, ensure_ascii=False))
    else:
        log.info("No plugin changes")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("Uncaught exception:\n%s", __import__("traceback").format_exc())
    sys.exit(0)
