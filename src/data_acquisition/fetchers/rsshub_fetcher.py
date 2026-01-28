#
# Author: WangQiushuo 185886867@qq.com
# Date: 2025-12-23 21:59:45
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-01-26 23:08:22
# FilePath: \NewsPilot\src\data_acquisition\fetchers\rsshub_fetcher.py
# Description: 
# 
# Copyright (c) 2026 by , All Rights Reserved. 

from typing import List, Dict, Any, Optional, Callable, Awaitable

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import traceback
import uuid
import aiohttp
import feedparser


from src.data_acquisition.fetchers.base_fetcher import BaseFetcher
from core.news_schemas import NewsItemRawSchema, Attachment

# from data_acquisition.module.get_content import enrich_full_content

class RSSHubFetcher(BaseFetcher):
    """
    RSSHub 抓取器实现
    """
    RSS_CONFIG = {
        # https://docs.rsshub.app/routes/reuters
        # 路透社
        'reuters': {
            'url':'/reuters',
            "options":[
                '/world', '/business', '/legal', '/markets', '/breakingviews', '/technology'
            ]
        },
        # https://docs.rsshub.app/routes/eastmoney
        # 东方财富网
        # 该处返回的是研报表（概述部分相对比较完整了） 
        # 其中link 中返回的直接是pdf文件链接，后续考虑增加到支撑文件中
        'eastmoney': {
            'url':'/eastmoney/report',
            "options":[
                "/strategyreport", "/macresearch", "/brokerreport", "/industry"
            ]  
        },
        # https://docs.rsshub.app/routes/bloomberg
        # 彭博社
        # 没有description 字段
        'bloomberg': {
            'url':'/bloomberg',
            "options":[
            ]  
        },
        # https://docs.rsshub.app/routes/cls
        # 财联社
        # description 字段基本基本是全文
        'cls': {
            'url':'/cls/telegraph',
            "options":[]  
        },
        # https://docs.rsshub.app/routes/bbc
        # BBC
        'bbc': {
            'url':'/bbc',
            "options":[
            ]  
        },
        # https://docs.rsshub.app/routes/ftchinese
        # FT中文网
        # description 字段基本基本是全文
        
        'ftchinese': {
            'url':'/ftchinese/simplified',
            "options":[
            ]  
        },
    }

    @property
    def SOURCE_NAME(self) -> str:
        return "RSSHub"

    @property
    def SOURCE_TYPE(self) -> str:
        return "RSS"
    
    def __init__(
        self,
        rss_url: str="http://localhost:1200",
        rss_config: Optional[Dict[str, Any]] = RSS_CONFIG,
        choices: List = None,
    ):
        self.rss_url = rss_url
        self.rss_config = rss_config or {}
        if choices:
            self.rss_config = {k:v for k,v in self.rss_config.items() if k in choices}

    def _parse_published_rfc822(self, published_at_raw: Any) -> Any:
        """解析 RSS 常见 RFC822/GMT 时间字符串为 datetime。

        示例：Mon, 26 Jan 2026 11:08:51 GMT
        - 解析成功：返回 tz-aware datetime
        - 解析失败：原样返回
        """
        if not isinstance(published_at_raw, str) or not published_at_raw:
            return published_at_raw
        try:
            published_at = parsedate_to_datetime(published_at_raw)
            if getattr(published_at, "tzinfo", None) is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            return published_at
        except Exception:
            return published_at_raw
        

    async def fetch_raw_data(self) -> List[Dict[str, Any]]:
        """
        从 rssd订阅 获取原始新闻数据

        设计：
        - 不同 RSS 入口（reuters/bloomberg/...）之间并发执行
        - 单个入口内部按 URL 串行执行（避免反扒/降压）
        """
        entry_fetchers: Dict[str, Callable[[], Awaitable[List[Dict[str, Any]]]]] = {
            "reuters": self._fetch_reuters_rss,
            "bloomberg": self._fetch_bloomberg_rss,
            "eastmoney": self._fetch_eastmoney_rss,
            "cls": self._fetch_cls_rss,
            "bbc": self._fetch_bbc_rss,
            "ftchinese": self._fetch_ftchinese_rss,
        }

        enabled_sources = [k for k in self.rss_config.keys() if k in entry_fetchers]
        if not enabled_sources:
            return []

        tasks = [entry_fetchers[source]() for source in enabled_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        articles: List[Dict[str, Any]] = []
        for source, result in zip(enabled_sources, results):
            if isinstance(result, Exception):
                # 不中断全局抓取：打印警告并跳过该源
                print(f"[WARN] RSS entry '{source}' failed: {type(result).__name__}: {result!r}")
                continue
            if result is None:
                print(f"[WARN] RSS entry '{source}' returned None; skipping")
                continue
            articles.extend(result)

        return articles
    

    async def _fetch_reuters_rss(self) -> List[Dict[str, Any]]:

        items_list = await self._get_items_list("reuters")
        articles: List[Dict[str, Any]] = []
        
        for item in items_list:
            published_at = self._parse_published_rfc822(item.get("published"))

            # 处理tag
            tags = item.get("tags", [])
            categories = [tag.get("term") for tag in tags if tag.get("term")]

            articles.append(
                {
                    'source_id': item.get("id", ""),

                    "source_channel": "Reuters",
                    "url": item.get("link"),

                    "publishedAt": published_at,
                    "fetchedAt": datetime.now(timezone.utc),

                    "title": item.get("title"),
                    "description": item.get("summary"),
                    "body": item.get("summary"),

                    "author": item.get("author"),
                    "categories" : categories,
                }
            )
        
        return articles



    async def _fetch_bloomberg_rss(self) -> List[Dict[str, Any]]:

        # Bloomberg 路由偶发较慢，单独提高超时到 60s
        items_list = await self._get_items_list("bloomberg", timeout=60)
        articles: List[Dict[str, Any]] = []
        print(f"Bloomberg items count: {len(items_list)}")

        for item in items_list:
            published_at = self._parse_published_rfc822(item.get("published"))

            articles.append(
                {
                    'source_id': item.get("id", ""),
                    
                    "source_channel": "Bloomberg",
                    "url": item.get("link"),

                    "publishedAt": published_at,
                    "fetchedAt": datetime.now(timezone.utc),

                    "title": item.get("title"),
                    "description": item.get("summary"),
                    "body": item.get("summary"),

                    "author": item.get("author"),
                    "categories" : [],
                }
            )

        
        return articles

    async def _fetch_eastmoney_rss(self) -> List[Dict[str, Any]]:
        
        items_list = await self._get_items_list("eastmoney")
        articles: List[Dict[str, Any]] = []
        
        for item in items_list:
            published_at = self._parse_published_rfc822(item.get("published"))

            articles.append(
                {
                    'source_id': item.get("link", ""),
                    
                    "source_channel": "Eastmoney",
                    "url": item.get("link"),

                    "title": item.get("title"),
                    "description": item.get("summary"),
                    "body": item.get("summary"),

                    "publishedAt": published_at,
                    "fetchedAt": datetime.now(timezone.utc),

                    "author": item.get("author"),
                    "categories" : [],

                    "attachments": [item.get("link")]
                }
            )

        return articles

    async def _fetch_cls_rss(self) -> List[Dict[str, Any]]:
        items_list = await self._get_items_list("cls")
        articles: List[Dict[str, Any]] = []
        
        for item in items_list:
            published_at = self._parse_published_rfc822(item.get("published"))
            
            # 处理tag
            tags = item.get("tags", [])
            categories = [tag.get("term") for tag in tags if tag.get("term")]

            articles.append(
                {
                    'source_id': item.get("id", ""),
                    
                    "source_channel": "CLS",
                    "url": item.get("link"),

                    "publishedAt": published_at,
                    "fetchedAt": datetime.now(timezone.utc),

                    "title": item.get("title"),
                    "description": item.get("summary"),
                    "body": item.get("summary"),

                    "author": item.get("author"),
                    "categories" : categories,
                }
            )

        return articles

    async def _fetch_bbc_rss(self) -> List[Dict[str, Any]]:
        items_list = await self._get_items_list("bbc")
        articles: List[Dict[str, Any]] = []
        for item in items_list:
            published_at = self._parse_published_rfc822(item.get("published"))

            articles.append(
                {
                    'source_id': item.get("id", ""),
                    
                    "source_channel": "BBC",
                    "url": item.get("link"),

                    "publishedAt": published_at,
                    "fetchedAt": datetime.now(timezone.utc),

                    "title": item.get("title"),
                    "description": item.get("summary"),
                    "body": item.get("summary"),

                    "author": item.get("author"),
                    "categories" : [],
                }
            )

        return articles

    async def _fetch_ftchinese_rss(self) -> List[Dict[str, Any]]:
        items_list = await self._get_items_list("ftchinese")
        articles: List[Dict[str, Any]] = []

        for item in items_list:
            published_at = self._parse_published_rfc822(item.get("published"))

            articles.append(
                {
                    'source_id': item.get("id", ""),
                    
                    "source_channel": "FTChinese",
                    "url": item.get("link"),

                    "publishedAt": published_at,
                    "fetchedAt": datetime.now(timezone.utc),

                    "title": item.get("title"),
                    "description": item.get("summary"),
                    "body": item.get("summary"),

                    "author": item.get("author"),
                    "categories" : [],
                }
            )
        # for i in range(5):
        #     item = items_list[i]
        #     print(f"Item {i+1}:")
        #     for key, value in item.items():
        #         print(f"{key}: {value}")


        return articles

    
    async def fetch_rss_items(
        self,
        rss_url: str,
        timeout: int = 15,
        retries: int = 3,
        retry_backoff_base: float = 1.0,
        retry_backoff_cap: float = 10.0,
    ) -> List[Dict]:
        """
        异步获取 RSS / Atom 并返回 entry 列表（字典形式）

        - 强制字段：title, link
        - 其余字段：按 feedparser entry 原样展开
        """
        last_exc: Optional[BaseException] = None
        for attempt in range(retries + 1):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    headers={
                        "User-Agent": "NewsPilot/0.1 (+https://github.com/Thislu13/NewsPilot)"
                    },
                ) as session:
                    async with session.get(rss_url) as resp:
                        # 对常见可恢复状态码做重试
                        if resp.status in (429, 500, 502, 503, 504):
                            raise aiohttp.ClientResponseError(
                                request_info=resp.request_info,
                                history=resp.history,
                                status=resp.status,
                                message=f"HTTP {resp.status}",
                                headers=resp.headers,
                            )
                        resp.raise_for_status()
                        content = await resp.read()
                break
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                if attempt >= retries:
                    raise
                sleep_s = min(retry_backoff_base * (2 ** attempt), retry_backoff_cap)
                print(
                    f"Fetch RSS failed (attempt {attempt + 1}/{retries + 1}) for {rss_url}: "
                    f"{type(e).__name__}: {e!r}; retrying in {sleep_s:.1f}s"
                )
                await asyncio.sleep(sleep_s)

        items: List[Dict] = []
        feed = feedparser.parse(content)
        for entry in feed.entries:
            # 1️⃣ 最小可用判断
            title = entry.get("title")
            link = entry.get("link")
            if not title or not link:
                continue
            item = {
                "title": title,
                "link": link,
            }

            # 2️⃣ 原样吸收 entry 的所有字段
            for key, value in entry.items():
                if key not in item:
                    item[key] = value
        
            items.append(item)

        return items

    def _get_urls_list(self, source_name: str) -> List[str]:
        
        config = self.rss_config.get(source_name)
        if not config:
            return []
        option = config.get("options", [])
        rss_urls = [self.rss_url + config.get("url", "") + op for op in option] or [
            self.rss_url + config.get("url", "")
        ]

        return rss_urls
    
    async def _get_items_list(self, source_name: str, timeout: int = 15) -> List[Dict[str, Any]]:
        items_list: List[Dict[str, Any]] = []
        rss_urls = self._get_urls_list(source_name)
        for rss_url in rss_urls:
            print(f"Fetching RSS from {rss_url} ...")
            try:
                items = await self.fetch_rss_items(rss_url, timeout=timeout)
            except Exception as e:
                # 某一路由失败不影响整体；按要求返回空值并给出警告
                print(
                    f"[WARN] Fetch RSS failed for source={source_name}, url={rss_url}: "
                    f"{type(e).__name__}: {e!r}; skipping"
                )
                continue
            print(f"Fetched {len(items)} items from {rss_url}")
            items_list.extend(items)
        
        return items_list
    
    def normalize_data(
        self, raw_data: Dict[str, Any]
    ) -> Optional[NewsItemRawSchema]:
        """
        将 RSSHub 抓取到的原始数据转换为 NewsItemRawSchema
        """
        # --- 基础校验 ---
        if not raw_data.get("url") or not raw_data.get("title"):
            return None

        # --- Source 信息 ---
        source_channel = raw_data.get("source_channel") or "Unknown"

        # --- 时间解析 ---
        published_at= raw_data.get("publishedAt")
        fetched_at= raw_data.get("fetchedAt") or datetime.now(timezone.utc)
        
        # --- 作者解析 ---
        authors: List[str] = []
        author_raw = raw_data.get("author")
        if isinstance(author_raw, list):
            authors = [str(a).strip() for a in author_raw if str(a).strip()]
        elif author_raw:
            authors = [a.strip() for a in str(author_raw).split(",") if a.strip()]

        # --- 分类 ---
        categories = raw_data.get("categories") or []

        # --- 附件处理 ---
        attachments: List[Attachment] = []
        raw_attachments = raw_data.get("attachments") or []
        if isinstance(raw_attachments, list):
            for att in raw_attachments:
                if isinstance(att, Attachment):
                    attachments.append(att)
                elif isinstance(att, dict):
                    try:
                        attachments.append(Attachment(**att))
                    except Exception:
                        continue
                elif isinstance(att, str) and att:
                    attachments.append(Attachment(type="file", url=att))

        # --- 构建 NewsItemRawSchema ---
        return NewsItemRawSchema(
            # 核心标识符
            unique_id=str(uuid.uuid4()),
            source_id=str(raw_data.get("source_id") or ""),

            # 溯源信息
            source_channel=source_channel,
            source_url=raw_data.get("url"),

            # 时间信息
            published_at=published_at,
            fetched_at=fetched_at,

            # 内容主体
            title=raw_data.get("title"),
            abstract=raw_data.get("description"),
            body=raw_data.get("body") or raw_data.get("description") or "",

            # 元数据
            authors=authors,
            categories=categories,

            # 附件与关联文件
            attachments=attachments,
            supportingDocument_id=[],

            # 去重&评估
            simhash=None,
            evaluation_score=None,

            # 扩展字段
            extra_data={
                "rsshub_raw": raw_data
            },
        )
    
    async def fetch_and_normalize(self) -> List[NewsItemRawSchema]:
        """
        完整的工作流：抓取原始数据并进行规范化。
        """
        raw_list = await self.fetch_raw_data()

        normalized_list: List[NewsItemRawSchema] = []
        for raw_item in raw_list:
            normalized = self.normalize_data(raw_item)
            if normalized:
                normalized_list.append(normalized)

        return normalized_list

if __name__ == "__main__":
    fetcher = RSSHubFetcher()
    result = asyncio.run(fetcher.fetch_and_normalize())
    import json
    print(f"Total normalized articles: {len(result)}")
    json_str = json.dumps(
        [item.model_dump() for item in result],
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    json_path = r"E:\code\NewsPilot\data\temp\news\rsshub_normalized_output.json"
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json_str)