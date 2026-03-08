#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-27 20:35:02
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-08 23:41:04
# FilePath: \NewsPilot\src\data_acquisition\zhihu_orchestrator.py
# Description: 
# 知乎数据编排器 - 遵循 orchestrator.py 的设计模式
# 
# Copyright (c) 2026 by , All Rights Reserved. 



from typing import List

from src.data_acquisition.fetchers.zhihu_fetcher import Zhihu_RSSHubFetcher
from src.data_acquisition.processors.module import ImageVision
from core.news_schemas import NewsItemRawSchema

from config import settings


class ZhihuAcquisitionService:
    """
    知乎抓取服务
    职责：调用 Zhihu_RSSHubFetcher 抓取原始数据
    """

    def __init__(self, config: dict = settings.ZHIHU_RSS_CONFIG, attachments_root: str = "data/attachments"):
        self.fetcher = Zhihu_RSSHubFetcher(rss_config=config, attachment_dir=attachments_root) 

    async def run(self) -> List[NewsItemRawSchema]:
        """
        执行抓取，返回原始数据列表
        """
        items = await self.fetcher.fetch_and_normalize()
        return items


class ZhihuProcessingService:
    """
    知乎处理服务
    职责：调用 ImageVisionProcessor 处理图片
    """

    def __init__(
        self, enable_vision: bool = True, 
        type: str = "llm", model: str = "qwen", model_id: str = "qwen-vl-plus",
        attachments_root = "data/attachments", max_concurrent = 5
    ):

        if enable_vision:
            self.vision_processor = ImageVision(
                type=type,
                model=model,
                model_id=model_id,
                attachments_root=attachments_root,
                max_concurrent=max_concurrent
            )
        else:
            self.vision_processor = None

    async def run(self, news_list: List[NewsItemRawSchema]) -> List[NewsItemRawSchema]:
        """
        处理图片，返回处理后的数据列表
        """
        if self.vision_processor:
            processed_items = await self.vision_processor.vision_batch(news_list)
            return processed_items
        else:
            return news_list


class ZhihuOrchestrator:
    """
    知乎数据编排器
    组合 Acquisition 和 Processing 服务
    """

    def __init__(self):
        self.acquisition_service = ZhihuAcquisitionService()
        self.processing_service = ZhihuProcessingService()

    async def run(self) -> List[NewsItemRawSchema]:
        """
        执行完整流程：抓取 → 处理图片
        """
        # 1. 抓取
        raw_items = await self.acquisition_service.run()

        # 2. 处理图片
        processed_items = await self.processing_service.run(raw_items)

        return processed_items
