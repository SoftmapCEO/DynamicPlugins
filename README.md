# DynamicPlugins

Auto enable/disable AI CLI plugins per project context. Reduces token consumption by ~89% compared to having all plugins loaded.

Supports **Claude Code**, **CodeBuddy CLI**, **Codex CLI**, **Gemini CLI**, **Kimi Code CLI**, **Qoder CLI**, and **Qwen Code CLI**.

## How It Works

1. **SessionStart**: Scans your project (file types, configs, dependencies) and disables plugins you don't need
2. **Prompt Hook**: When you mention a disabled plugin's topic (e.g. "stripe"), injects a brief summary (~120 tokens) instead of loading the full plugin (~4000 tokens)
3. **Shared rules**: `rules.json` defines which plugins match which project patterns

```
DynamicPlugins/
├── lib/                   # Shared: logger, keyword extraction
│   ├── logger.py
│   └── skill_parser.py
├── rules.json             # Shared: plugin-to-project matching rules
├── claude/                # Claude Code hooks + manager
├── codebuddy/             # CodeBuddy CLI (Tencent) hooks + manager
├── codex/                 # Codex CLI hooks + manager
├── gemini/                # Gemini CLI hooks + manager
├── kimi/                  # Kimi Code CLI hooks + manager
├── qoder/                 # Qoder CLI hooks + manager
└── qwen/                  # Qwen Code CLI hooks + manager
```

## Platform Support

Works on **macOS**, **Linux**, and **Windows**. Pure Python, no bash dependency.

## Quick Start

```bash
git clone <this-repo> ~/DynamicPlugins
cd ~/DynamicPlugins

# One-click install (auto-detects your CLI tools):
python3 install.py

# Or specify a project directory:
python3 install.py /path/to/your/project

# Or install for a specific CLI only:
python3 install.py --cli claude
```

On Windows, use `python` instead of `python3`.

The installer will:
1. Detect which CLI tools are installed (Claude, CodeBuddy, Codex, Gemini, Kimi, Qoder, Qwen)
2. Configure hooks for each detected CLI
3. Scan your project and auto-enable/disable plugins
4. Build the keyword cache

You can also install for individual CLIs:

```bash
python3 claude/install.py     # Claude Code only
python3 gemini/install.py     # Gemini CLI only
# ... etc
```

## Per-CLI Details

### Claude Code

- Config: `~/.claude/settings.json`
- Hooks: `SessionStart` + `UserPromptSubmit`
- Plugin control: `enabledPlugins` map
- HTTP API server: `claude/server/plugin_server.py` (optional, port 9800)

```bash
# Preview without changes
python3 claude/plugin_manager.py /path/to/project --dry

# Apply changes
python3 claude/plugin_manager.py /path/to/project

# Restore all plugins
python3 claude/plugin_manager.py --restore

# Rebuild keyword index
python3 claude/build_cache.py
```

### Codex CLI

- Config: `~/.codex/config.toml`
- Skills: `~/.agents/skills/`, `~/.codex/skills/`, `/etc/codex/skills/`
- Hook: `notify` (experimental)

```bash
python3 codex/plugin_manager.py /path/to/project --dry
python3 codex/build_cache.py
```

### Gemini CLI

- Config: `~/.gemini/settings.json`
- Extensions: `~/.gemini/extensions/`
- Hooks: `SessionStart` + `BeforeAgent`

```bash
python3 gemini/plugin_manager.py /path/to/project --dry
python3 gemini/build_cache.py
```

## Token Savings

| Scenario | Tokens/message |
|---|---|
| All plugins loaded | ~26,600 |
| DynamicPlugins (no match) | ~0 |
| DynamicPlugins (match) | ~120 |
| **Savings** | **~89%** |

The system only injects a one-line summary + file path. The AI reads the full skill file only when actually needed.

## Customizing Rules

Edit `rules.json` to add your own plugin-to-project mappings:

```json
{
  "always_on": ["plugin-a", "plugin-b"],
  "conditional": [
    {
      "plugin": "my-plugin",
      "file_extensions": [".xyz"],
      "config_files": ["my.config.json"],
      "package_deps": ["my-package"]
    }
  ]
}
```

## Requirements

- Python 3.9+
- No external dependencies (stdlib only)

## License

MIT
