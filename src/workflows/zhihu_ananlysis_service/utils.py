# -*- coding: utf-8 -*-
"""
知乎分析服务工具集

包含辅助函数、常量定义、配置解析和存储操作。
"""

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from src.distribution.email_sender import send_daily_report_email
from src.module.content_converter import ContentConverter
from src.custom_logging import get_logger

logger = get_logger(__name__)

# Markdown 输出目录和首次运行标记文件
MARKDOWN_DIR = Path("data/zhihu_analysis_md")
FIRST_RUN_FLAG = MARKDOWN_DIR / ".first_run_complete"


@dataclass
class ZhihuServiceConfig:
    """知乎分析服务配置类。"""
    fetch_interval: int = 60 * 30
    auther_list: Optional[List[str]] = None
    process_interval: int = 60
    batch_size: int = 10
    enable_email: bool = True
    model_name: str = "gemini"
    enable_vision: bool = True
    vision_model: str = "qwen-vl-plus"

    @staticmethod
    def from_cli() -> "ZhihuServiceConfig":
        """从命令行参数解析配置。"""
        parser = argparse.ArgumentParser(description="Run zhihu analysis service.")
        parser.add_argument(
            "--fetch_interval",
            type=int,
            default=60 * 30,
            help="数据采集间隔，默认30分钟"
        )

        parser.add_argument(
            "--process_interval",
            type=int,
            default=60,
            help="数据处理间隔，默认1分钟"
        )
        parser.add_argument(
            "--batch_size",
            type=int,
            default=10,
            help="每批处理的文章数量，默认10"
        )

        parser.add_argument(
            "--enable_email",
            type=parse_bool,
            default=True,
            help="是否启用邮件通知，默认启用"
        )

        args = parser.parse_args()
        
        return ZhihuServiceConfig(
            fetch_interval=args.fetch_interval,
            process_interval=args.process_interval,
            batch_size=args.batch_size,
            enable_email=args.enable_email,
        )


def parse_bool(value: str) -> bool:
    """将字符串解析为布尔值。"""
    v = (value or "").strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def is_first_run_complete() -> bool:
    """检查首次运行初始化是否已完成。"""
    return FIRST_RUN_FLAG.exists()


def mark_first_run_complete():
    """标记首次运行初始化为已完成。"""
    FIRST_RUN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    FIRST_RUN_FLAG.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    logger.info(f"First run completed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")


def normalize_title_for_filename(title: str) -> str:
    """将标题标准化为安全的文件名片段。"""
    text = (title or "").strip()
    if not text:
        return "untitled"

    parts = re.split(r"\s*:\s*", text, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        text = parts[1].strip()

    text = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip().replace(" ", "_")
    return text[:120] if text else "untitled"


def save_markdown_file(
    title: str,
    published_at: Optional[datetime],
    markdown: str,
    markdown_dir: Path = MARKDOWN_DIR
) -> str:
    """保存 Markdown 输出并返回文件路径。"""
    published = published_at or datetime.now(timezone.utc)
    date_folder = published.strftime("%Y-%m-%d")
    target_dir = markdown_dir / date_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = published.strftime("%Y%m%d_%H%M%S")
    title_part = normalize_title_for_filename(title or "")
    file_name = f"{ts}_{title_part}.md"
    file_path = target_dir / file_name
    file_path.write_text(markdown, encoding="utf-8")

    return file_path.as_posix()


def save_json_file(
    title: str,
    published_at: Optional[datetime],
    json_content: str,
    json_dir: Optional[Path] = None
) -> str:
    """保存原始 JSON 输出并返回文件路径。"""
    if json_dir is None:
        json_dir = MARKDOWN_DIR / "raw_json"

    published = published_at or datetime.now(timezone.utc)
    date_folder = published.strftime("%Y-%m-%d")
    target_dir = json_dir / date_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = published.strftime("%Y%m%d_%H%M%S")
    title_part = normalize_title_for_filename(title or "")
    file_name = f"{ts}_{title_part}.json"
    file_path = target_dir / file_name
    file_path.write_text(json_content, encoding="utf-8")

    return file_path.as_posix()


def reconstruct_body_with_captions(body: str, attachments: list) -> str:
    """用图片说明标记替换附件占位符。"""
    if not body or not attachments:
        return body

    result_body = body
    for i, att_dict in enumerate(attachments):
        placeholder = f"<attach_{i}>"
        if placeholder in result_body:
            caption = att_dict.get("caption", "")
            if caption:
                result_body = result_body.replace(
                    placeholder,
                    f"[image{i}: {caption}]"
                )
            else:
                # 即使说明缺失，也保留明确的标记。
                result_body = result_body.replace(
                    placeholder,
                    f"[image{i}: no caption available]"
                )

    return result_body


def extract_source_url(markdown_content: str) -> str:
    """从 Markdown 内容中提取知乎源 URL。"""
    url_pattern = r'https?://[^\s\)]+zhihu\.com[^\s\)]*'
    match = re.search(url_pattern, markdown_content)
    if match:
        return match.group(0)
    return ""


async def send_markdown_email(md_file: Path):
    """发送一个 Markdown 分析文件作为邮件。"""
    try:
        converter = ContentConverter()
        md_content = md_file.read_text(encoding="utf-8")
        source_url = extract_source_url(md_content)
        html_content = converter.md_to_html(md_content, full_page=False)

        email_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <style>
                            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                            .header {{ background: #f5f5f5; padding: 15px; border-left: 4px solid #1890ff; margin-bottom: 20px; }}
                            .footer {{ color: #999; font-size: 12px; text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; }}
                        </style>
                    </head>
                    <body>
                        <div class="header">
                            <strong>Source:</strong> <a href="{source_url}">{source_url}</a>
                        </div>
                        {html_content}
                        <div class="footer">
                            发送时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
                        </div>
                    </body>
                    </html>
                    """

        temp_html = md_file.with_suffix(".html")
        temp_html.write_text(email_html, encoding="utf-8")

        subject = f"知乎分析- {md_file.stem}"
        send_daily_report_email(
            subject=subject,
            html_body_path=str(temp_html),
            attachment_paths=None,
            service_name="zhihu_dang_report"
        )

        logger.info(f"📧 Email sent: {md_file.name}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send email for {md_file.name}: {e}", exc_info=True)
        return False
