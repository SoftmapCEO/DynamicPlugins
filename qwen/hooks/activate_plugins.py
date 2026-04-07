#!/usr/bin/env python3
"""
Qwen Code CLI SessionStart hook -- 自动启禁 extensions

扫描项目，根据 rules.json 启禁 extensions，输出 JSON。

Qwen hook 输入 (stdin): {"session_id", "cwd", "hook_event_name", ...}
Qwen hook 输出 (stdout): {"hookSpecificOutput": {"additionalContext": "..."}}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
QWEN_DIR = SCRIPT_DIR.parent
ROOT_DIR = QWEN_DIR.parent
MANAGER = QWEN_DIR / "plugin_manager.py"

sys.path.insert(0, str(ROOT_DIR))
from lib.logger import get_logger

log = get_logger("qwen_activate_plugins")


def main():
    # 尝试从 stdin 获取 cwd，或用环境变量
    project = os.getcwd()
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

    log.debug("Manager output: %s", output)

    if "新启用" in output or "将禁用" in output:
        log.info("Extension changes detected")
        out = {
            "hookSpecificOutput": {
                "additionalContext": (
                    "Extensions 已根据项目自动调整:\n" + output.strip()
                ),
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
