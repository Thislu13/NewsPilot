"""事件提取模块 — 从 refined_news 提取独立事件并生成 embedding"""
import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from tqdm.asyncio import tqdm_asyncio

from config.prompts.event_extraction_prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from src.module.init_client import LLMClientFactory
from src.graph.embedder import generate_embedding
from src.graph.schema import EventItem


class EventExtractor:
    def __init__(self, model_id: str = "qwen-flash", max_concurrent: int = 5):
        self.model_id = model_id
        self.semaphore = asyncio.BoundedSemaphore(max_concurrent)
        factory = LLMClientFactory()
        self._client = factory.get_client("qwen")

    async def close(self):
        if self._client:
            await self._client.close()

    async def extract_from_refined(self, title: str, abstract: Optional[str],
                                   source_news_id: str, source_channel: str,
                                   source_url: str, categories, published_at,
                                   fetched_at) -> List[EventItem]:
        """从单条 refined_news 提取事件并生成 embedding"""
        event_texts = await self._extract_events(title, abstract)
        events = []
        for text in event_texts:
            embedding = await generate_embedding(text)
            events.append(EventItem(
                event_id=str(uuid.uuid4()),
                source_news_id=source_news_id,
                source_channel=source_channel,
                source_url=source_url,
                categories=categories,
                event_text=text,
                embedding=embedding,
                published_at=published_at,
                fetched_at=fetched_at,
                created_at=datetime.now(timezone.utc),
            ))
        return events

    async def _extract_events(self, title: str, abstract: Optional[str]) -> List[str]:
        for attempt in range(3):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                    title=title or "",
                    abstract=abstract or ""
                )},
            ]
            try:
                response = await self._client.chat.completions.create(
                    model=self.model_id,
                    messages=messages,
                    temperature=0.1,
                    extra_body={"enable_thinking": False},
                )
                content = (response.choices[0].message.content or "").strip()
                json_text = self._extract_json(content)
                if not json_text:
                    continue
                data = json.loads(json_text)
                events = data.get("events", [])
                if isinstance(events, list):
                    return [str(e).strip() for e in events if str(e).strip()]
                return []
            except Exception:
                continue
        return []

    @staticmethod
    def _extract_json(text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        match = re.search(r"\{[\s\S]*\}", text)
        return match.group(0) if match else ""
