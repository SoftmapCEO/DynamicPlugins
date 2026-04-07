#!/usr/bin/env python3
"""
统一缓存构建入口

用法: python3 cache.py --cli claude
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cli_config import get_config
from lib.core import build_cache


def main():
    args = sys.argv[1:]
    cli = None
    for i, a in enumerate(args):
        if a == "--cli" and i + 1 < len(args):
            cli = args[i + 1]

    if not cli:
        print("Usage: python3 cache.py --cli <name>")
        sys.exit(1)

    cfg = get_config(cli)
    result = build_cache(cfg)
    print(f"{cfg['label']} cache built: {result['path']}")
    print(f"  Skills: {result['total']}")
    print(f"  Keywords: {len(result['index']['i'])}")
    print(f"  Skipped (enabled): {result['skipped']}")
    print(f"  Size: {result['path'].stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
