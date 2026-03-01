#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-23 19:48:28
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-01 23:42:45
# FilePath: \NewsPilot\src\data_acquisition\zhihu_daemon_orchestrator.py
# Description: 
# 知乎数据采集守护进程 - 负责定时抓取指定用户的知乎文章，进行图片理解处理，并存入数据库等待后续分析
# 
# Copyright (c) 2026 by , All Rights Reserved. 



from __future__ import annotations

import asyncio
import time
from typing import List

from src.storage import db_manager, StorageRepository, ZhihuRawPost
from src.data_acquisition.zhihu_orchestrator import ZhihuAcquisitionService, ZhihuProcessingService
from src.logging import get_logger

logger = get_logger("ZhihuDaemonOrchestrator")

class ZhihuDaemonOrchestrator:
    """
    知乎守护编排器
    职责：
    1. 调用 ZhihuAcquisitionService 抓取原始数据
    2. 检查数据库去重
    3. 调用 ZhihuProcessingService 处理新文章的图片（使用Qwen3-VL-Plus）
    4. 存入 zhihu_raw_posts 表，状态标记为 pending
    注意：
    - 图片理解在入库前完成，避免重复处理
    - LLM分析由独立的 Processing Worker 完成
    """

    def __init__(
        self,
        fetch_interval: int = 1800,
        enable_vision: bool = True,
        vision_model: str = "qwen-vl-plus",
    ):
        self.fetch_interval = fetch_interval
        self.repo = StorageRepository()
        self.acquisition_service = ZhihuAcquisitionService()
        self.processing_service = ZhihuProcessingService(
            enable_vision=enable_vision,
            vision_model=vision_model
        )

    def _ensure_infrastructure(self):
        """确保数据库表存在"""
        db_manager.verify_and_create_tables()

    def _reset_stuck_tasks(self):
        """重置异常退出的任务状态"""
        try:
            count = self.repo.reset_zhihu_raw_statuses(
                ["processing", "retry_later"],
                to_status="pending"
            )
            if count > 0:
                logger.info(f"Reset {count} stuck tasks to pending.")
        except Exception as e:
            logger.error(f"Failed to reset stuck tasks: {e}")


    async def run_acquisition_processing_once(self) -> List[str]:
        """
        执行一次抓取和入库（先去重，再处理图片，最后入库）
        Returns: 新增记录的 unique_id 列表
        """
        session = db_manager.get_session()
        created_ids: List[str] = []

        try:
            logger.info("[Zhihu-Acquisition] Start fetching...")
            start_time = time.time()

            # 1. 调用 ZhihuAcquisitionService 抓取原始数据
            raw_items = await self.acquisition_service.run()
            logger.info(f"[Zhihu-Acquisition] Fetched {len(raw_items)} raw items")

            if not raw_items:
                return []

            # 2. 先对本批次按URL去重
            seen_urls = set()
            deduplicated_items = []
            for item in raw_items:
                if item.source_url not in seen_urls:
                    seen_urls.add(item.source_url)
                    deduplicated_items.append(item)

            logger.info(f"[Zhihu-Acquisition] After batch deduplication: {len(deduplicated_items)} items (removed {len(raw_items) - len(deduplicated_items)} duplicates)")

            # 3. 检查数据库去重，筛选出新文章
            new_items = []
            for item in deduplicated_items:
                exists = self.repo.exists_zhihu_raw_by_source_url(
                    item.source_url,
                    session=session
                )
                if not exists:
                    new_items.append(item)

            logger.info(f"[Zhihu-Acquisition] Found {len(new_items)} new items after database deduplication")

            if not new_items:
                return []

            # 4. 对新文章进行图片处理
            processed_items = await self.processing_service.run(new_items)
            logger.info(f"[Zhihu-Acquisition] Processed {len(processed_items)} items with image understanding")

            # 5. 存入数据库
            new_count = 0
            for item in processed_items:
                zhihu_post = ZhihuRawPost(
                    unique_id=item.unique_id,
                    source_id=item.source_id,
                    source_channel=item.source_channel or "Zhihu",
                    source_url=item.source_url,
                    author=(item.authors[0] if item.authors else None),
                    published_at=item.published_at,
                    fetched_at=item.fetched_at,
                    title=item.title,
                    body=item.body,  # body保持占位符，图片描述在attachments.caption
                    categories=item.categories,
                    attachments=[a.model_dump() for a in item.attachments] if item.attachments else [],
                    extra_data=item.extra_data,
                    status="pending",  # 等待LLM分析
                )

                self.repo.add_zhihu_raw_posts([zhihu_post], session=session)
                created_ids.append(item.unique_id)
                new_count += 1

            session.commit()

            duration = time.time() - start_time
            logger.info(
                f"[Zhihu-Acquisition] Completed. New items: {new_count}. "
                f"Duration: {duration:.2f}s"
            )
            return created_ids

        except Exception as e:
            session.rollback()
            logger.error(f"[Zhihu-Acquisition] Failed: {e}", exc_info=True)
            return []
        finally:
            session.close()

    async def start(self):
        """启动守护进程 - 执行抓取、图片处理和入库"""
        self._ensure_infrastructure()
        self._reset_stuck_tasks()
        logger.info("Zhihu Daemon Orchestrator started (acquisition only).")

        # 定时抓取循环
        while True:
            new_ids = await self.run_acquisition_processing_once()
            if new_ids:
                logger.info(f"[Zhihu-Daemon] Created {len(new_ids)} new records with status=pending")
            else:
                logger.info("[Zhihu-Daemon] No new articles found.")

            logger.info(f"[Zhihu-Daemon] Sleeping for {self.fetch_interval}s...")
            await asyncio.sleep(self.fetch_interval)



