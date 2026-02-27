#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-09 21:40:37
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-01-31 18:03:59
# FilePath: \NewsPilot\src\data_acquisition\processors\module\summarizer.py
# Description: 新闻摘要模块 - 使用 LLM 生成摘要
# 
# Copyright (c) 2026 by , All Rights Reserved. 

import asyncio
from tqdm.asyncio import tqdm_asyncio
from typing import List, Tuple, Any
import json
import re

from core.news_schemas import NewsItemRawSchema, NewsItemRefinedSchema
from src.module.init_client import LLMClientFactory
from config.prompts import REFINE_CLASSIFY_SCORE_PROMPT_CN
from src.module.tools import generate_uuid7
    


class Summarizer:
    def __init__(self, type: str = "llm", model_name: str = "deepseek"):
        """
        新闻摘要模块：异步生成摘要，分类，评分
        """
        self.type = type
        self.model_name = model_name

        if self.type == "llm":
            factory = LLMClientFactory()
            self._client = factory.get_client(model_name)

    async def close(self):
        if hasattr(self, '_client') and self._client:
            await self._client.close()

    async def llm_summarize_async(self, news_item: NewsItemRawSchema) -> NewsItemRefinedSchema:
        system_prompt = REFINE_CLASSIFY_SCORE_PROMPT_CN["SYSTEM_PROMPT"]
        user_prompt = REFINE_CLASSIFY_SCORE_PROMPT_CN["USER_PROMPT_TEMPLATE"].format(
            title=news_item.title or "",
            abstract=news_item.abstract or "",
            body=news_item.body or "",
        )

        abstract, categories, score = "", ["other"], 50
        if self.model_name == 'deepseek':
            model_id = "deepseek-chat"
            abstract, categories, score = await self.deepseek_refine_classify_score(
                system_prompt,
                user_prompt,
                model_id=model_id,
            )
        elif self.model_name == 'gemini':
            raise NotImplementedError("Gemini 摘要尚未实现")
        elif self.model_name == 'gpt':
            raise NotImplementedError("GPT 摘要尚未实现")
        else:
            raise ValueError(f"Unsupported translation model: {self.model_name}")


        refined_item = NewsItemRefinedSchema(
            unique_id=str(generate_uuid7()),
            source_id=news_item.source_id,
            source_channel=news_item.source_channel,
            source_url=news_item.source_url,
            NewsItemRaw_id=news_item.unique_id,
            published_at=news_item.published_at,
            fetched_at=news_item.fetched_at,
            title=news_item.title,
            abstract=abstract,
            categories=categories,
            embedding=None, 
            evaluation_score=score,
            extra_data=news_item.extra_data,
        )
        return refined_item

    async def summarize_batch(self, news_list: List[NewsItemRawSchema]) -> List[NewsItemRefinedSchema]:
        
        semaphore = asyncio.BoundedSemaphore(5)
        async def safe_summarize(item):
            async with semaphore:
                try:
                    if self.type == "llm":
                        return await self.llm_summarize_async(item)
                except Exception as e:
                    print(f"Summarization failed for item {item.unique_id}: {e}")
                    return None  # 失败时返回 None，后续需要清洗掉

        tasks = [safe_summarize(item) for item in news_list]
        results = await tqdm_asyncio.gather(
            *tasks,
            desc="Summarizing news",
            total=len(tasks)
        )
        # 过滤掉失败的 None 结果
        return [r for r in results if r is not None]

    def _extract_json_object(self, text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        match = re.search(r"\{[\s\S]*\}", text)
        return match.group(0) if match else ""

    def _coerce_score(self, value: Any) -> int:
        try:
            score = int(round(float(value)))
        except Exception:
            score = 50
        return max(0, min(100, score))

    def _coerce_categories(self, value: Any) -> List[str]:
        allowed = {
            "policy_regulation",
            "macro_economy",
            "markets",
            "company_business",
            "technology",
            "energy_commodities",
            "geopolitics",
            "society_public_safety",
            "environment_climate",
            "health_medicine",
            "other",
        }
        if isinstance(value, str):
            types = [value]
        elif isinstance(value, list):
            types = [str(x) for x in value if x is not None]
        else:
            types = []

        cleaned: List[str] = []
        for t in types:
            t = t.strip()
            if not t:
                continue
            if t in allowed and t not in cleaned:
                cleaned.append(t)
            if len(cleaned) >= 3:
                break

        return cleaned or ["other"]

    def _validate_payload(self, payload: Any) -> Tuple[bool, str]:
        if not isinstance(payload, dict):
            return False, "输出不是字典类型"

        keys = set(payload.keys())
        if keys != {"abstract", "categories", "score"}:
            return False, "字典键必须且只能包含 abstract, categories, score"

        categories = payload.get("categories")
        if not isinstance(categories, list) or not (1 <= len(categories) <= 3):
            return False, "categories 必须是长度 1-3 的列表"

        cleaned = self._coerce_categories(categories)
        if not cleaned or cleaned == ["other"] and categories != ["other"]:
            return False, "categories 不在允许范围"

        score = payload.get("score")
        try:
            s = int(round(float(score)))
        except Exception:
            return False, "score 必须是数字"
        if not (0 <= s <= 100):
            return False, "score 必须在 0-100"

        abstract = payload.get("abstract")
        if not isinstance(abstract, str) or not abstract.strip():
            return False, "abstract 必须是非空字符串"

        return True, ""

    async def deepseek_refine_classify_score(
        self,
        system_prompt: str,
        user_prompt: str,
        model_id: str = "deepseek-chat",
    ) -> Tuple[str, List[str], int]:
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
                        "content": f"上一条输出无效：{last_error}。请严格按要求重新输出 JSON 字典，只包含 abstract, categories, score。",
                    }
                )

            response = await self._client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0.2,
            )
            content = (response.choices[0].message.content or "").strip()
            last_content = content

            json_text = self._extract_json_object(content)
            if not json_text:
                last_error = "未找到 JSON 对象"
                continue

            try:
                data = json.loads(json_text)
            except Exception:
                last_error = "JSON 解析失败"
                continue

            ok, err = self._validate_payload(data)
            if not ok:
                last_error = err
                continue

            abstract = str(data.get("abstract", "") or "").strip()
            categories = self._coerce_categories(data.get("categories"))
            score = self._coerce_score(data.get("score"))
            return abstract, categories, score

        return last_content or "", ["other"], 50