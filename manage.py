#!/usr/bin/env python3
"""
统一插件管理入口

用法:
    python3 manage.py --cli claude /path/to/project         # 扫描并应用
    python3 manage.py --cli claude /path/to/project --dry    # 预览
    python3 manage.py --cli claude --restore                 # 恢复
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cli_config import get_config
from lib.core import scan_project, match_rules, discover_plugins, apply_changes
from lib.registry import ensure_plugins_available


def main():
    args = sys.argv[1:]
    cli = None
    project_dir = None
    dry_run = "--dry" in args
    restore = "--restore" in args

    i = 0
    while i < len(args):
        if args[i] == "--cli" and i + 1 < len(args):
            cli = args[i + 1]
            i += 2
        elif args[i].startswith("--"):
            i += 1
        else:
            project_dir = args[i]
            i += 1

    if not cli:
        print("Usage: python3 manage.py --cli <name> [project_dir] [--dry] [--restore]")
        sys.exit(1)

    cfg = get_config(cli)

    if restore:
        plugins = discover_plugins(cfg)
        needed = set(plugins.keys())  # enable all
        changes = apply_changes(cfg, needed, plugins)
        print(f"Restored {len(changes['enabled'])} plugins.")
        sys.exit(0)

    if not project_dir or not os.path.isdir(project_dir):
        print(f"Error: invalid directory: {project_dir}", file=sys.stderr)
        sys.exit(1)

    scan = scan_project(project_dir)
    needed = match_rules(scan)
    plugins = discover_plugins(cfg)

    if not dry_run:
        installed = set(plugins.keys())
        ensure_plugins_available(cli, needed, installed)
        plugins = discover_plugins(cfg)

    changes = apply_changes(cfg, needed, plugins, dry_run=dry_run)

    prefix = "[Preview] " if dry_run else ""
    print(f"\n{prefix}{cfg['label']} Plugin Config")
    print("=" * 50)
    if changes["enabled"]:
        print(f"\n  Enable ({len(changes['enabled'])}):")
        for p in sorted(changes["enabled"]):
            print(f"    + {p}")
    if changes["disabled"]:
        print(f"\n  Disable ({len(changes['disabled'])}):")
        for p in sorted(changes["disabled"]):
            print(f"    - {p}")
    total = sum(len(v) for v in changes.values())
    active = len(changes["enabled"]) + len([p for p in changes["unchanged"] if p in needed])
    print(f"\n  Total: {active} on / {total - active} off / {total}")


if __name__ == "__main__":
    main()
