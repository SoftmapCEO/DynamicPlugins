#!/usr/bin/env python3
"""
UserPromptSubmit hook -- 插件热注入

在用户发送消息时，分析消息内容，匹配禁用插件的 skill，
通过 additionalContext 将 skill 内容注入当前对话。

工作流:
  用户消息 -> 提取关键词 -> 匹配禁用插件的 skills -> 读取 SKILL.md -> 注入

限制:
  - 注入内容有大小上限（默认 16KB），避免过度消耗 token
  - 最多同时注入 2 个 skill
  - 只匹配禁用插件的 skill（已启用的无需注入）
"""

import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

# -- 日志初始化（在所有业务逻辑之前） --
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from lib.logger import get_logger

log = get_logger("prompt_inject")

# -- 常量 --
CACHE_FILE = Path(__file__).parent.parent / "cache" / "skills_index.json"
SIGNAL_FILE = Path(tempfile.gettempdir()) / "claude-plugin-hotload-signal.json"
MAX_SKILLS = 2
MIN_MATCH_SCORE = 3  # 至少 3 分才注入（提高阈值减少误报）

# 插件名匹配的排除词（这些词太通用，会导致误匹配插件名）
PLUGIN_NAME_STOPWORDS = {
    "data", "code", "dev", "app", "test", "set", "run", "get",
    "add", "use", "new", "the", "for", "and", "not", "but",
    "all", "can", "has", "its", "let", "may", "own", "say",
    "she", "too", "her", "was", "one", "our", "out", "are",
}


def load_index():
    """加载反向索引缓存。

    v2 格式:
      b: 路径公共前缀
      s: [[plugin, skill, relative_path], ...]
      i: {keyword: [skill_id, ...]}
    """
    if not CACHE_FILE.exists():
        log.debug("缓存文件不存在: %s", CACHE_FILE)
        return None

    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            index = json.load(f)

        log.debug("加载缓存成功: %d skills, %d 关键词", len(index.get("s", [])), len(index.get("i", {})))
        return index
    except (json.JSONDecodeError, OSError) as e:
        log.error("加载缓存失败: %s", e)
        return None


def extract_prompt_words(prompt: str) -> set:
    """从用户消息中提取有效词汇。"""
    text = prompt.lower()
    # 连字符也作为分隔符，与 build_cache 保持一致
    text = re.sub(r"[^\w\s]", " ", text)
    words = set(text.split())
    # 也保留原始大小写的词（匹配如 MongoDB 等大小写敏感的名称）
    words.update(re.sub(r"[^\w\s]", " ", prompt).split())
    # 过滤过短的词和常见停用词
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
    """用反向索引查找匹配的 skills。

    v2 格式:
      b: 路径公共前缀
      s: [[plugin, skill, relative_path], ...]
      i: {keyword: [skill_id, ...]}

    查询流程: 提取词汇 -> 查反向索引得到 skill_id -> 按命中次数计分 -> 加插件名匹配分
    """
    prompt_words = extract_prompt_words(prompt)
    log.debug("提取词汇: %s", sorted(prompt_words)[:20])

    inverted = index.get("i", {})
    skills_table = index.get("s", [])
    base = index.get("b", "")

    # 通过反向索引收集命中的 skill_id 及关键词命中次数
    hit_counts = {}  # skill_id -> keyword hit count
    for word in prompt_words:
        wl = word.lower()
        skill_ids = inverted.get(wl)
        if skill_ids:
            for sid in skill_ids:
                hit_counts[sid] = hit_counts.get(sid, 0) + 1

    if not hit_counts:
        log.debug("无关键词命中")
        return []

    # 计算最终分数
    candidates = []
    for sid, kw_hits in hit_counts.items():
        if sid >= len(skills_table):
            continue
        entry = skills_table[sid]
        plugin_name, skill_name, rel_path = entry[0], entry[1], entry[2]
        summary = entry[3] if len(entry) > 3 else ""

        score = kw_hits * 2  # 关键词命中分

        # 插件名匹配加分
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
                "plugin": plugin_name,
                "skill": skill_name,
                "score": score,
                "file": full_path,
                "summary": summary,
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[:MAX_SKILLS]

    if top:
        log.info(
            "匹配结果: %s",
            ", ".join(f"{c['plugin']}:{c['skill']}(score={c['score']})" for c in top),
        )
    else:
        log.debug("无匹配 skill (命中 %d 个但分数不足)", len(hit_counts))

    return top



def check_api_signal() :
    """检查方案 C 的 API 信号文件。"""
    if not SIGNAL_FILE.exists():
        return None

    try:
        signal = json.loads(SIGNAL_FILE.read_text())
        SIGNAL_FILE.unlink(missing_ok=True)
        log.info("消费 API 信号: %s", signal.get("action", "unknown"))
        return signal
    except (json.JSONDecodeError, OSError) as e:
        log.error("读取信号文件失败: %s", e)
        try:
            SIGNAL_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    return None


def main():
    # 读取 stdin 输入
    try:
        raw = sys.stdin.read()
    except Exception as e:
        log.error("读取 stdin 失败: %s", e)
        return

    if not raw or not raw.strip():
        log.debug("stdin 为空，跳过")
        return

    try:
        input_data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        log.error("解析 stdin JSON 失败: raw=%r, error=%s", raw[:200], e)
        return

    # Claude Code 传入的字段名
    prompt = (
        input_data.get("user_prompt")
        or input_data.get("prompt")
        or input_data.get("message")
        or ""
    )

    if not prompt:
        log.debug("未找到 prompt 字段, keys=%s", list(input_data.keys()))
        return

    log.debug("收到 prompt: %s", prompt[:100])
    result = {}

    # 检查 API 信号
    signal = check_api_signal()
    if signal:
        action = signal.get("action", "")
        details = signal.get("details", "")
        result["additionalContext"] = (
            f"[插件管理器 API] {action}: {details}\n"
            f"请告知用户运行 /reload-plugins 以应用插件变更。"
        )
        print(json.dumps(result, ensure_ascii=False))
        return

    # 匹配禁用插件的 skill
    index = load_index()
    if not index:
        return

    matches = find_matching_skills(prompt, index)
    if not matches:
        return

    # 只注入摘要 + 文件路径，不读全文（节省 token）
    parts = []
    for m in matches:
        desc = f": {m['summary']}" if m.get("summary") else ""
        parts.append(f"- {m['plugin']}:{m['skill']}{desc}\n  文件: {m['file']}")

    if parts:
        result["additionalContext"] = (
            "[插件提示] 以下禁用插件的 skill 与用户消息相关。"
            "如需使用，请用 Read 工具读取对应文件:\n"
            + "\n".join(parts)
        )
        log.info("注入摘要 %d 个 skill, ~%d chars", len(parts), len(result["additionalContext"]))

    if result:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.error("未捕获异常:\n%s", traceback.format_exc())
    sys.exit(0)
