#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-09 22:52:52
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-02-06 01:48:21
# FilePath: \NewsPilot\src\module\init_client.py
# Description: LLM 客户端初始化工厂
# 
# Copyright (c) 2026 by , All Rights Reserved. 

from openai import AsyncOpenAI, api_key
from google import genai
from config import keys

class LLMClientFactory:
    """
    单独封装 LLM 客户端初始化
    """

    def __init__(self):
        self.client_init = {
            "gpt": self._init_gpt,
            "deepseek": self._init_deepseek,
            "gemini": self._init_gemini,
            "qwen": self._init_qwen,
        }

    def get_client(self, model_name: str) ->AsyncOpenAI:
        """
        返回初始化好的 client
        """
        if model_name not in self.client_init:
            raise ValueError(f"Unsupported model: {model_name}")
        return self.client_init[model_name]()

    # ----------------- 初始化不同模型 -----------------
    def _init_gpt(self) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=keys.openai_api)
    
    def _init_deepseek(self) ->AsyncOpenAI:
        return AsyncOpenAI(api_key=keys.deepseek_api, base_url="https://api.deepseek.com")
    
    def _init_gemini(self) -> genai.Client:
        return genai.Client(api_key=keys.gemini_api)
    
    def _init_qwen(self) -> AsyncOpenAI:
        return AsyncOpenAI(api_key=keys.qwen_api, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")