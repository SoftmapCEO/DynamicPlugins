"""
DynamicPlugins 共享 skill 解析模块

提供 SKILL.md 解析、关键词提取等公共函数，
被 claude/codex/gemini 的 build_cache.py 共同引用。
"""

import re

# 扩展的停用词表——过滤掉不具备插件辨识度的通用词
STOPWORDS = {
    # 英语功能词
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "this",
    "that", "these", "those", "it", "its", "and", "or", "but", "not",
    "if", "then", "else", "when", "where", "how", "what", "which",
    "who", "whom", "why", "all", "each", "every", "both", "few",
    "more", "most", "other", "some", "such", "no", "nor", "only",
    "own", "same", "so", "than", "too", "very", "just", "use",
    "using", "used", "your", "you", "they", "them", "their",
    # 编程/技术通用词（会导致大量误匹配）
    "code", "file", "data", "type", "name", "value", "list", "item",
    "make", "create", "update", "delete", "read", "write", "check",
    "run", "start", "stop", "set", "get", "add", "remove", "send",
    "save", "load", "open", "close", "show", "hide", "find", "search",
    "error", "message", "request", "response", "status", "result",
    "input", "output", "event", "action", "state", "config", "setting",
    "tool", "command", "option", "param", "argument", "help",
    "user", "account", "project", "server", "client", "app",
    "test", "debug", "log", "info", "warn", "build", "deploy",
    "version", "path", "url", "key", "token", "api", "sdk",
    "install", "setup", "init", "configure", "enable", "disable",
    "access", "manage", "control", "handle", "process", "channel",
    "skill", "plugin", "hook", "module", "package", "library",
    "function", "method", "class", "interface", "model", "schema",
    "table", "field", "column", "row", "record", "entry", "node",
    "page", "view", "component", "element", "widget", "layout",
    "click", "submit", "form", "button", "link", "image", "text",
    "string", "number", "boolean", "array", "object", "map", "hash",
}


def parse_frontmatter(content: str) -> dict:
    """解析 SKILL.md 的 YAML frontmatter。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}

    fm = {}
    current_key = None
    current_value_lines = []

    for line in match.group(1).splitlines():
        if current_key and (line.startswith("  ") or line.startswith("\t")):
            current_value_lines.append(line.strip())
            continue

        if current_key and current_value_lines:
            fm[current_key] = " ".join(current_value_lines)
            current_value_lines = []
            current_key = None

        kv = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val in (">", "|", ">-"):
                current_key = key
                current_value_lines = []
            else:
                fm[key] = val.strip("'\"")

    if current_key and current_value_lines:
        fm[current_key] = " ".join(current_value_lines)

    return fm


def extract_keywords(name: str, description: str, body: str) -> list:
    """从 skill 名称、描述和正文中提取搜索关键词。

    名称中的词优先保留（确保 stripe 等核心词不被截断），
    其余按字母排序填充。连字符视为分隔符。
    """
    def _clean_words(text: str) -> set:
        text = re.sub(r"[^\w\s]", " ", text.lower())
        return {w for w in text.split() if len(w) >= 3 and w not in STOPWORDS and not w.isdigit()}

    name_words = _clean_words(name)
    desc_words = _clean_words(description)
    body_words = _clean_words(body[:500])

    # 名称词优先，然后描述词，最后正文词
    result = sorted(name_words)
    remaining = sorted((desc_words | body_words) - name_words)
    result.extend(remaining)
    return result[:30]


def get_body_without_frontmatter(content: str) -> str:
    """返回去掉 frontmatter 的正文。"""
    match = re.match(r"^---\s*\n.*?\n---\s*\n", content, re.DOTALL)
    if match:
        return content[match.end():]
    return content
