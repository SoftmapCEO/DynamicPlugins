"""
各 CLI 工具的配置定义

运行时只加载指定 CLI 的配置，避免加载其他 CLI 的代码。
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_config(cli: str) -> dict:
    """获取指定 CLI 的配置。只加载一个 CLI，不加载其他。"""
    configs = {
        "claude": {
            "label": "Claude Code",
            "settings_file": Path.home() / ".claude" / "settings.json",
            "settings_format": "json",
            "disable_mechanism": "enabledPlugins",  # enabledPlugins map (true/false)
            "marketplace_suffix": "@claude-plugins-official",
            "plugin_cache": Path.home() / ".claude" / "plugins" / "cache" / "claude-plugins-official",
            "skills_dirs": [],
            "hooks": {
                "session_start": "SessionStart",
                "prompt_submit": "UserPromptSubmit",
            },
            "hook_output": "additionalContext",  # or "hookSpecificOutput"
            "env_project_dir": "CLAUDE_PROJECT_DIR",
            "cache_dir": ROOT_DIR / "claude" / "cache",
        },
        "codebuddy": {
            "label": "CodeBuddy",
            "settings_file": Path.home() / ".codebuddy" / "settings.json",
            "settings_format": "json",
            "disable_mechanism": "enabledPlugins",
            "marketplace_suffix": "",
            "plugin_cache": Path.home() / ".codebuddy" / "plugins" / "cache",
            "skills_dirs": [],
            "hooks": {
                "session_start": "SessionStart",
                "prompt_submit": "UserPromptSubmit",
            },
            "hook_output": "hookSpecificOutput",
            "env_project_dir": "CODEBUDDY_PROJECT_DIR",
            "cache_dir": ROOT_DIR / "codebuddy" / "cache",
        },
        "codex": {
            "label": "Codex CLI",
            "settings_file": Path.home() / ".codex" / "config.toml",
            "settings_format": "toml",
            "disable_mechanism": "skill_rename",  # SKILL.md -> SKILL.md.disabled
            "skills_dirs": [
                Path.home() / ".agents" / "skills",
                Path.home() / ".codex" / "skills",
            ],
            "hooks": {
                "prompt_submit": "notify",
            },
            "hook_output": "additionalContext",
            "cache_dir": ROOT_DIR / "codex" / "cache",
        },
        "gemini": {
            "label": "Gemini CLI",
            "settings_file": Path.home() / ".gemini" / "settings.json",
            "settings_format": "json",
            "disable_mechanism": "disabledExtensions",  # disabledExtensions array
            "extensions_dir": Path.home() / ".gemini" / "extensions",
            "extension_manifest": "gemini-extension.json",
            "skills_dirs": [],
            "hooks": {
                "session_start": "SessionStart",
                "prompt_submit": "BeforeAgent",
            },
            "hook_output": "hookSpecificOutput",
            "env_project_dir": "GEMINI_PROJECT_DIR",
            "cache_dir": ROOT_DIR / "gemini" / "cache",
        },
        "kimi": {
            "label": "Kimi Code",
            "settings_file": Path.home() / ".kimi" / "config.toml",
            "settings_format": "toml",
            "disable_mechanism": "plugin_rename",  # plugin.json -> plugin.json.disabled
            "plugins_dir": Path.home() / ".kimi" / "plugins",
            "skills_dirs": [
                Path.home() / ".kimi" / "skills",
                Path.home() / ".agents" / "skills",
            ],
            "hooks": {
                "session_start": "SessionStart",
                "prompt_submit": "PreToolUse",
            },
            "hook_output": "additionalContext",
            "env_project_dir": "KIMI_WORK_DIR",
            "cache_dir": ROOT_DIR / "kimi" / "cache",
        },
        "qoder": {
            "label": "Qoder CLI",
            "settings_file": Path.home() / ".qoder" / "settings.json",
            "settings_format": "json",
            "disable_mechanism": "skill_rename",
            "skills_dirs": [Path.home() / ".qoder" / "skills"],
            "hooks": {
                "prompt_submit": "UserPromptSubmit",
                # no session_start
            },
            "hook_output": "hookSpecificOutput",
            "cache_dir": ROOT_DIR / "qoder" / "cache",
        },
        "qwen": {
            "label": "Qwen Code",
            "settings_file": Path.home() / ".qwen" / "settings.json",
            "settings_format": "json",
            "disable_mechanism": "disabledExtensions",
            "extensions_dir": Path.home() / ".qwen" / "extensions",
            "extension_manifest": "qwen-extension.json",
            "skills_dirs": [],
            "hooks": {
                "session_start": "SessionStart",
                "prompt_submit": "UserPromptSubmit",
            },
            "hook_output": "hookSpecificOutput",
            "env_project_dir": "",
            "cache_dir": ROOT_DIR / "qwen" / "cache",
        },
    }

    if sys.platform != "win32" and cli == "codex":
        configs["codex"]["skills_dirs"].append(Path("/etc/codex/skills"))

    if cli not in configs:
        raise ValueError(f"Unknown CLI: {cli}. Available: {', '.join(sorted(configs))}")

    return configs[cli]


def all_cli_names() -> list:
    return ["claude", "codebuddy", "codex", "gemini", "kimi", "qoder", "qwen"]
