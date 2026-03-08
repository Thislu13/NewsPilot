"""
统一日志配置模块

使用方式：
    from src.custom_logging.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("服务启动")
    logger.error("发生错误", exc_info=True)
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


# 日志格式
LOG_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志目录
LOG_DIR = Path("logs")

# 日志级别（从环境变量读取，默认INFO）
LOG_LEVEL = os.getenv("NEWSPILOT_LOG_LEVEL", "INFO").upper()


def setup_logging():
    """
    初始化日志系统

    只需在应用启动时调用一次
    """
    # 创建日志目录
    LOG_DIR.mkdir(exist_ok=True)

    # 获取root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # 清除已有的handlers（避免重复配置）
    root_logger.handlers.clear()

    # 1. 控制台Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # 2. 全局错误日志Handler（ERROR+）
    error_handler = TimedRotatingFileHandler(
        LOG_DIR / "error.log",
        when="midnight",
        interval=1,
        backupCount=90,  # 保留90天
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root_logger.addHandler(error_handler)

    # 3. 关闭第三方HTTP库的日志噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def get_logger(
    name: str,
    log_file: Optional[str] = None,
    level: Optional[str] = None
) -> logging.Logger:
    """
    获取logger实例

    Args:
        name: logger名称，通常使用 __name__
        log_file: 可选的日志文件名（不含路径），如 "acquisition.log"
        level: 可选的日志级别，如 "DEBUG"

    Returns:
        配置好的logger实例

    示例：
        # 基础用法
        logger = get_logger(__name__)

        # 指定日志文件
        logger = get_logger(__name__, log_file="acquisition.log")

        # 指定日志级别
        logger = get_logger(__name__, level="DEBUG")
    """
    logger = logging.getLogger(name)

    # 设置日志级别
    if level:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 如果指定了日志文件，添加文件Handler
    if log_file:
        # 检查是否已经添加过该文件的Handler
        file_path = LOG_DIR / log_file
        has_file_handler = any(
            isinstance(h, TimedRotatingFileHandler) and h.baseFilename == str(file_path.absolute())
            for h in logger.handlers
        )

        if not has_file_handler:
            file_handler = TimedRotatingFileHandler(
                file_path,
                when="midnight",
                interval=1,
                backupCount=30,  # 保留30天
                encoding="utf-8"
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            logger.addHandler(file_handler)

    return logger


# 模块级别的logger（用于本模块内部）
_module_logger = logging.getLogger(__name__)
