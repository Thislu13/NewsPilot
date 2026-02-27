#
# Author: Claude Code
# Date: 2026-02-22
# Description: 知乎数据编排器 - 遵循 orchestrator.py 的设计模式

from typing import List

from src.data_acquisition.fetchers.rsshub_fetcher import RSSHubFetcher
from src.data_acquisition.processors.module.ImageVision import ImageVision
from core.news_schemas import NewsItemRawSchema


class ZhihuAcquisitionService:
    """
    知乎抓取服务
    职责：调用 ZhihuFetcher 抓取原始数据
    """

    def __init__(self):
        self.fetcher = RSSHubFetcher(choices=["zhihu_people"], attachment_dir="data/attachments") 

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
        self,
        enable_vision: bool = True,
        vision_model: str = "qwen-vl-plus"
    ):
        self.enable_vision = enable_vision
        self.vision_model = vision_model

        if enable_vision:
            self.vision_processor = ImageVision(model_name="qwen", model_id=vision_model)
        else:
            self.vision_processor = None

    async def run(self, news_list: List[NewsItemRawSchema]) -> List[NewsItemRawSchema]:
        """
        处理图片，返回处理后的数据列表
        """
        if self.enable_vision and self.vision_processor:
            processed_items = await self.vision_processor.process_batch(news_list)
            return processed_items
        else:
            return news_list


class ZhihuOrchestrator:
    """
    知乎数据编排器
    组合 Acquisition 和 Processing 服务
    """

    def __init__(
        self,
        enable_vision: bool = True,
        vision_model: str = "qwen-vl-plus"
    ):
        self.acquisition_service = ZhihuAcquisitionService()
        self.processing_service = ZhihuProcessingService(
            enable_vision=enable_vision,
            vision_model=vision_model
        )

    async def run(self) -> List[NewsItemRawSchema]:
        """
        执行完整流程：抓取 → 处理图片
        """
        # 1. 抓取
        raw_items = await self.acquisition_service.run()

        # 2. 处理图片
        processed_items = await self.processing_service.run(raw_items)

        return processed_items
