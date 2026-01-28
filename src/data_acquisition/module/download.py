import os
import logging
from typing import Optional
from pathlib import Path
from bs4 import BeautifulSoup
import contextlib
from src.data_acquisition.module.paser_html import extract

# 配置日志
# log_dir = Path('logs')
# log_dir.mkdir(exist_ok=True)

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s',
#     handlers=[
#         logging.FileHandler(log_dir / 'download.log', encoding='utf-8'),
#         logging.StreamHandler()
#     ]
# )
# logger = logging.getLogger(__name__)

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
        print('ERROR: '+f"解析HTML失败: {e}")
        return None



@contextlib.asynccontextmanager
async def page_conn(headless=False):
    try:
        from playwright.async_api import async_playwright
        print('INFO: '+"Playwright模块导入成功")
    except Exception as e:
        print('ERROR: '+f"Playwright未安装或不可用: {e}")
        raise RuntimeError(f"Playwright未安装或不可用: {e}")

    try:
        print('INFO: '+"正在连接Playwright浏览器...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            yield page
            await context.close()
            await browser.close()
    except Exception as e:
        print('ERROR: '+f"Playwright连接失败: {e}")
        raise

async def parser_url(url: str, page, wait_seconds: int = 10) -> dict:
    await page.goto(url, wait_until='domcontentloaded')
    print('INFO: '+"已打开页面：如果需要验证码请手动完成，然后回到控制台按回车继续。")
    try:
        # input()
        pass
    except EOFError:
        await page.wait_for_timeout(wait_seconds * 1000)
    print('等待页面加载资源')
    await page.wait_for_load_state('networkidle')
    html = await page.content()
    news_url, title = parser(html)
    await page.goto(news_url, wait_until='domcontentloaded')
    print('INFO: '+f"正在抓取新闻页面: {news_url}")
    await page.wait_for_load_state('networkidle')
    html = await page.content()
    auth = title.split('-')[-1].strip()
    data = extract(html)
    return title, auth, data
        
async def html_with_playwright_onece(
    url_list: str|list[str],
    headless: bool = False,
    wait_seconds: int = 10,
    save: bool = False
) -> list[dict]:
    """
    使用Playwright(Chromium)抓取HTML，支持手动通过验证码。

    Args:
        url_list: 页面链接列表
        headless: 是否无头模式
        wait_seconds: 非交互环境等待秒数

    Returns:
        data: 抓取的数据字典的列表
    """
    if isinstance(url_list, str):
        url_list = [url_list]
    result_data = []
    async with page_conn(headless=headless) as page:
        assert page is not None, "Playwright页面连接失败"
        print('INFO: '+"正在启动Playwright浏览器...")
        for url in url_list:
            title, auth, data = await parser_url(url, page, wait_seconds=wait_seconds)
            data['title'] = title
            data['author'] = auth
            if save:
                with open(Path(f'save/{title}.md'), 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n")
                    f.write(f"## AUTHOR\n\n{data['author']}\n\n")
                    f.write(f"## TIME\n\n{data['time']}\n\n")
                    f.write(f"## CONTENT\n\n{data['content_text']}\n")
            result_data.append(data)
    return result_data

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