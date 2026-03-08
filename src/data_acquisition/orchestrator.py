#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-07 22:40:42
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-02 20:06:06
# FilePath: \NewsPilot\src\data_acquisition\orchestrator.py
# Description: 新闻采集编排器 - 统一管理新闻抓取流程
# 
# Copyright (c) 2026 by , All Rights Reserved. 
import asyncio
import json

from typing import List, Optional, Union, Iterable

from src.data_acquisition.fetchers.newsapi_fetcher import NewsAPIFetcher
from src.data_acquisition.fetchers.rsshub_fetcher import RSSHubFetcher
from src.data_acquisition.processors.pipeline import NewsProcessingPipeline
from core.news_schemas import NewsItemRawSchema, NewsItemRefinedSchema

from config import keys, settings



class NewsAcquisitionService:
    """
    统一管理新闻抓取流程
    """

    def __init__(self, config: dict = settings.NEWS_SOURCES_CONFIG, attachments_root: str = "data/attachments"):

        self.fetchers = {
            "newsapi": NewsAPIFetcher(api_key=keys.newsapi_api, ),
            "rsshub": RSSHubFetcher(
                choices=config.get("reuters", {}).get("choice", []),
                attachment_dir=attachments_root
            )
            # "reuters": ReutersFetcher(...),
        }
        self.sources = config.keys()


    async def run(self) -> List[NewsItemRawSchema]:
        all_news: List[NewsItemRawSchema] = []

        for name, fetcher in self.fetchers.items():
            if self.sources and name not in self.sources:
                continue
            items = await fetcher.fetch_and_normalize()
            all_news.extend(items)
        return all_news
    

class NewsProcessingService:
    """
    统一管理新闻处理流程
    """

    def __init__(self, newspilot_config = settings.NewsProcessingPipeline_DEFAULT_CONFIG):
        self.pipeline = NewsProcessingPipeline(newspilot_config=newspilot_config)

    async def run(self, news_list: List[NewsItemRawSchema]) -> dict:
        
        pipeline_result = await self.pipeline.process_async(news_list)
        return pipeline_result



class NewsDataOrchestrator():
    def __init__(self, news_config: dict = settings.NEWS_SOURCES_CONFIG, attachments_root: str = "data/attachments"):
        self.news_config = news_config
        self.attachments_root = attachments_root
        self.m_init()

    def m_init(self):
        self.source = self.news_config.get('source', 'newsapi')
        self.ewspilot_config = settings.NewsProcessingPipeline_DEFAULT_CONFIG


        self.news_acquisition_service = NewsAcquisitionService(sources=self.source)
        self.news_processing_service = NewsProcessingService(newspilot_config=self.ewspilot_config)

    async def run_async(self) -> tuple[List[NewsItemRawSchema], dict]:
        news_items_raw = await self.news_acquisition_service.run()
        pipeline_result = await self.news_processing_service.run(news_items_raw)
        
        return news_items_raw, pipeline_result

    def run(self) -> tuple[List[NewsItemRawSchema], dict]:
        return asyncio.run(self.run_async())
