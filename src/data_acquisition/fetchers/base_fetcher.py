#
# Author: WangQiushuo 185886867@qq.com
# Date: 2025-12-19 22:27:00
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-01-07 23:20:33
# FilePath: \NewsPilot\src\data_acquisition\fetchers\base_fetcher.py
# Description: 基础新闻采集器抽象类
# 
# Copyright (c) 2026 by , All Rights Reserved. 

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from core.news_schemas import NewsItemRawSchema, Attachment

class BaseFetcher(ABC):
    """
    所有新闻抓取器的抽象基类。
    """
    @property
    @abstractmethod
    def SOURCE_NAME(self) -> str:
        """抓取器名称，必须由子类实现"""
        pass

    @property
    @abstractmethod
    def SOURCE_TYPE(self) -> str:
        """抓取器类型 (API, Web Scraper, RSS)"""
        pass
    
    @abstractmethod
    async def fetch_raw_data(self) -> List[Dict[str, Any]]:
        """
        异步地从外部源获取原始数据。
        返回的数据应是原始、未规范化的字典列表。
        """
        pass
        
    @abstractmethod
    def normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NewsItemRawSchema]:
        """
        将单个原始数据字典转换为标准的 NewsItemRawSchema 实例。
        这个方法应处理所有的数据清洗和格式转换。
        """
        pass
        
    async def fetch_and_normalize(self) -> List[NewsItemRawSchema]:
        """
        完整的工作流：抓取原始数据并进行规范化。
        """
        raw_list = await self.fetch_raw_data()
        normalized_list = []
        for raw_item in raw_list:
            normalized_item = self.normalize_data(raw_item)
            if normalized_item:
                normalized_list.append(normalized_item)
        return normalized_list