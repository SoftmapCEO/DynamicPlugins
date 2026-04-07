#!/usr/bin/env python3
"""
Claude Code SessionStart hook -- 自动启禁插件

1. 扫描 CLAUDE_PROJECT_DIR 中的文件类型和依赖
2. 根据 rules.json 决定启用哪些插件
3. 更新 settings.json
4. 如果有变更，输出 additionalContext 通知模型
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CLAUDE_DIR = SCRIPT_DIR.parent
ROOT_DIR = CLAUDE_DIR.parent
MANAGER = CLAUDE_DIR / "plugin_manager.py"

sys.path.insert(0, str(ROOT_DIR))
from lib.logger import get_logger

log = get_logger("activate_plugins")


def main():
    project = os.environ.get("CLAUDE_PROJECT_DIR", ".")

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
            "插件管理器已根据当前项目自动调整插件配置:\n"
            + output.strip()
            + "\n\n请告知用户运行 /reload-plugins 或重启 session 以应用变更。"
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
