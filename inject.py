#!/usr/bin/env python3
"""
统一关键词注入入口 (hook 调用)

用法: echo '{"prompt":"..."}' | python3 inject.py --cli claude
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cli_config import get_config
from lib.core import find_matching_skills, format_inject_output
from lib.logger import get_logger

log = get_logger("inject")


def main():
    args = sys.argv[1:]
    cli = None
    for i, a in enumerate(args):
        if a == "--cli" and i + 1 < len(args):
            cli = args[i + 1]

    if not cli:
        return

    cfg = get_config(cli)
    cache_file = cfg["cache_dir"] / "skills_index.json"

    # 读取 stdin
    try:
        raw = sys.stdin.read()
    except Exception:
        return
    if not raw or not raw.strip():
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    prompt = data.get("prompt") or data.get("user_prompt") or data.get("message") or ""
    if not prompt:
        return

    # 信号文件检查
    signal_file = Path(tempfile.gettempdir()) / f"{cli}-plugin-hotload-signal.json"
    if signal_file.exists():
        try:
            signal = json.loads(signal_file.read_text(encoding="utf-8"))
            signal_file.unlink(missing_ok=True)
            text = f"[Plugin manager] {signal.get('action', '')}: {signal.get('details', '')}"
            out_type = cfg.get("hook_output", "additionalContext")
            if out_type == "hookSpecificOutput":
                event = cfg["hooks"].get("prompt_submit", "UserPromptSubmit")
                print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, ensure_ascii=False))
            else:
                print(json.dumps({"additionalContext": text}, ensure_ascii=False))
            return
        except (json.JSONDecodeError, OSError):
            pass

    # 加载缓存
    if not cache_file.exists():
        return
    try:
        with open(cache_file, encoding="utf-8") as f:
            index = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    matches = find_matching_skills(prompt, index)
    if not matches:
        return

    result = format_inject_output(matches, cfg)
    print(json.dumps(result, ensure_ascii=False))
    log.info("[%s] injected %d skills", cli, len(matches))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
