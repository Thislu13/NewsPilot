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
        'model': "qwen",
        'model_id': "qwen-flash",
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
    新闻处理流水线：图片识别 -> 翻译 -> 摘要 -> 事件提取+embedding
    """

    def __init__(
        self,
        newspilot_config: dict = NewsProcessingPipeline_DEFAULT_CONFIG
    ):
        self._validate_config(newspilot_config)
        self._read_config(newspilot_config)


    def run(self, raw_item: List[NewsItemRawSchema]) -> dict:
        return asyncio.run(self.process_async(raw_item))


    async def process_async(
        self, raw_item: List[NewsItemRawSchema]
    ) -> dict:
        """
        异步批量处理新闻：
        1. 图片识别
        2. 翻译标题、摘要、正文
        3. 生成摘要 + 对齐
        4. 事件提取 + embedding → 写入 candidate_events
        """
        refined_items: List[NewsItemRefinedSchema] = []

        if self.image_vision_flag == True:
            raw_items = await self.image_vision.vision_batch(raw_item)
        if self.translotor_flag == True:
            raw_items = await self.translator.translate_batch(raw_items)
        if self.summarizer_flag == True:
            refined_items = await self.summarizer.summarize_batch(raw_items)
            raw_items, refined_items = align_news_lists(raw_items, refined_items)

        # Stage E: 事件提取 + embedding → 去重 → 写入
        extracted_events = []
        if self.event_extraction_flag and refined_items:
            from src.data_acquisition.processors.module.event_extractor import EventExtractor
            from src.storage.graph_repository import write_candidate_event, load_existing_event_embeddings
            from src.graph.config import DEDUP_THRESHOLD
            import numpy as np
            import logging

            logger = logging.getLogger("pipeline")
            extractor = EventExtractor()
            try:
                # 1. 提取所有事件
                for raw, refined in zip(raw_items, refined_items):
                    try:
                        events = await extractor.extract_from_refined(
                            title=refined.title,
                            abstract=refined.abstract,
                            source_news_id=refined.unique_id,
                            source_channel=refined.source_channel,
                            source_url=refined.source_url,
                            categories=refined.categories,
                            published_at=refined.published_at,
                            fetched_at=refined.fetched_at,
                        )
                        extracted_events.extend(
                            [ev for ev in events if ev.event_text and ev.embedding]
                        )
                    except Exception as e:
                        logger.warning(f"事件提取失败 (news={refined.unique_id}): {e}")

                # 2. 语义去重
                if extracted_events:
                    existing_ids, existing_embs = load_existing_event_embeddings()

                    new_embs = np.array(
                        [ev.embedding for ev in extracted_events], dtype=np.float32
                    )
                    norms = np.linalg.norm(new_embs, axis=1, keepdims=True)
                    norms[norms == 0] = 1
                    new_embs_norm = new_embs / norms

                    dup_mask = np.zeros(len(extracted_events), dtype=bool)

                    # 与已有事件去重
                    if existing_embs:
                        ex_mat = np.array(existing_embs, dtype=np.float32)
                        ex_norms = np.linalg.norm(ex_mat, axis=1, keepdims=True)
                        ex_norms[ex_norms == 0] = 1
                        ex_mat_norm = ex_mat / ex_norms
                        sim_matrix = ex_mat_norm @ new_embs_norm.T
                        dup_mask |= np.any(sim_matrix >= DEDUP_THRESHOLD, axis=0)

                    # 新事件之间去重（保先去后）
                    inner_sim = new_embs_norm @ new_embs_norm.T
                    for i in range(len(extracted_events)):
                        if dup_mask[i]:
                            continue
                        for j in range(i + 1, len(extracted_events)):
                            if dup_mask[j]:
                                continue
                            if inner_sim[i, j] >= DEDUP_THRESHOLD:
                                dup_mask[j] = True

                    # 写入过滤后的事件
                    kept_count = 0
                    for idx, ev in enumerate(extracted_events):
                        if dup_mask[idx]:
                            continue
                        write_candidate_event(
                            event_id=ev.event_id,
                            source_news_id=ev.source_news_id,
                            source_channel=ev.source_channel,
                            source_url=ev.source_url,
                            categories=ev.categories,
                            event_text=ev.event_text,
                            embedding=ev.embedding,
                            published_at=ev.published_at,
                            fetched_at=ev.fetched_at,
                        )
                        kept_count += 1

                    dup_count = int(dup_mask.sum())
                    if dup_count > 0:
                        logger.info(f"事件去重: {len(extracted_events)} → {kept_count} (过滤 {dup_count} 重复)")

                    extracted_events = [
                        ev for idx, ev in enumerate(extracted_events) if not dup_mask[idx]
                    ]
            finally:
                await extractor.close()

        pipeline_result = {
            "raw_items": raw_items,
            "refined_items": refined_items,
            "extracted_events": extracted_events,
        }
        return pipeline_result

    async def close(self):
        if self.image_vision_flag == True:
            await self.image_vision.close()
        if self.translotor_flag == True:
            await self.translator.close()
        if self.summarizer_flag == True:
            await self.summarizer.close()

    def _validate_config(self, config: dict):
        required_keys = ["image_vision", "translator", "summarizer", "embedding"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing config key: {key}")

    def _read_config(self, config: dict):
        self.image_vision_flag = config["image_vision"]["flag"]
        self.translotor_flag = config["translator"]["flag"]
        self.summarizer_flag = config["summarizer"]["flag"]
        self.event_extraction_flag = config.get("event_extraction", {}).get("flag", True)

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
