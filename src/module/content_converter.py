import markdown
import asyncio
from playwright.async_api import async_playwright
import os
import base64

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
                
                /* 打赏区域样式 - 美化版 */
                .donation-container {
                    margin-top: 50px;
                    padding: 30px;
                    background: linear-gradient(135deg, #f6f8fa 0%, #ffffff 100%);
                    border-top: 1px solid #eaecef;
                    text-align: center;
                    border-radius: 12px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.02);
                }
                .donation-title {
                    font-size: 1.2em;
                    font-weight: 600;
                    color: #586069;
                    margin-bottom: 20px;
                }
                .donation-img {
                    width: 200px;
                    height: 200px;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    transition: transform 0.3s ease;
                }
                .donation-img:hover {
                    transform: scale(1.05);
                }
                .donation-desc {
                    margin-top: 15px;
                    font-size: 0.9em;
                    color: #6a737d;
                }
            </style>
        """

    def md_to_html(self, md_content: str, full_page: bool = True, footer_image_path: str = None) -> str:
        """
        将 Markdown 转换为 HTML
        :param md_content: Markdown 文本
        :param full_page: 是否包含完整的 <html><body> 结构
        :param footer_image_path: 可选，底部附加图片的绝对路径（如打赏码）
        :return: HTML 字符串
        """
        html_body = markdown.markdown(
            md_content, 
            extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
        )
        
        # 插入底部图片逻辑
        if footer_image_path and os.path.exists(footer_image_path):
            try:
                with open(footer_image_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    ext = footer_image_path.split('.')[-1].lower()
                    mime_type = f"image/{ext}" if ext != 'jpg' else "image/jpeg"
                    
                    footer_html = f"""
                    <div class="donation-container">
                        <div class="donation-title">🤝 感谢支持开源项目</div>
                        <img src="data:{mime_type};base64,{encoded_string}" alt="Support" class="donation-img">
                        <div class="donation-desc">如果不介意，可以请作者喝杯咖啡 ☕</div>
                    </div>
                    """
                    html_body += footer_html
            except Exception as e:
                print(f"[!] Warning: Failed to embed footer image: {e}")
        
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
