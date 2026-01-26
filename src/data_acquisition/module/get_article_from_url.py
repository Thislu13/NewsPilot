import asyncio
import aiohttp
import trafilatura

from bs4 import BeautifulSoup
from datetime import datetime
from readability import Document
from download import html_with_playwright_onece
from datetime import datetime
from typing import List, Dict, Any


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_full_article_by_url(
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

    # ======================
    # 1️⃣ 直抓
    # ======================
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
    
    # ======================
    # 2️⃣ archive.ph 兜底
    # ======================
    if not result["success"]:
        archive_url = f"https://archive.ph/{url}"
        
        try:
            # 现在 html_with_playwright_onece 是异步函数，需要使用 await
            archive_data = await html_with_playwright_onece(archive_url)
            
            if archive_data is not None and isinstance(archive_data, dict):
                result["body"] = archive_data.get('content_text')
                result["title"] = archive_data.get('title')
                result["authors"] = [archive_data.get('author')] if archive_data.get('author') else []
                
                # 处理时间格式
                time_str = archive_data.get('time')
                if time_str:
                    try:
                        result["published_at"] = datetime.strptime(time_str, "%Y年%m月%d日 %H:%M:%S %Z")
                    except ValueError:
                        # 如果时间格式不匹配，保持为 None
                        pass
                
                result["method"] = "archive"
                result["confidence"] = 0.6
                result["success"] = True
            else:
                result["error"] = "archive_data_invalid_or_none"
                
        except Exception as e:
            result["error"] = f"archive_fetch_failed: {str(e)}"
            result["success"] = False

    return result


if __name__ == "__main__":
    import asyncio

    test_url_list = ["https://www.bloomberg.com/news/articles/2026-01-21/ex-bridgewater-executive-is-hired-by-florida-based-cv-advisors",
                     "https://www.bloomberg.com/news/articles/2026-01-23/another-russian-shadow-fleet-oil-tanker-runs-into-difficulties"]
    for test_url in test_url_list:
        async def main():
            article = await fetch_full_article_by_url(test_url)
            print('='*100)
            print(article['body'])

        asyncio.run(main())