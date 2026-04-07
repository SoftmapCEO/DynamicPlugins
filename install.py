#!/usr/bin/env python3
"""
DynamicPlugins 一键安装

自动检测已安装的 CLI 工具，配置 hooks，扫描当前项目，构建缓存。

用法:
    python3 install.py                     # 自动检测 CLI + 扫描当前目录
    python3 install.py /path/to/project    # 指定项目目录
    python3 install.py --cli claude        # 只安装指定 CLI
    python3 install.py --list              # 列出支持的 CLI 及检测结果
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable

# CLI 检测配置: (目录名, CLI 可执行文件名列表, 配置目录)
CLI_TOOLS = {
    "claude":    {"bins": ["claude"],                "config": "~/.claude",    "label": "Claude Code (Anthropic)"},
    "codebuddy": {"bins": ["codebuddy"],             "config": "~/.codebuddy", "label": "CodeBuddy (Tencent)"},
    "codex":     {"bins": ["codex"],                 "config": "~/.codex",     "label": "Codex CLI (OpenAI)"},
    "gemini":    {"bins": ["gemini"],                "config": "~/.gemini",    "label": "Gemini CLI (Google)"},
    "kimi":      {"bins": ["kimi", "kimi-code"],     "config": "~/.kimi",      "label": "Kimi Code (Moonshot)"},
    "qoder":     {"bins": ["qodercli", "qoder"],     "config": "~/.qoder",     "label": "Qoder CLI"},
    "qwen":      {"bins": ["qwen", "qwen-code"],     "config": "~/.qwen",      "label": "Qwen Code (Alibaba)"},
}


def detect_cli(name: str) -> bool:
    """检测 CLI 是否已安装（在 PATH 中或配置目录存在）。"""
    info = CLI_TOOLS[name]

    # 检查可执行文件
    for bin_name in info["bins"]:
        if shutil.which(bin_name):
            return True

    # 检查配置目录（用户可能已安装但不在 PATH 中）
    config_dir = Path(info["config"]).expanduser()
    if config_dir.exists():
        return True

    return False


def detect_all() -> dict:
    """检测所有 CLI，返回 {name: detected}。"""
    return {name: detect_cli(name) for name in CLI_TOOLS}


def _setup_hooks(name: str):
    """用统一脚本注册 hooks 到 CLI 配置文件。"""
    import json as _json
    sys.path.insert(0, str(ROOT_DIR))
    from lib.cli_config import get_config

    cfg = get_config(name)
    settings_file = cfg["settings_file"]
    fmt = cfg.get("settings_format", "json")

    inject_cmd = f'"{PYTHON}" "{ROOT_DIR / "inject.py"}" --cli {name}'
    manage_cmd = f'"{PYTHON}" "{ROOT_DIR / "manage.py"}" --cli {name}'

    if fmt == "json":
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        if not settings_file.exists():
            settings_file.write_text("{}\n", encoding="utf-8")
        with open(settings_file, encoding="utf-8") as f:
            settings = _json.load(f)

        hooks = settings.setdefault("hooks", {})
        modified = False

        for event_key, event_name in cfg.get("hooks", {}).items():
            cmd = manage_cmd if event_key == "session_start" else inject_cmd
            script_marker = "manage.py" if event_key == "session_start" else "inject.py"

            # 检查是否已注册
            existing_cmds = []
            for group in hooks.get(event_name, []):
                if isinstance(group, dict):
                    for h in group.get("hooks", []):
                        existing_cmds.append(h.get("command", ""))
                elif isinstance(group, str):
                    existing_cmds.append(group)

            if not any(script_marker in c for c in existing_cmds):
                hook_entry = {"type": "command", "command": cmd, "timeout": 30}
                hooks.setdefault(event_name, []).append({"hooks": [hook_entry]})
                modified = True
                print(f"  + {event_name} hook added")
            else:
                print(f"  {event_name} hook exists, skipped")

        if modified:
            with open(settings_file, "w", encoding="utf-8") as f:
                _json.dump(settings, f, indent=2, ensure_ascii=False)
                f.write("\n")

    elif fmt == "toml":
        import re
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        content = settings_file.read_text(encoding="utf-8") if settings_file.exists() else ""

        for event_key, event_name in cfg.get("hooks", {}).items():
            cmd = manage_cmd if event_key == "session_start" else inject_cmd
            script_marker = "manage.py" if event_key == "session_start" else "inject.py"

            if script_marker not in content:
                content = content.rstrip() + f'\n\n[[hooks]]\nevent = "{event_name}"\ncommand = "{cmd}"\ntimeout = 30\n'
                print(f"  + {event_name} hook added")
            else:
                print(f"  {event_name} hook exists, skipped")

        settings_file.write_text(content, encoding="utf-8")


def install_cli(name: str, project_dir: str):
    """为指定 CLI 安装 DynamicPlugins。"""
    info = CLI_TOOLS[name]

    print(f"\n{'='*60}")
    print(f"  Installing for {info['label']}...")
    print(f"{'='*60}")

    # 1. 配置 hooks (使用统一入口脚本)
    _setup_hooks(name)

    # 2. 扫描项目
    if project_dir:
        print(f"\n  Scanning project: {project_dir}")
        subprocess.run(
            [PYTHON, str(ROOT_DIR / "manage.py"), "--cli", name, project_dir],
            cwd=str(ROOT_DIR), timeout=60,
        )

    # 3. 构建缓存
    print(f"\n  Building cache...")
    subprocess.run(
        [PYTHON, str(ROOT_DIR / "cache.py"), "--cli", name],
        cwd=str(ROOT_DIR), timeout=60,
    )

    return True


def print_status(detected: dict):
    """打印检测结果表格。"""
    print("\n  Detected CLI tools:\n")
    print(f"  {'CLI':<30} {'Status':<12} {'Directory'}")
    print(f"  {'-'*30} {'-'*12} {'-'*20}")
    for name, found in sorted(detected.items()):
        info = CLI_TOOLS[name]
        status = "FOUND" if found else "not found"
        marker = "+" if found else "-"
        config = Path(info["config"]).expanduser()
        config_str = str(config) if config.exists() else ""
        print(f"  {marker} {info['label']:<28} {status:<12} {config_str}")


def main():
    args = sys.argv[1:]

    # --list: 只显示检测结果
    if "--list" in args:
        print("\n  DynamicPlugins - CLI Detection\n")
        print_status(detect_all())
        print()
        return

    # 解析参数
    target_cli = None
    project_dir = None

    i = 0
    while i < len(args):
        if args[i] == "--cli" and i + 1 < len(args):
            target_cli = args[i + 1]
            i += 2
        elif args[i].startswith("--"):
            i += 1
        else:
            project_dir = args[i]
            i += 1

    if not project_dir:
        project_dir = os.getcwd()

    if not os.path.isdir(project_dir):
        print(f"Error: directory does not exist: {project_dir}", file=sys.stderr)
        sys.exit(1)

    print(r"""
     ____                              _      ____  _             _
    |  _ \ _   _ _ __   __ _ _ __ ___ (_) ___|  _ \| |_   _  __ _(_)_ __  ___
    | | | | | | | '_ \ / _` | '_ ` _ \| |/ __| |_) | | | | |/ _` | | '_ \/ __|
    | |_| | |_| | | | | (_| | | | | | | | (__|  __/| | |_| | (_| | | | | \__ \
    |____/ \__, |_| |_|\__,_|_| |_| |_|_|\___|_|   |_|\__,_|\__, |_|_| |_|___/
           |___/                                              |___/
    """)

    print(f"  Project:  {project_dir}")
    print(f"  Python:   {PYTHON}")
    print(f"  Platform: {sys.platform}")

    # 检测 CLI 工具
    detected = detect_all()
    print_status(detected)

    # 确定要安装的 CLI
    if target_cli:
        if target_cli not in CLI_TOOLS:
            print(f"\n  Error: unknown CLI '{target_cli}'")
            print(f"  Available: {', '.join(sorted(CLI_TOOLS))}")
            sys.exit(1)
        to_install = [target_cli]
    else:
        to_install = [name for name, found in detected.items() if found]

    if not to_install:
        print("\n  No supported CLI tools detected!")
        print("  Install one of: claude, codebuddy, codex, gemini, kimi, qoder, qwen")
        print("  Or specify manually: python3 install.py --cli <name>")
        sys.exit(1)

    print(f"\n  Will install for: {', '.join(CLI_TOOLS[n]['label'] for n in to_install)}")

    # 逐个安装
    success = []
    failed = []
    for name in to_install:
        if install_cli(name, project_dir):
            success.append(name)
        else:
            failed.append(name)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  Installation Summary")
    print(f"{'='*60}")
    if success:
        print(f"\n  Installed ({len(success)}):")
        for n in success:
            print(f"    + {CLI_TOOLS[n]['label']}")
    if failed:
        print(f"\n  Failed ({len(failed)}):")
        for n in failed:
            print(f"    ! {CLI_TOOLS[n]['label']}")

    print(f"""
  Next steps:
    1. Start a new session in your CLI tool
    2. The SessionStart hook will auto-configure plugins for your project
    3. Type naturally - matching skills are injected automatically

  Manual commands:
    python3 {ROOT_DIR}/<cli>/plugin_manager.py {project_dir} --dry   # Preview
    python3 {ROOT_DIR}/<cli>/build_cache.py                          # Rebuild cache
    python3 {ROOT_DIR}/<cli>/plugin_manager.py --restore             # Restore all
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)
