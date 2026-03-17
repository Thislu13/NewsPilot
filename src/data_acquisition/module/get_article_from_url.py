import asyncio
import aiohttp
import trafilatura
from bs4 import BeautifulSoup
from datetime import datetime
from readability import Document

from src.data_acquisition.module.download import html_with_playwright_onece

from typing import List, Dict, Any

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_article_direct(
    url: str,
    timeout: int = 8,
    min_body_length: int = 50,
) -> Dict[str, Any]:
    """
    直接抓取文章（不使用 archive.ph）

    返回字段：
    - success: bool
    - title: str | None
    - body: str | None
    - authors: list[str]
    - published_at: datetime | None
    - method: str | None
    - confidence: float
    - error: str | None
    """
    result = {
        "success": False,
        "title": None,
        "body": None,
        "authors": [],
        "published_at": None,
        "method": None,
        "confidence": 0.0,
        "error": None,
    }

    async def _download(target_url: str) -> str | None:
        try:
            async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
                async with session.get(target_url, timeout=timeout) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.text()
        except Exception:
            return None

    def _extract(html: str) -> tuple[str | None, float, str | None]:
        """
        返回 (body, confidence, method)
        """
        # --- trafilatura ---
        try:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if text and len(text.strip()) >= min_body_length:
                return text.strip(), 0.9, "direct"
        except Exception:
            pass

        # --- readability 兜底 ---
        try:
            doc = Document(html)
            content_html = doc.summary(html_partial=True)
            soup = BeautifulSoup(content_html, "lxml")
            text = soup.get_text(separator="\n").strip()
            if len(text) >= min_body_length:
                return text, 0.7, "direct+readability"
        except Exception:
            pass

        return None, 0.0, None

    # 直接抓取
    html = await _download(url)
    if html:
        body, confidence, method = _extract(html)
        if body:
            result["body"] = body
            result["confidence"] = confidence
            result["method"] = method
            result["success"] = True
        else:
            result["error"] = "direct_extract_failed"
    else:
        result["error"] = "direct_fetch_failed"

    if result["success"]:
        soup = BeautifulSoup(html, "lxml")

        # title
        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()

        # author（启发式）
        for key in ["author", "byline", "parsely-author"]:
            meta = soup.find("meta", attrs={"name": key})
            if meta and meta.get("content"):
                result["authors"] = [
                    a.strip() for a in meta["content"].split(",") if a.strip()
                ]
                break

    return result


async def fetch_article_from_archive(
    url_list: str|list[str],
) -> list[Dict[str, Any]]:
    """
    从 archive.ph 抓取文章（兜底方案）

    返回字段：
    - success: bool
    - title: str | None
    - body: str | None
    - authors: list[str]
    - published_at: datetime | None
    - method: str | None
    - confidence: float
    - error: str | None
    """
    if isinstance(url_list, str):
        url_list = [url_list]
    archive_data_list = await html_with_playwright_onece([f"https://archive.ph/{url}" for url in url_list])
    result_data = []
    print(f"INFO: 对长度为{len(url_list)}的url列表使用archive.ph兜底")
    for archive_data in archive_data_list:
        print("INFO: archive_data:", archive_data)
        result = {
            "success": False,
            "title": None,
            "body": None,
            "authors": [],
            "published_at": None,
            "method": None,
            "confidence": 0.0,
            "error": None,
        }
        try:
            if archive_data:
                archive_data = archive_data_list[0]  # 取第一个结果
                result["body"] = archive_data.get('content_text')
                result["title"] = archive_data.get('title')
                result["authors"] = [archive_data.get('author')] if archive_data.get('author') else []
                
                # 处理时间格式
                time_str = archive_data.get('time')
                if time_str:
                    try:
                        result["published_at"] = datetime.strptime(time_str, "%Y年%m月%d日 %H:%M:%S %Z")
                    except ValueError:
                        pass
                
                result["method"] = "archive"
                result["confidence"] = 0.6
                result["success"] = True
            else:
                result["error"] = "archive_data_invalid_or_empty"
                
        except Exception as e:
            result["error"] = f"archive_fetch_failed: {str(e)}"
            result["success"] = False
        result_data.append(result)

    return result_data


async def fetch_full_article_by_url_one(
    url: str,
    timeout: int = 8,
    min_body_length: int = 50,
) -> Dict[str, Any]:
    """
    根据 URL 抓取新闻正文（直抓 + archive.ph 兜底）

    返回字段：
    - success: bool
    - title: str | None
    - body: str | None
    - authors: list[str]
    - published_at: datetime | None
    - method: str | None
    - confidence: float
    - error: str | None
    """
    
    # 1️⃣ 直抓
    result = await fetch_article_direct(url, timeout, min_body_length)
    
    # 2️⃣ archive.ph 兜底
    if not result["success"]:
        result = await fetch_article_from_archive(url)[0]
    
    return result


async def fetch_full_article_by_url_async(url_list: List[str]) -> List[Dict[str, Any ]]:
    """
    批量根据 URL 抓取新闻正文（直抓 + archive.ph 兜底）
    
    流程：
    1. 第一步：异并发执行所有 URL 的直抓
    2. 第二步：对失败的 URL 异并发执行 archive.ph 兜底
    """
    # 第一步：异并发直抓所有 URL
    print('INFO: 开始批量直抓文章...')
    direct_tasks = [
        fetch_article_direct(url)
        for url in url_list
    ]
    results = await asyncio.gather(*direct_tasks)
    
    # 第二步：找出失败的 URL 并并发使用 archive 兜底
    print('INFO: 直抓完成，开始使用 archive.ph 兜底失败的文章...')
    failed_indices = [i for i, result in enumerate(results) if not result["success"]]  # 失败的结果索引
    print(f'INFO: 需要使用 archive.ph 兜底的文章数量: {len(failed_indices)}')
    print(f'INFO: 失败的文章索引: {failed_indices}')
    print(f'INFO: 失败的文章URL: {"\t".join([url_list[i]+'\n' for i in failed_indices])}')
    urls = [url_list[i] for i in failed_indices]
    if failed_indices:
        archive_results = await fetch_article_from_archive(urls)
        
        # 用 archive 结果替换失败的结果
        for k, archive_result in zip(failed_indices, archive_results):
            results[k] = archive_result
    
    return results


def fetch_full_article_by_url(url_list: List[str]) -> List[Dict[str, Any]]:
    """
    批量根据 URL 抓取新闻正文（直抓 + archive.ph 兜底）
    """
    return asyncio.run(fetch_full_article_by_url_async(url_list))

if __name__ == "__main__":
    import asyncio

    test_url_list = ["https://www.bloomberg.com/news/articles/2026-01-21/ex-bridgewater-executive-is-hired-by-florida-based-cv-advisors",
                     "https://www.bloomberg.com/news/articles/2026-01-23/another-russian-shadow-fleet-oil-tanker-runs-into-difficulties"]
    
    result = fetch_full_article_by_url(test_url_list)
    for item in result:
        print('='*100)
        print(item['body'])



    # for test_url in test_url_list:
    #     async def main():
    #         article = await fetch_full_article_by_url(test_url)
    #         print('='*100)
    #         print(article['body'])

    #     asyncio.run(main())