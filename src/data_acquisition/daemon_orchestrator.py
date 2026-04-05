#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-31
# FilePath: \NewsPilot\src\data_acquisition\daemon_orchestrator.py
# Description: 守护进程编排器 - 实现"抓取入库"与"异步处理"的解耦
#   基于数据库状态的长期驻留编排器 (Daemon Orchestrator)。
#   实现“抓取入库”与“异步处理”的解耦。
# 
# Copyright (c) 2026 by , All Rights Reserved. 

import asyncio
import time
from typing import List

# 项目内引用
from src.storage import db_manager, RawNews, RefinedNews, RawNewsStaging, StorageRepository
from src.data_acquisition.orchestrator import NewsAcquisitionService, NewsProcessingService
from core.news_schemas import NewsItemRawSchema, NewsItemRefinedSchema

from config import settings

from src.custom_logging.logging_config import get_logger
logger = get_logger("DaemonOrchestrator")

class DaemonOrchestrator:
    """
    守护进程编排器。
    包含两个核心任务：
    1. Acquisition Job: 定时抓取外部新闻，存入 RawNewsStaging (临时表)，状态标记为 pending。
    2. Processing Worker: 持续轮询 RawNewsStaging 中 pending 的记录，调用 pipeline 处理，
       成功后将数据归档到 RawNews (永久表) 并存入 RefinedNews。
    """

    def __init__(self, fetch_interval: int = 60*120, process_interval: int = 60, batch_size: int = 20):
        """
        :param fetch_interval: 抓取间隔（秒），默认 120 分钟。
        :param process_interval: 处理轮询间隔（秒），当没有任务时休眠多久。
        :param batch_size: 每次从数据库取多少条进行并发处理。
        """
        self.fetch_interval = fetch_interval
        self.process_interval = process_interval
        self.batch_size = batch_size
        self.repo = StorageRepository()

        # 初始化采集服务
        self.acquisition_service = NewsAcquisitionService(config= settings.NEWS_SOURCES_CONFIG, attachments_root="data/attachments")  
        # 初始化处理服务，传入配置
        self.processing_service = NewsProcessingService(newspilot_config=settings.NewsProcessingPipeline_DEFAULT_CONFIG)

    def _ensure_infrastructure(self):
        """确保数据库表存在"""
        db_manager.verify_and_create_tables()

    def _reset_stuck_tasks(self):
        """重置异常退出的任务状态"""
        try:
            count = self.repo.reset_staging_statuses(['processing', 'retry_later'], to_status='pending')
            if count > 0:
                logger.info(f"Reset {count} stuck tasks to pending.")
        except Exception as e:
            logger.error(f"Failed to reset stuck tasks: {e}")

    async def run_acquisition_once(self):
        """
        一次完整的抓取任务：Fetcher -> 归一化 -> DB (RawNewsStaging)
        """
        session = db_manager.get_session()
        try:
            logger.info("[Acquisition] Start fetching news...")
            start_time = time.time()

            # 1. 执行抓取
            raw_schemas = await self.acquisition_service.run()
            logger.info(f"[Acquisition] Fetched {len(raw_schemas)} raw items.")
            if not raw_schemas:
                return

            # 2. 入库 (RawNewsStaging)
            new_count = 0
            staging_items: List[RawNewsStaging] = []
            for item in raw_schemas:
                # 检查 Staging 表去重 (确保当前队列里没有在这个 URL)
                exists_staging = self.repo.exists_staging_by_source_url(item.source_url, session=session)
                # 检查正式表去重 (确保历史没抓过)
                exists_raw = self.repo.exists_raw_by_source_url(item.source_url, session=session)
                
                if not exists_staging and not exists_raw:
                    staging_item = RawNewsStaging(
                        unique_id=item.unique_id,
                        source_id=item.source_id,
                        source_channel=item.source_channel,
                        source_url=item.source_url,
                        published_at=item.published_at,
                        fetched_at=item.fetched_at,
                        title=item.title,
                        abstract=item.abstract,
                        body=item.body,
                        authors=item.authors,
                        categories=item.categories,
                        attachments=[a.model_dump() for a in item.attachments] if item.attachments else [],
                        supporting_document_ids=item.supportingDocument_id,
                        extra_data=item.extra_data,
                        processing_status='pending', # 初始状态
                    )
                    staging_items.append(staging_item)
                    new_count += 1
                    if staging_items:
                        self.repo.add_raw_news_staging(staging_items, session=session)
                        session.commit()
            duration = time.time() - start_time
            logger.info(f"[Acquisition] Job finished. New items staged: {new_count}. Duration: {duration:.2f}s")
        except Exception as e:
            session.rollback()
            logger.error(f"[Acquisition] Failed: {e}", exc_info=True)
        finally:
            session.close()

    async def run_processing_worker(self):
        """
        持续运行的处理工作流：
        Poll Staging(pending) -> Pipeline -> Save(Refined & Raw) -> Delete Staging
        """
        logger.info("[Processing] Worker started.")
        while True:
            processing_ids = []
            try:
                session = db_manager.get_session()
                # 1. 拉取 Staging 表中 PENDING 任务
                staging_orms = self.repo.fetch_staging_pending(limit=self.batch_size, session=session)

                if not staging_orms:
                    session.close()
                    await asyncio.sleep(self.process_interval)
                    continue
                
                logger.info(f"[Processing] Picked up {len(staging_orms)} items from staging.")

                # 2. 锁定状态 -> processing
                processing_ids = [r.unique_id for r in staging_orms]
                self.repo.mark_staging_status(processing_ids, 'processing', session=session)
                session.commit()

                # 3. 构造 Schema 用于 Pipeline
                raw_schemas = []
                for r in staging_orms:
                    schema = NewsItemRawSchema(
                        unique_id=r.unique_id,
                        source_id=r.source_id,
                        source_channel=r.source_channel,
                        source_url=r.source_url,
                        published_at=r.published_at,
                        fetched_at=r.fetched_at,
                        title=r.title,
                        abstract=r.abstract,
                        body=r.body,
                        authors=r.authors or [],
                        categories=r.categories or [],
                        attachments=r.attachments or [],
                        supportingDocument_id=r.supporting_document_ids or [],
                        extra_data=r.extra_data
                    )
                    # 保留上下文，以便后续从 schema 映射回 staging 对象
                    raw_schemas.append(schema)

                # 4. 执行 Pipeline (耗时操作)
                session.close() # 释放连接
                
                result_dict = await self.processing_service.run(raw_schemas)
                
                # 获取结果
                raw_schemas: List[NewsItemRawSchema] = result_dict.get("raw_items", [])
                refined_schemas: List[NewsItemRefinedSchema] = result_dict.get("refined_items", [])
                
                # 建立翻译后数据的索引，方便查找
                raw_map = {item.unique_id: item for item in raw_schemas}

                # 重新连接数据库
                session = db_manager.get_session()

                # 5. 归档逻辑：Staging -> RawNews(Translated) + RefinedNews
                success_ids = []
                raw_orms: List[RawNews] = []
                refined_orms: List[RefinedNews] = []
                
                for refined_item in refined_schemas:
                    raw_id = refined_item.NewsItemRaw_id
                    
                    # 获取对应的翻译后 Raw Item
                    raw_item = raw_map.get(raw_id)
                    if not raw_item:
                        logger.warning(f"Refined item for {raw_id} missing translated raw item. Skipping.")
                        continue

                    # 5.2 写入永久 RawNews 表 (使用翻译后的内容)
                    raw_orms.append(RawNews(
                        unique_id=raw_item.unique_id,
                        source_id=raw_item.source_id,
                        source_channel=raw_item.source_channel,
                        source_url=raw_item.source_url,
                        published_at=raw_item.published_at,
                        fetched_at=raw_item.fetched_at,
                        title=raw_item.title,
                        abstract=raw_item.abstract,
                        body=raw_item.body,
                        authors=raw_item.authors,
                        categories=raw_item.categories,
                        evaluation_score=raw_item.evaluation_score,
                        attachments=[a.model_dump() for a in raw_item.attachments] if raw_item.attachments else [],
                        supporting_document_ids=raw_item.supportingDocument_id,
                        extra_data=raw_item.extra_data,
                    ))
                    
                    # 5.3 保存 RefinedNews
                    refined_orms.append(RefinedNews(
                        unique_id=refined_item.unique_id,
                        source_id=refined_item.source_id,
                        source_channel=refined_item.source_channel,
                        source_url=refined_item.source_url,
                        news_item_raw_id=refined_item.NewsItemRaw_id,
                        published_at=refined_item.published_at,
                        fetched_at=refined_item.fetched_at,
                        title=refined_item.title,
                        abstract=refined_item.abstract,
                        categories=refined_item.categories,
                        evaluation_score=refined_item.evaluation_score,
                        extra_data=refined_item.extra_data
                    ))
                    
                    # 标记为成功，稍后从 Staging 删除
                    success_ids.append(raw_id)

                if raw_orms:
                    self.repo.upsert_raw_news(raw_orms, session=session)
                if refined_orms:
                    self.repo.upsert_refined_news(refined_orms, session=session)

                # 6. 清理 Staging 表
                if success_ids:
                    # 成功的从 Staging 删除
                    self.repo.delete_staging_by_ids(success_ids, session=session)

                # 失败的(在处理批次中但不在结果中) 标记为 failed
                failed_ids = set(processing_ids) - set(success_ids)
                if failed_ids:
                    self.repo.mark_staging_status(
                        failed_ids,
                        'failed',
                        last_error='Pipeline processing failed',
                        session=session,
                    )
                    logger.warning(f"[Processing] {len(failed_ids)} items failed. Kept in staging with status=failed.")
                session.commit()
                logger.info(f"[Processing] Archive finished. {len(success_ids)} moved to RawNews/Refined.")

            except Exception as e:
                logger.error(f"[Processing] Error: {e}", exc_info=True)
                if session.is_active:
                    session.rollback()
                # 恢复处理中的状态
                if processing_ids:
                    try:
                        self.repo.mark_staging_status(processing_ids, 'pending')
                    except:
                        pass
                await asyncio.sleep(10)
            finally:
                if session:
                    session.close()

    async def start(self):
        """启动整个守护进程"""
        self._ensure_infrastructure()
        self._reset_stuck_tasks()
        logger.info("Daemon Orchestrator started.")

        # 定义定时抓取任务
        async def acquisition_loop():
            while True:
                await self.run_acquisition_once()
                logger.info(f"[Acquisition] Sleeping for {self.fetch_interval}s...")
                await asyncio.sleep(self.fetch_interval)

        # 启动并发任务
        # task1: 抓取循环 (低频)
        # task2: 处理循环 (高频/常驻)
        await asyncio.gather(
            acquisition_loop(),
            self.run_processing_worker()
        )
