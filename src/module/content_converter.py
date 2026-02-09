import markdown
import asyncio
from playwright.async_api import async_playwright
import os

class ContentConverter:
    def __init__(self):
        # 基础 CSS 样式 (GitHub 风格简化版)
        self.css_styles = """
            <style>
                body {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji";
                    font-size: 16px;
                    line-height: 1.5;
                    word-wrap: break-word;
                    color: #24292e;
                    background-color: #fff;
                    margin: 0;
                    padding: 20px;
                }
                h1, h2, h3 { margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }
                h1 { font-size: 2em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }
                h2 { font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }
                h3 { font-size: 1.25em; }
                p { margin-top: 0; margin-bottom: 16px; }
                blockquote { margin: 0; padding: 0 1em; color: #6a737d; border-left: 0.25em solid #dfe2e5; }
                table { display: block; width: 100%; overflow: auto; margin-top: 0; margin-bottom: 16px; border-spacing: 0; border-collapse: collapse; }
                table tr { background-color: #fff; border-top: 1px solid #c6cbd1; }
                table tr:nth-child(2n) { background-color: #f6f8fa; }
                table th, table td { padding: 6px 13px; border: 1px solid #dfe2e5; }
                table th { font-weight: 600; }
                a { color: #0366d6; text-decoration: none; }
                a:hover { text-decoration: underline; }
                code { padding: .2em .4em; margin: 0; font-size: 85%; background-color: #f6f8fa; border-radius: 3px; }
                pre { padding: 16px; overflow: auto; font-size: 85%; line-height: 1.45; background-color: #f6f8fa; border-radius: 3px; }
                pre code { background-color: transparent; }
                hr { height: .25em; padding: 0; margin: 24px 0; background-color: #e1e4e8; border: 0; }
            </style>
        """

    def md_to_html(self, md_content: str, full_page: bool = True) -> str:
        """
        将 Markdown 转换为 HTML
        :param md_content: Markdown 文本
        :param full_page: 是否包含完整的 <html><body> 结构 (如果为 False 则只返回片段，适合嵌入)
        :return: HTML 字符串
        """
        html_body = markdown.markdown(
            md_content, 
            extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
        )
        
        if not full_page:
            return html_body

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            {self.css_styles}
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

    async def md_to_pdf_bytes(self, md_content: str) -> bytes:
        """
        将 Markdown 转换为 PDF (使用 Playwright 渲染)
        :param md_content: Markdown 文本
        :return: PDF 二进制数据
        """
        html_content = self.md_to_html(md_content, full_page=True)
        
        async with async_playwright() as p:
            # 启动浏览器 (这里使用 chromium)
            browser = await p.chromium.launch()
            page = await browser.new_page()
            
            # 设置 HTML 内容
            await page.set_content(html_content)
            
            # 打印为 PDF
            pdf_bytes = await page.pdf(
                format="A4",
                margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"},
                print_background=True
            )
            
            await browser.close()
            return pdf_bytes

    async def save_pdf(self, md_content: str, output_path: str):
        """直接保存 PDF 到文件"""
        pdf_bytes = await self.md_to_pdf_bytes(md_content)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"   [+] PDF 已生成: {output_path}")

# 使用示例
if __name__ == "__main__":
    converter = ContentConverter()
    md_text = "# Test Report\n\n> This is a test.\n\n| Col1 | Col2 |\n|---|---|\n| Val1 | Val2 |"
    
    # 测试 HTML
    print(converter.md_to_html(md_text)[:100] + "...")
    
    # 测试 PDF (需要 asyncio)
    async def test_pdf():
        await converter.save_pdf(md_text, "test_report.pdf")
    
    # asyncio.run(test_pdf())
