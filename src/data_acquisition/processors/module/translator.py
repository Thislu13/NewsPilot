#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-09 23:37:21
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-01 20:42:51
# FilePath: \NewsPilot\src\data_acquisition\processors\module\translator.py
# Description: 新闻翻译模块 - 使用 LLM 进行翻译
# 
# Copyright (c) 2026 by , All Rights Reserved. 

import asyncio
import json
import re
from typing import List, Tuple, Any
from tqdm.asyncio import tqdm_asyncio

from core.news_schemas import NewsItemRawSchema, NewsItemRefinedSchema
from src.module.init_client import LLMClientFactory
from config.prompts import  TRANSLATION_BATCH_PROMPT_CN
from src.module.tools import normalize_text

class Translator:
    """
    新闻翻译模块：异步翻译标题、摘要、正文
    """

    def __init__(self, 
                 type: str = "llm", model_name: str = "qwen", model_id: str = "qwen-flash",
                 target_language: str = "zh", max_concurrent: int = 5):
        self.type = type
        self.model_name = model_name
        self.model_id = model_id
        self.target_language = target_language
        self.semaphore = asyncio.BoundedSemaphore(max_concurrent)  # 控制并发数量

        if self.type == "llm":
            factory = LLMClientFactory()
            self._client = factory.get_client(model_name)

    async def close(self):
        if hasattr(self, '_client') and self._client:
            await self._client.close()

    async def llm_translate_async(self, news_item: NewsItemRawSchema) -> NewsItemRawSchema:
        """
        异步翻译单条新闻的标题、摘要、正文 (Batch Mode)
        """
        system_prompt = TRANSLATION_BATCH_PROMPT_CN["SYSTEM_PROMPT"]
        
        user_prompt = TRANSLATION_BATCH_PROMPT_CN["USER_PROMPT_TEMPLATE"].format(
            target_language=self.target_language,
            title=normalize_text(news_item.title or ""),
            abstract=normalize_text(news_item.abstract or ""),
            body=normalize_text(news_item.body or "")
        )

        translated_title, translated_abstract, translated_body = "", "", ""
        if self.model_name == 'deepseek':
            translated_title, translated_abstract, translated_body = await self.deepseek_translate(
                system_prompt,
                user_prompt,
                model_id = self.model_id
            )
        elif self.model_name == 'gemini':
            raise NotImplementedError("Gemini 翻译尚未实现")
        elif self.model_name == 'gpt':
            raise NotImplementedError("GPT 翻译尚未实现")
        elif self.model_name == 'qwen':
            translated_title, translated_abstract, translated_body = await self.deepseek_translate(
                system_prompt,
                user_prompt,
                model_id = self.model_id
            )

        if not translated_title :
            translated_title = news_item.title or ""
        if not translated_abstract:
            translated_abstract = news_item.abstract or ""
        if not translated_body:
            translated_body = news_item.body or ""
        # 构建返回结果
        refined_item = NewsItemRawSchema(
            unique_id=news_item.unique_id,
            source_id=news_item.source_id,
            source_channel=news_item.source_channel,
            source_url=news_item.source_url,
            published_at=news_item.published_at,
            fetched_at=news_item.fetched_at,
            title=translated_title,
            abstract=translated_abstract,
            body=translated_body,
            authors=news_item.authors,
            categories=news_item.categories,
            attachments=news_item.attachments,
            supportingDocument_id=news_item.supportingDocument_id,
            evaluation_score=news_item.evaluation_score,
            extra_data=news_item.extra_data,
        )

        return refined_item

    async def translate_batch(self, news_list: List[NewsItemRawSchema]) -> List[NewsItemRawSchema]:
        """
        异步批量翻译，使用 asyncio.gather 并发处理
        """
        async def safe_translate(item):
            async with self.semaphore:
                try:
                    if self.type == "llm":
                        return await self.llm_translate_async(item)
                except Exception as e:
                    print(f"Translation failed for item {item.unique_id}: {e}")
                    return item  # 失败时返回原文，保证流程不中断

        tasks = [safe_translate(item) for item in news_list]
        return await tqdm_asyncio.gather(
            *tasks,
            desc="Translating news",
            total=len(tasks)
        )
    
    def _extract_json_object(self, text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        match = re.search(r"\{[\s\S]*\}", text)
        return match.group(0) if match else ""

    def _validate_payload(self, payload: Any) -> Tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, "输出不是字典类型"
        return True, ""

    async def deepseek_translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str ,
    ) -> Tuple[str, str, str]:
        last_content = ""
        last_error = ""
        for _ in range(2):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            if last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": f"上一条输出无效：{last_error}。请严格按要求重新输出 JSON 字典，包含 translated_title, translated_abstract, translated_body。",
                    }
                )
            
            try:
                response = await self._client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    temperature=0.1,
                    # response_format={"type": "json_object"}
                )
                content = (response.choices[0].message.content or "").strip()
                last_content = content

                json_text = self._extract_json_object(content)
                if not json_text:
                    last_error = "未找到 JSON 对象"
                    continue

                data = json.loads(json_text)
                
                ok, err = self._validate_payload(data)
                if not ok:
                    last_error = err
                    continue

                return (
                    str(data.get("translated_title", "") or ""),
                    str(data.get("translated_abstract", "") or ""),
                    str(data.get("translated_body", "") or "")
                )
            except Exception as e:
                last_error = str(e)
                continue

        return "", "", ""
