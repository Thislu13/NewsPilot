#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-01-25 19:35:19
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-01-31 20:34:32
# FilePath: \NewsPilot\src\data_acquisition\module\get_content.py
# Description: 内容获取工具模块
# 
# Copyright (c) 2026 by , All Rights Reserved. 

from typing import List, Dict, Any, Set, Tuple


from core.news_schemas import NewsItemRawSchema

from src.data_acquisition.module.get_article_from_url import fetch_full_article_by_url
from src.module.tools import extract_host

def _enrich_single_item(
    raw_item: NewsItemRawSchema,
    result: Dict[str, Any],
) -> NewsItemRawSchema:
    if result.get("success"):
        raw_item["body"] = result.get("body") or raw_item.get("body")
        raw_item["title"] = result.get("title") or raw_item.get("title")
        raw_item["authors"] = result.get("authors") or raw_item.get("authors")
        raw_item["published_at"] = result.get("published_at") or raw_item.get("published_at")
    else:
        # print(f"无法丰富内容，URL: {raw_item['url']}，错误: {result.get('error')}")
        pass
    return raw_item





def _build_domain_batch(
    items: List[NewsItemRawSchema],
    remaining: Set[int],
) -> Tuple[List[str], List[int]]:
    """从 remaining 中取出一批 URL：每个 host 只取 1 条。"""

    seen_hosts: Set[str] = set()
    url_list: List[str] = []
    index_list: List[int] = []

    for idx in sorted(remaining):
        item = items[idx]
        url = item.get("source_url")
        if not url:
            continue

        host = extract_host(url)
        if not host:
            continue

        if host in seen_hosts:
            continue

        seen_hosts.add(host)
        url_list.append(url)
        index_list.append(idx)

    return url_list, index_list


def enrich_full_content(raw_item: List[NewsItemRawSchema]) -> List[NewsItemRawSchema]:
    """
    使用外部服务丰富新闻的完整内容。
    """
    remaining: Set[int] = set()
    for idx, item in enumerate(raw_item):
        if item.get("source_url"):
            remaining.add(idx)

    while remaining:
        url_list, index_list = _build_domain_batch(raw_item, remaining)
        if not url_list:
            break

        # 本轮批次处理完的 idx 从 remaining 移除
        for idx in index_list:
            remaining.discard(idx)

        full_content_results = fetch_full_article_by_url(url_list)
        for idx, result in zip(index_list, full_content_results):
            raw_item[idx] = _enrich_single_item(raw_item[idx], result)

    return raw_item

            







    

