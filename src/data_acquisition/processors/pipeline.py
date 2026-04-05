#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-09 21:38:09
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-01 21:33:10
# FilePath: \NewsPilot\src\data_acquisition\processors\pipeline.py
# Description: 新闻处理流水线 - 翻译、摘要、向量化
# 
# Copyright (c) 2026 by , All Rights Reserved. 

# src/processors/pipeline.py
import asyncio
from typing import List

from core.news_schemas import NewsItemRawSchema, NewsItemRefinedSchema
from .module import Translator, Summarizer, align_news_lists, ImageVision


NewsProcessingPipeline_DEFAULT_CONFIG = {
    "image_vision": {
        'flag': True,
        'model': "qwen",
        'model_id': "qwen-vl-plus",
        'attachments_root': "data/attachments",
        'max_concurrent': 5
    },
    "translator": {
        'flag': True,
        'model': "qwen",
        'model_id': "qwen-flash",
        'target_language': "zh",
        'max_concurrent': 5
    },
    "summarizer": {
        'flag': True,
        'model': "deepseek",
        'model_id': "deepseek-chat",
        'max_concurrent': 5
    },
    "embedding": {
        'flag': False,
        'model': "qwen",
        'model_id': "text-embedding-v4",
        'dimensions': 1024,
        'encoding_format': "float",
        'max_concurrent': 5
    }
}

class NewsProcessingPipeline:
    """
    新闻处理流水线：图片识别 -> 翻译 -> 摘要 -> 向量化
    - 图片识别：从新闻中的图片提取文字和核心信息，丰富新闻内容
    - 翻译：将新闻标题、摘要、正文翻译成指定语言（默认为中文）
    - 摘要：生成新闻摘要，提取关键信息
        - 向量化：基于摘要生成文本向量，便于后续的相似度计算和检索(依赖摘要结果)
        - 对齐：确保翻译和摘要结果的顺序和数量一致，返回对齐后的原始新闻和精炼新闻列表

     - 结果返回：返回处理后的新闻列表，包括原始新闻和精炼新闻
    
    note: 处理流程中的每个步骤都是可选的，可以根据需要启用或禁用特定的处理模块。
     - 例如，知乎文章只需要图片识别模块，返回raw_items和空的refined_items
    """

    def __init__(
        self,
        newspilot_config: dict = NewsProcessingPipeline_DEFAULT_CONFIG
    ):
        self._validate_config(newspilot_config)
        self._read_config(newspilot_config)


    def run(self, raw_item: List[NewsItemRawSchema]) -> dict:
        """
        同步接口（外部调用），内部使用 asyncio.run
        """
        return asyncio.run(self.process_async(raw_item))


    async def process_async(
        self, raw_item: List[NewsItemRawSchema]
    ) -> dict:
        """
        异步批量处理新闻：
        1. 图片识别
        2. 翻译标题、摘要、正文
        3. 生成摘要
            3-1. 生成 Embedding(依赖摘要结果)
            3-2. 对齐翻译和摘要结果，确保顺序和数量一致
        4. 返回处理结果
        """
        refined_items: List[NewsItemRefinedSchema] = []
        
        if self.image_vision_flag == True:
            # 异步图片识别
            raw_items = await self.image_vision.vision_batch(raw_item)
        if self.translotor_flag == True:
            # 异步翻译
            raw_items = await self.translator.translate_batch(raw_items)
        if self.summarizer_flag == True:
            # 异步生成摘要
            refined_items = await self.summarizer.summarize_batch(raw_items)
            # 对齐翻译和摘要结果，确保顺序和数量一致, 返回的是(aligned_raw, aligned_refined)
            raw_items, refined_items = align_news_lists(raw_items, refined_items)


        pipeline_result = {
            "raw_items": raw_items,
            "refined_items": refined_items,
        }
        return pipeline_result

    async def close(self):
        """显式关闭资源"""
        if self.image_vision_flag == True:
            await self.image_vision.close()
        if self.translotor_flag == True:
            await self.translator.close()
        if self.summarizer_flag == True:
            await self.summarizer.close()
    
    def _validate_config(self, config: dict):
        """验证配置的有效性"""
        required_keys = ["image_vision", "translator", "summarizer", "embedding"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing config key: {key}")
            
    def _read_config(self, config: dict):
        """从配置字典中读取参数并初始化模块"""
        self.image_vision_flag = config["image_vision"]["flag"]
        self.translotor_flag = config["translator"]["flag"]
        self.summarizer_flag = config["summarizer"]["flag"]

        if self.image_vision_flag:
            self.image_vision = ImageVision(
                model=config["image_vision"]["model"],
                model_id=config["image_vision"]["model_id"],
                attachments_root=config["image_vision"]["attachments_root"],
                max_concurrent=config["image_vision"]["max_concurrent"]
            )
        if self.translotor_flag:
            self.translator = Translator(
                model_name=config["translator"]["model"],
                model_id=config["translator"]["model_id"],
                target_language=config["translator"]["target_language"],
                max_concurrent=config["translator"]["max_concurrent"]
            )
        if self.summarizer_flag:
            self.summarizer = Summarizer(
                model_name=config["summarizer"]["model"],
                model_id=config["summarizer"]["model_id"],
                max_concurrent=config["summarizer"]["max_concurrent"]
            )
