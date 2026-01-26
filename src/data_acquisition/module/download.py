import os
import logging
from typing import Optional
from pathlib import Path
from bs4 import BeautifulSoup
from paser_html import extract
# 配置日志
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'download.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def parser(html: str) -> tuple[Optional[str], Optional[str]]:
    """
    解析HTML内容，提取新闻链接和标题。

    Args:
        html: HTML内容字符串

    Returns:
        url, title: 提取的新闻链接和标题
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        nodes = soup.select('#CONTENT .TEXT-BLOCK>a')
        n = nodes[0]
        news_url = n.attrs['href']
        title = n.get_text().strip()
        return news_url, title
    except Exception as e:
        logger.error(f"解析HTML失败: {e}")
        return None

async def html_with_playwright_onece(
    url: str,
    headless: bool = False,
    wait_seconds: int = 10,
    save: bool = False
) -> dict:
    """
    使用Playwright(Chromium)抓取HTML，支持手动通过验证码。

    Args:
        url: 页面链接
        headless: 是否无头模式
        wait_seconds: 非交互环境等待秒数

    Returns:
        data: 抓取的数据字典
    """
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        logger.error(f"Playwright未安装或不可用: {e}")
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until='domcontentloaded')

            logger.info("已打开页面：如果需要验证码请手动完成，然后回到控制台按回车继续。")
            try:
                # input()
                pass
            except EOFError:
                await page.wait_for_timeout(wait_seconds * 1000)

            await page.wait_for_load_state('networkidle')
            html = await page.content()
            news_url, title = parser(html)
            await page.goto(news_url, wait_until='domcontentloaded')
            logger.info(f"正在抓取新闻页面: {news_url}")
            await page.wait_for_load_state('networkidle')
            html = await page.content()
            data = extract(html)
            data['title'] = title
            auth = title.split('-')[-1].strip()
            data['author'] = auth
            if save:
                with open(Path(f'save/{title}.md'), 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n")
                    f.write(f"## AUTHOR\n\n{data['author']}\n\n")
                    f.write(f"## TIME\n\n{data['time']}\n\n")
                    f.write(f"## CONTENT\n\n{data['content_text']}\n")
            await context.close()
            await browser.close()
        return data
    except Exception as e:
        logger.error(f"Playwright抓取失败: {e}")
        return None

if __name__ == '__main__':
    import asyncio
    
    async def main():
        # 示例：使用Playwright抓取HTML页面（可手动过验证码）
        # url = "https://archive.ph/https://www.bloomberg.com/news/articles/2026-01-21/ex-bridgewater-executive-is-hired-by-florida-based-cv-advisors"
        url = "https://archive.ph/https://www.bloomberg.com/news/articles/2026-01-23/another-russian-shadow-fleet-oil-tanker-runs-into-difficulties"
        html = await html_with_playwright_onece(
            url,
            headless=False,
            wait_seconds=1,
            save=False
        )
        print(html)
    
    asyncio.run(main())