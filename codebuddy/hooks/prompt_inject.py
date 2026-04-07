#!/usr/bin/env python3
"""
CodeBuddy CLI UserPromptSubmit hook -- 插件热注入

Stdin: {"prompt": "...", "session_id": "...", "cwd": "..."}
Stdout: {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}
"""

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib.logger import get_logger

log = get_logger("codebuddy_prompt_inject")

CACHE_FILE = Path(__file__).resolve().parent.parent / "cache" / "skills_index.json"
SIGNAL_FILE = Path(tempfile.gettempdir()) / "codebuddy-plugin-hotload-signal.json"
MAX_SKILLS = 2
MIN_MATCH_SCORE = 3

PLUGIN_NAME_STOPWORDS = {
    "data", "code", "dev", "app", "test", "set", "run", "get",
    "add", "use", "new", "the", "for", "and", "not", "but",
    "all", "can", "has", "its", "let", "may", "own", "say",
}


def load_index():
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("加载缓存失败: %s", e)
        return None


def extract_prompt_words(prompt: str) -> set:
    text = prompt.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    words = set(text.split())
    words.update(re.sub(r"[^\w\s]", " ", prompt).split())
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "shall", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "this", "that", "these", "those", "it", "its", "and", "or",
        "but", "not", "if", "then", "else", "when", "where", "how",
        "what", "which", "who", "why", "all", "some", "any", "no",
        "so", "than", "too", "very", "just", "use", "using", "used",
        "your", "you", "they", "them", "their", "about", "need",
        "want", "like", "make", "get", "set", "run", "add", "new",
        "one", "two", "also", "been", "more", "most", "only", "each",
        "now", "way", "own", "here", "there",
    }
    return {w for w in words if len(w) >= 3 and w.lower() not in stopwords}


def find_matching_skills(prompt: str, index: dict) -> list:
    prompt_words = extract_prompt_words(prompt)
    inverted = index.get("i", {})
    skills_table = index.get("s", [])
    base = index.get("b", "")

    hit_counts = {}
    for word in prompt_words:
        wl = word.lower()
        sids = inverted.get(wl)
        if sids:
            for sid in sids:
                hit_counts[sid] = hit_counts.get(sid, 0) + 1

    if not hit_counts:
        return []

    candidates = []
    for sid, kw_hits in hit_counts.items():
        if sid >= len(skills_table):
            continue
        entry = skills_table[sid]
        plugin_name, skill_name, rel_path = entry[0], entry[1], entry[2]
        summary = entry[3] if len(entry) > 3 else ""

        score = kw_hits * 2
        plugin_lower = plugin_name.lower().replace("-", " ").replace("_", " ")
        plugin_parts = set(plugin_lower.split())
        meaningful_parts = plugin_parts - PLUGIN_NAME_STOPWORDS
        if meaningful_parts:
            for word in prompt_words:
                wl = word.lower()
                if wl == plugin_lower.replace(" ", ""):
                    score += 5
                    break
                if len(wl) >= 4:
                    for part in meaningful_parts:
                        if len(part) >= 4 and (wl == part or wl.startswith(part) or part.startswith(wl)):
                            score += 4
                            break

        if score >= MIN_MATCH_SCORE:
            full_path = os.path.join(base, rel_path) if base else rel_path
            candidates.append({
                "plugin": plugin_name, "skill": skill_name,
                "score": score, "file": full_path, "summary": summary,
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:MAX_SKILLS]


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        return

    if not raw or not raw.strip():
        return

    try:
        input_data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    prompt = input_data.get("prompt") or input_data.get("user_prompt") or ""
    if not prompt:
        return

    # 信号文件
    if SIGNAL_FILE.exists():
        try:
            signal = json.loads(SIGNAL_FILE.read_text())
            SIGNAL_FILE.unlink(missing_ok=True)
            out = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": f"[CodeBuddy 插件管理] {signal.get('action', '')}: {signal.get('details', '')}",
                }
            }
            print(json.dumps(out, ensure_ascii=False))
            return
        except (json.JSONDecodeError, OSError):
            pass

    index = load_index()
    if not index:
        return

    matches = find_matching_skills(prompt, index)
    if not matches:
        return

    parts = []
    for m in matches:
        desc = f": {m['summary']}" if m.get("summary") else ""
        parts.append(f"- {m['plugin']}:{m['skill']}{desc}\n  File: {m['file']}")

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "[Skill hint] The following disabled plugin skills match your query. "
                "Read the file if needed:\n" + "\n".join(parts)
            ),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    log.info("注入摘要 %d 个 skill", len(parts))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", traceback.format_exc())
    sys.exit(0)
