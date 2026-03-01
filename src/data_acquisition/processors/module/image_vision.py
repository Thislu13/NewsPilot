#
# Author: Claude Code
# Date: 2026-02-22
# Description: 图片视觉理解处理器 - 使用Qwen3-VL-Plus理解图片内容

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import List
import base64

from core.news_schemas import NewsItemRawSchema
from src.module.init_client import LLMClientFactory
from config.prompts import Image_Vision_PROMPT_CN


class ImageVision:
    """
    图片视觉理解处理器
    使用Qwen3-VL-Plus视觉语言模型理解图片内容
    将<attach_n>占位符替换为图片描述
    """

    def __init__(self,
        type: str = "llm", model: str = "qwen", model_id: str = "qwen-vl-plus",
        attachments_root: str = "data/attachments", max_concurrent: int = 5
    ):
        self.type = type
        self.model = model
        self.model_id = model_id
        self.attachments_root = Path(attachments_root)
        self.semaphore = asyncio.BoundedSemaphore(max_concurrent)


        self._client = LLMClientFactory().get_client(self.model)

    def _encode_image_to_base64(self, image_path: Path) -> str:
        """将图片编码为base64字符串"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def _understand_image(self, image_path: Path) -> str:
        """
        使用Qwen3-VL-Plus理解图片内容

        Args:
            image_path: 图片文件路径

        Returns:
            图片内容描述
        """
        try:
            # 编码图片
            image_base64 = self._encode_image_to_base64(image_path)

            # 构建提示词
            prompt = Image_Vision_PROMPT_CN["SYSTEM_PROMPT"]

            # 调用Qwen VL API
            response = await self._client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                            {"type": "text", "text": prompt}
                        ]
                    }
                ],
                temperature=0.3,
            )

            content = response.choices[0].message.content if response.choices else ""
            return content.strip() if content else "图片内容无法识别"

        except Exception as e:
            return "图片理解失败"

    async def process_single(self, news_item: NewsItemRawSchema) -> NewsItemRawSchema:
        """
        处理单个新闻项，理解图片内容并存储在attachments的caption字段

        Args:
            news_item: 新闻项

        Returns:
            处理后的新闻项（attachments中添加了图片描述，body保持占位符不变）
        """
        body = news_item.body or ""
        attachments = news_item.attachments or []

        if not attachments:
            return news_item

        # 查找所有<attach_n>占位符
        pattern = r'<attach_(\d+)>'
        matches = list(re.finditer(pattern, body))

        if not matches:
            return news_item

        # 处理每个图片，将描述存储在attachment的caption字段
        updated_attachments = list(attachments)  # 创建副本
        for match in matches:
            idx = int(match.group(1))
            if idx < len(updated_attachments):
                att = updated_attachments[idx]
                if att.type == "image" and att.file_id:
                    # 构建图片路径
                    image_path = self.attachments_root / att.file_id

                    if image_path.exists():
                        # 理解图片内容
                        async with self.semaphore:
                            description = await self._understand_image(image_path)

                        # 更新attachment的caption字段
                        updated_attachments[idx] = att.model_copy(
                            update={"caption": description}
                        )
                    else:
                        updated_attachments[idx] = att.model_copy(
                            update={"caption": "图片文件不存在"}
                        )

        # 返回修改后的新闻项（body保持不变，只更新attachments）
        return news_item.model_copy(update={"attachments": updated_attachments})

    async def vision_batch(self, news_items: List[NewsItemRawSchema]) -> List[NewsItemRawSchema]:
        """
        批量处理新闻项

        Args:
            news_items: 新闻项列表

        Returns:
            处理后的新闻项列表
        """
        if not news_items:
            return []

        tasks = [self.process_single(item) for item in news_items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_items = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_items.append(news_items[i])  # 保留原始项
            else:
                processed_items.append(result)

        return processed_items



