"""共享 AsyncOpenAI 客户端（单例）— Qwen"""
from typing import Optional
from openai import AsyncOpenAI
from src.module.init_client import LLMClientFactory

_shared_client: Optional[AsyncOpenAI] = None


def get_shared_client() -> AsyncOpenAI:
    """获取共享的 Qwen AsyncOpenAI 客户端（懒初始化）"""
    global _shared_client
    if _shared_client is None:
        factory = LLMClientFactory()
        _shared_client = factory.get_client("qwen")
    return _shared_client


async def close_shared_client():
    """关闭共享客户端"""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.close()
        _shared_client = None
