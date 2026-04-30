"""Embedding 生成器（768维 text-embedding-v4）"""
from typing import List, Optional
from src.graph.client import get_shared_client
from src.graph.config import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, EMBEDDING_ENCODING_FORMAT


async def generate_embedding(text: str) -> Optional[List[float]]:
    if not text:
        return None
    client = get_shared_client()
    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            dimensions=EMBEDDING_DIMENSIONS,
            encoding_format=EMBEDDING_ENCODING_FORMAT,
        )
        if hasattr(response, "data") and response.data:
            return response.data[0].embedding
        return None
    except Exception as e:
        print(f"[ERROR] Embedding failed: {e}")
        return None
