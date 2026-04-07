"""
DynamicPlugins 共享日志模块

日志写入项目根目录下的 logs/ 目录。
每个组件有独立的日志文件，按天轮转。
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_DIR = Path(__file__).parent.parent / "logs"
MAX_BYTES = 2 * 1024 * 1024  # 2MB per file
BACKUP_COUNT = 3


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger，自动写入对应日志文件。

    Args:
        name: 组件名，如 "prompt_inject", "plugin_manager"

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(f"dynplugins.{name}")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{name}.log"

    handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
