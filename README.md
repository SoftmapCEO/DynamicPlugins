# DynamicPlugins

**The World's First Dynamic Plugin System for AI CLI**

> Make Great Things Happen Today.

Auto enable/disable AI CLI plugins per project context. Save **74%** plugin tokens -- **$192/year** per user ($200/mo subscription), **11.1 billion** tokens freed per user annually.

Claude Code, Codex CLI, Gemini CLI, Kimi Code, Qwen Code, CodeBuddy, Qoder -- every official CLI loads all plugins statically and requires manual management. **DynamicPlugins is the first and only solution that automatically adapts plugins to your project context.**

## The Problem

Every AI CLI today loads all 20 plugins on every message. You pay for plugins you don't need.

### Without DynamicPlugins

- All 20 plugins loaded on every message (~4,300 tokens)
- Manual enable/disable -- tedious, error-prone
- Switch projects? Manually reconfigure plugins
- $192/year wasted per user from $200/mo subscription
- Official CLIs provide no dynamic mechanism

### With DynamicPlugins

- Only 5 relevant plugins loaded (~1,100 tokens average)
- Auto-detects project type and adapts instantly
- Switch projects? Plugins auto-reconfigure on session start
- Save $192/year + 11.1B tokens -- faster responses, better AI quality
- Works across 7 CLI tools with one install

## Token Savings

| Scenario | Tokens / Message | Context Waste |
|---|---|---|
| 20 plugins all loaded (official default) | ~4,300 | 10.7% of context |
| DynamicPlugins (5 needed + smart inject) | ~1,100 | 2.75% of context |
| **Savings per message** | **~3,200 (74%)** | **8% subscription unlocked** |

## Annual Savings Calculator

Based on real power-user data: 9,500 messages/day, 20 plugins, 365 days.

### Per User ($200/mo subscription)

| Metric | Value |
|---|---|
| Subscription / Year | $2,400 |
| Tokens Saved / Year | 11.1B |
| **Saved / Year** | **$192** ($2,400 x 8%) |

### Global Impact (10M Power Users, 2026)

| Metric | Value |
|---|---|
| Total Subscriptions / Year | $24B |
| **Saved / Year** | **$19.2B** (10M x $192) |
| Tokens Saved / Year | 111T |
| CO2 Reduced | 1.3M tons |

> \* $200/mo subscription. Real data: 9,500 msgs/day. Plugins waste 10.7% context, DynamicPlugins reclaims 8%. 50M AI devs (SlashData 2026), 10M power users.

## How It Works

Three-stage pipeline. Each CLI runs only its own code path via `--cli` flag.

### 1. Project Scan
On session start, scans file types, configs, and dependencies. Disables plugins you don't need. Auto-installs missing official plugins.

### 2. Keyword Index
Builds an inverted index from disabled plugins' skills. Name keywords prioritized. Compact JSON cache ~90KB.

### 3. Smart Inject
When your prompt matches a disabled plugin, injects a one-line summary (~120 tokens). AI reads the full skill only when needed.

## Supported CLIs

7 CLI tools. All use static plugin loading officially. DynamicPlugins adds the missing dynamic layer.

| CLI | Vendor | Config | Hooks | Disable Mechanism |
|---|---|---|---|---|
| **Claude Code** | Anthropic | `~/.claude/settings.json` | SessionStart + UserPromptSubmit | `enabledPlugins` |
| **CodeBuddy** | Tencent | `~/.codebuddy/settings.json` | SessionStart + UserPromptSubmit | `enabledPlugins` |
| **Codex CLI** | OpenAI | `~/.codex/config.toml` | notify | TOML `enabled` |
| **Gemini CLI** | Google | `~/.gemini/settings.json` | SessionStart + BeforeAgent | `disabledExtensions` |
| **Kimi Code** | Moonshot | `~/.kimi/config.toml` | SessionStart + PreToolUse | `plugin.json.disabled` |
| **Qoder CLI** | Qoder AI | `~/.qoder/settings.json` | UserPromptSubmit | `SKILL.md.disabled` |
| **Qwen Code** | Alibaba | `~/.qwen/settings.json` | SessionStart + UserPromptSubmit | `disabledExtensions` |

## Platform Support

Works on **macOS**, **Linux**, and **Windows**. Pure Python, no bash dependency.

## Quick Start

```bash
git clone https://github.com/SoftmapCEO/DynamicPlugins ~/DynamicPlugins
cd ~/DynamicPlugins

# One-click: auto-detect all installed CLIs, scan project, build cache
python3 install.py

# Or specify a project directory
python3 install.py /path/to/your/project

# Or install for a specific CLI only
python3 install.py --cli claude

# Check detection results
python3 install.py --list
```

On Windows, use `python` instead of `python3`.

## Architecture

Unified entry points. `--cli` flag ensures each CLI only loads its own config. Zero cross-contamination.

```
DynamicPlugins/
├── install.py          # One-click install (auto-detect CLIs)
├── manage.py --cli X   # Scan project, enable/disable plugins
├── cache.py  --cli X   # Build keyword index
├── inject.py --cli X   # Hook: match & inject (~120 tokens)
├── rules.json          # Plugin-to-project matching rules
└── lib/
    ├── core.py         # Unified logic (scan/match/inject)
    ├── cli_config.py   # 7 CLI configs (~20 lines each)
    ├── registry.py     # Official channel verify + auto-install
    ├── skill_parser.py # SKILL.md parsing + keyword extraction
    └── logger.py       # Shared rotating file logger
```

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

## Community

- Email: lvfei99999@gmail.com
- GitHub: https://github.com/SoftmapCEO/DynamicPlugins

### WeChat Group: AllAI

<img src="assets/wechat.jpg" width="250" alt="WeChat Group: AllAI">

### Telegram Group

<img src="assets/telegram.png" width="250" alt="Telegram Group">

## Support This Project

DynamicPlugins is free and open-source. If it saves you time and money, consider supporting:

### PayPal

https://www.paypal.me/softmap

### Alipay

<img src="assets/alipay.jpg" width="250" alt="Alipay QR Code">

## License

MIT
