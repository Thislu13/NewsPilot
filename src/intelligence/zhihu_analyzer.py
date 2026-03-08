#
# Author: Claude Code
# Date: 2026-02-22
# Description: 知乎内容分析器 - 专注于LLM分析逻辑

from __future__ import annotations

import asyncio
from typing import Any

from src.module.init_client import LLMClientFactory
from config.zhihu_user_config import get_author_config
from google.genai import types
from src.custom_logging import get_logger

logger = get_logger(__name__)


class ZhihuAnalyzer:
    """
    知乎内容分析器
    职责：使用LLM对知乎文章进行深度分析，返回markdown格式的分析结果
    """

    def __init__(self, model_name: str = "gemini", model_id: str | None = None):
        self.model_name = model_name
        self.model_id = model_id
        self.llm_client = LLMClientFactory().get_client(model_name)

    def _resolve_model_id(self) -> str:
        """解析模型ID"""
        if self.model_id:
            return self.model_id
        if self.model_name == "gemini":
            return "gemini-3-pro-preview"
        if self.model_name == "deepseek":
            return "deepseek-chat"
        if self.model_name == "qwen":
            return "qwen-flash"
        if self.model_name == "gpt":
            return "gpt-4o-mini"
        return self.model_name

    async def analyze_single(
        self,
        title: str,
        body: str,
        source_url: str,
        author: str = None
    ) -> str:
        """
        分析单篇知乎文章

        Args:
            title: 文章标题
            body: 文章正文（已经过图片理解处理）
            source_url: 原文链接
            author: 作者标识符（用于选择对应的prompt）

        Returns:
            markdown格式的分析结果
        """
        # Get author-specific configuration
        author_config = get_author_config(author)
        prompt_config = author_config["prompt"]

        system_prompt = prompt_config["SYSTEM_PROMPT"]
        user_prompt = prompt_config["USER_PROMPT_TEMPLATE"].format(
            source_url=source_url,
            title=title,
            body=body,
        )

        model_id = self._resolve_model_id()

        try:
            if self.model_name == "gemini":
                return await self._analyze_with_gemini(system_prompt, user_prompt, model_id)
            else:
                return await self._analyze_with_openai_compatible(system_prompt, user_prompt, model_id)
        except Exception as e:
            logger.error(f"[ZhihuAnalyzer] LLM request failed: {type(e).__name__}: {e}")
            return "# 分析失败\n\n模型调用异常。"

    async def _analyze_with_gemini(self, system_prompt: str, user_prompt: str, model_id: str) -> str:
        """使用Gemini模型进行分析"""
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        def _call_gemini() -> Any:
            return self.llm_client.models.generate_content(
                model=model_id,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="high"),
                    tools=[{"google_search": {}}],
                    temperature=0.3,
                    max_output_tokens=100000
                ),
            )

        response = await asyncio.to_thread(_call_gemini)
        content = getattr(response, "text", None) or ""
        return content or "# 分析失败\n\n未获得有效输出。"

    async def _analyze_with_openai_compatible(self, system_prompt: str, user_prompt: str, model_id: str) -> str:
        """使用OpenAI兼容模型进行分析"""
        response = await self.llm_client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            stream=False,
        )
        content = response.choices[0].message.content if response.choices else ""
        return content or "# 分析失败\n\n未获得有效输出。"


