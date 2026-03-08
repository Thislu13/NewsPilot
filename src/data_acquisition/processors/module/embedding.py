#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+#+########
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-06
# FilePath: \NewsPilot\src\data_acquisition\processors\module\embedding.py
# Description: embedding 生成模块
# 
# Copyright (c) 2026 by , All Rights Reserved. 

import asyncio
from typing import List, Optional
from tqdm.asyncio import tqdm_asyncio

from core.news_schemas import NewsItemRefinedSchema
from src.module.init_client import LLMClientFactory
from src.custom_logging import get_logger

logger = get_logger(__name__)


class EmbeddingGenerator:
	"""
	新闻 Embedding 模块：异步生成向量
	目前仅支持 qwen embedding
	"""

	def __init__(
		self,
		type: str = "llm", model_name: str = "qwen", model_id: str = "text-embedding-v4",
		dimensions: int = 1024, encoding_format: str = "float", max_concurrent: int = 5
	):
		self.type = type
		self.model_name = model_name
		self.model_id = model_id
		self.dimensions = dimensions
		self.encoding_format = encoding_format
		self.semaphore = asyncio.BoundedSemaphore(max_concurrent)

		if self.type == "llm":
			factory = LLMClientFactory()
			self._client = factory.get_client(model_name)

	async def close(self):
		if hasattr(self, "_client") and self._client:
			await self._client.close()



	async def llm_embed_async(self, news_item: NewsItemRefinedSchema) -> NewsItemRefinedSchema:
		text = news_item.abstract
		if self.model_name == 'qwen':
			embedding = await self.qwen_embedding(text, model_id=self.model_id)
		else:
			raise ValueError(f"Unsupported embedding model: {self.model_name}")
    
		return NewsItemRefinedSchema(
			unique_id=news_item.unique_id,
			source_id=news_item.source_id,
			source_channel=news_item.source_channel,
			source_url=news_item.source_url,
			NewsItemRaw_id=news_item.NewsItemRaw_id,
			published_at=news_item.published_at,
			fetched_at=news_item.fetched_at,
			title=news_item.title,
			abstract=news_item.abstract,
			categories=news_item.categories,
			embedding=embedding,
			evaluation_score=news_item.evaluation_score,
			extra_data=news_item.extra_data,
		)

	async def embed_batch(self, news_list: List[NewsItemRefinedSchema]) -> List[NewsItemRefinedSchema]:
		"""
		异步批量生成 embedding
		"""

		async def safe_embed(item: NewsItemRefinedSchema) -> NewsItemRefinedSchema:
			async with self.semaphore:
				try:
					if self.type == "llm":
						return await self.llm_embed_async(item)
				except Exception as e:
					logger.error(f"Embedding failed for item {item.unique_id}: {e}")
					return item  # 失败时返回原对象

			return item

		tasks = [safe_embed(item) for item in news_list]
		return await tqdm_asyncio.gather(
			*tasks,
			desc="Embedding news",
			total=len(tasks),
		)

	async def qwen_embedding(self, text: str, model_id: str = "text-embedding-v4") -> Optional[List[float]]:
		if not text:
			return None

		response = await self._client.embeddings.create(
			model=model_id,
			input=text,
			dimensions=self.dimensions,
			encoding_format=self.encoding_format,
		)

		if not hasattr(response, "data") or not response.data:
			return None

		return response.data[0].embedding
