#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-08 21:49:47
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-02-08 21:52:25
# FilePath: \NewsPilot\src\workflows\run_news_service.py
# Description: 后台新闻采集与处理服务 - 定时抓取、实时处理
#
# Copyright (c) 2026 by , All Rights Reserved.

# src/workflows/start_news_service.py
"""
启动后台新闻采集与处理服务 (News Pipeline Service)
职责：
1. 定时抓取 (Interval Loop): 周期性从外部源获取新闻
2. 实时处理 (Processing Worker): 持续监控数据库队列，执行清洗、翻译、摘要、向量化
该脚本应作为后台服务长期驻留运行 (Systemd / Supervisor / PM2 / Docker Entrypoint)。
"""
import asyncio
import os
import sys

from src.data_acquisition.daemon_orchestrator import DaemonOrchestrator
from src.custom_logging import get_logger, setup_logging

logger = get_logger(__name__)

async def main(fetch_interval=1800, process_interval=10):
    daemon = DaemonOrchestrator(
        fetch_interval=fetch_interval,
        process_interval=process_interval
    )

    logger.info(f"🚀 NewsPilot Service Started [PID: {os.getpid()}]")
    logger.info(f"├─ 📡 Auto-Fetch: Every {fetch_interval}s")
    logger.info(f"├─ ⚙️ Auto-Process: Every {process_interval}s POLLING")
    logger.info(f"└─ 🛑 Press Ctrl+C to stop...")

    await daemon.start()

if __name__ == "__main__":
    # 初始化日志系统
    setup_logging()

    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        # Default: Fetch every 2 hours (7200s), Process every 60s
        asyncio.run(main(
            fetch_interval=60*120,
            process_interval=60
        ))
    except KeyboardInterrupt:
        logger.info("👋 Service Stopped.")
