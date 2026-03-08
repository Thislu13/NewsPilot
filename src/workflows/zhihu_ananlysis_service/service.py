# -*- coding: utf-8 -*-
"""
知乎分析服务

编排采集守护进程、处理工作器和首次运行初始化。
"""

import asyncio
import os
from typing import Optional, List

from src.data_acquisition.zhihu_daemon_orchestrator import ZhihuDaemonOrchestrator
from src.storage import db_manager, ZhihuRawPost

from src.workflows.zhihu_ananlysis_service.worker import ZhihuProcessingWorker
from src.workflows.zhihu_ananlysis_service.utils import ZhihuServiceConfig, is_first_run_complete, mark_first_run_complete
from src.custom_logging import get_logger

logger = get_logger("ZhihuAnalysisService")

class ZhihuAnalysisService:
    """
    知乎分析主服务。

    管理采集守护进程和处理工作器，编排它们的并发执行，
    并可选地执行首次运行初始化来处理历史数据。
    """

    def __init__(self, config: ZhihuServiceConfig):
        """
        初始化服务。

        参数：
            config: 包含所有服务参数的 ZhihuServiceConfig 实例
        """
        self.config = config

        # 初始化采集守护进程
        self.daemon = ZhihuDaemonOrchestrator(
            fetch_interval=config.fetch_interval,
            process_interval=config.process_interval,
            batch_size=config.batch_size,
        )

        # 将在 run() 方法中创建工作器
        self.worker: Optional[ZhihuProcessingWorker] = None

    async def run(self):
        """
        启动知乎分析服务。

        如果需要，执行首次运行初始化，然后并发运行采集和处理循环。
        """
        # 初始化数据库表
        db_manager.verify_and_create_tables()

        logger.info(f"\n🚀 知乎分析服务已启动 [PID: {os.getpid()}]")
        logger.info(f"  📡 采集间隔: {self.config.fetch_interval}秒")
        logger.info(f"  ⚙️ 处理间隔: {self.config.process_interval}秒")
        logger.info(f"  📊 批处理大小: {self.config.batch_size}")
        logger.info(f"  📧 邮件: {'已启用' if self.config.enable_email else '已禁用'}")
        logger.info("  🛑 按 Ctrl+C 停止服务...\n")

        # 处理首次运行初始化
        if not is_first_run_complete():
            await self._run_first_time_bootstrap()

        # 启动正常运行模式
        logger.info("🚀 启动正常操作模式...\n")
        await self._run_normal_mode()

    async def _run_first_time_bootstrap(self):
        """
        执行首次运行初始化以处理历史数据。

        获取初始数据并处理，不发送邮件。
        """
        logger.info("🔔 检测到首次运行 - 处理历史文章但不发送邮件...")

        # 执行一次采集
        new_ids = await self.daemon.run_acquisition_processing_once()
        if new_ids:
            logger.info(f"✅ 创建了 {len(new_ids)} 条待处理状态的记录")

        # 检查待处理数量
        logger.info("⚙️  处理待处理记录（不发送邮件）...")
        session = db_manager.get_session()
        pending_count = session.query(ZhihuRawPost).filter(
            ZhihuRawPost.status == "pending"
        ).count()
        session.close()

        if pending_count > 0:
            logger.info(f"📋 找到 {pending_count} 条待处理记录...")

            # 创建临时工作器（跳过邮件）
            temp_worker = ZhihuProcessingWorker(
                batch_size=self.config.batch_size,
                process_interval=1,  # 快速轮询用于初始化
                model_name=self.config.model_name,
                enable_email=self.config.enable_email,
                skip_email=True,  # 初始化期间不发送邮件
            )

            temp_worker_task = asyncio.create_task(temp_worker.run())

            # 等待所有待处理/处理中项目完成
            while True:
                session = db_manager.get_session()
                remaining = session.query(ZhihuRawPost).filter(
                    ZhihuRawPost.status.in_(["pending", "processing"])
                ).count()
                session.close()

                if remaining == 0:
                    temp_worker_task.cancel()
                    try:
                        await temp_worker_task
                    except asyncio.CancelledError:
                        pass
                    break

                logger.info(f"⚙️  处理中... 剩余 {remaining} 条")
                await asyncio.sleep(5)

        mark_first_run_complete()
        logger.info("✅ 首次运行已完成。之后的运行将发送邮件通知。\n")

    async def _run_normal_mode(self):
        """
        以正常模式运行服务，并发执行采集和处理。
        """
        async def acquisition_loop():
            """采集守护进程的轮询循环。"""
            while True:
                await self.daemon.run_acquisition_processing_once()
                await asyncio.sleep(self.config.fetch_interval)

        # 为正常模式创建工作器
        self.worker = ZhihuProcessingWorker(
            batch_size=self.config.batch_size,
            process_interval=self.config.process_interval,
            model_name=self.config.model_name,
            enable_email=self.config.enable_email,
            skip_email=False,  # 正常模式下发送邮件
        )

        # 并发运行采集和处理
        await asyncio.gather(
            acquisition_loop(),
            self.worker.run()
        )
