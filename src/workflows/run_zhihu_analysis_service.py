#
# Author: Claude Code
# Date: 2026-02-22
# Description: 知乎博主分析服务 - 包含抓取守护进程和分析处理工作流

"""
启动知乎博主分析服务 (Zhihu Analysis Service)
架构：
1. Acquisition Daemon: 定时抓取知乎文章，存入数据库（status=pending）
2. Processing Worker: 轮询pending记录，调用LLM分析，保存markdown，发送邮件
"""

import asyncio
import os
import sys
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List

from src.data_acquisition.zhihu_daemon_orchestrator import ZhihuDaemonOrchestrator
from src.intelligence.zhihu_analyzer import ZhihuAnalyzer
from src.intelligence.renderers import ZhihuDangReportRenderer
from src.storage import db_manager, StorageRepository, ZhihuRawPost
from src.distribution.email_sender import send_daily_report_email
from src.module.content_converter import ContentConverter

# 配置
MARKDOWN_DIR = Path("data/zhihu_analysis_md")
FIRST_RUN_FLAG = MARKDOWN_DIR / ".first_run_complete"


def is_first_run_complete() -> bool:
    """检查是否已完成首次运行"""
    return FIRST_RUN_FLAG.exists()


def mark_first_run_complete():
    """标记首次运行已完成"""
    FIRST_RUN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    FIRST_RUN_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
    print(f"✅ First run completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def normalize_title_for_filename(title: str) -> str:
    """规范化标题用于文件名"""
    text = (title or "").strip()
    if not text:
        return "untitled"

    # 兼容中英文冒号，按第一个冒号切分
    parts = re.split(r"\s*[:：]\s*", text, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        text = parts[1].strip()

    text = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip().replace(" ", "_")
    return text[:120] if text else "untitled"


def save_markdown_file(
    title: str,
    published_at: datetime | None,
    markdown: str,
    markdown_dir: Path
) -> str:
    """保存markdown文件"""
    published = published_at or datetime.utcnow()
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
    published_at: datetime | None,
    json_content: str,
    json_dir: Path
) -> str:
    """保存原始JSON文件（用于调试和未来分析）"""
    published = published_at or datetime.utcnow()
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
    """
    重构body，将占位符替换为图片描述
    用于LLM分析时提供完整上下文
    """
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
                    f"[图片{i}: {caption}]"
                )

    return result_body


def extract_source_url(markdown_content: str) -> str:
    """从markdown内容中提取原文链接"""
    url_pattern = r'https?://[^\s\)]+zhihu\.com[^\s\)]*'
    match = re.search(url_pattern, markdown_content)
    if match:
        return match.group(0)
    return ""


async def send_markdown_email(md_file: Path):
    """发送单个markdown文件的邮件通知"""
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
                            <strong>原文链接:</strong> <a href="{source_url}">{source_url}</a>
                        </div>
                        {html_content}
                        <div class="footer">
                            生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        </div>
                    </body>
                    </html>
                    """

        temp_html = md_file.with_suffix(".html")
        temp_html.write_text(email_html, encoding="utf-8")

        subject = f"知乎分析 - {md_file.stem}"
        send_daily_report_email(
            subject=subject,
            html_body_path=str(temp_html),
            attachment_paths=None,
            service_name="zhihu_analysis"  # 指定服务名称
        )

        print(f"📧 Email sent: {md_file.name}")
        return True

    except Exception as e:
        print(f"⚠️  Failed to send email for {md_file.name}: {e}")
        return False


async def run_processing_worker(
    batch_size: int = 10,
    process_interval: int = 5,
    model_name: str = "gemini",
    model_id: str | None = None,
    enable_email: bool = True,
    skip_email: bool = False
):
    """
    处理工作流：轮询 zhihu_raw_posts 中 pending 的记录，调用 LLM 分析，保存 markdown

    注意：图片处理已在 acquisition 阶段完成，这里只做分析

    Args:
        batch_size: 每次处理的批次大小
        process_interval: 轮询间隔（秒）
        model_name: 使用的模型名称
        model_id: 模型ID
        enable_email: 是否启用邮件通知
        skip_email: 是否跳过邮件发送（用于首次运行）
    """
    repo = StorageRepository()
    analyzer = ZhihuAnalyzer(model_name=model_name, model_id=model_id)

    print(f"[Processing] Worker started (batch_size={batch_size}, interval={process_interval}s)")

    while True:
        processing_ids: List[str] = []
        session = None

        try:
            session = db_manager.get_session()

            # 1. 拉取 pending 任务（排除重试次数过多的）
            MAX_RETRIES = 3
            rows = (
                session.query(ZhihuRawPost)
                .filter(ZhihuRawPost.status == "pending")
                .limit(batch_size * 2)  # 多拉取一些，因为可能有些会被过滤
                .all()
            )

            # 过滤掉重试次数过多的记录
            valid_rows = []
            skip_rows = []
            for r in rows:
                retry_count = (r.extra_data or {}).get("retry_count", 0)
                if retry_count >= MAX_RETRIES:
                    skip_rows.append(r)
                else:
                    valid_rows.append(r)
                    if len(valid_rows) >= batch_size:
                        break

            # 将超过重试次数的记录标记为 failed
            if skip_rows:
                skip_ids = [r.unique_id for r in skip_rows]
                repo.mark_zhihu_raw_status(skip_ids, "failed", session=session)
                for r in skip_rows:
                    r.extra_data = {
                        **(r.extra_data or {}),
                        "failed_reason": "Max retries exceeded",
                        "failed_at": datetime.now().isoformat()
                    }
                session.commit()
                print(f"[Processing] ⚠️  Marked {len(skip_rows)} items as failed (max retries exceeded)")

            rows = valid_rows
            if not rows:
                session.close()
                await asyncio.sleep(process_interval)
                continue

            print(f"[Processing] Picked up {len(rows)} pending items")
            processing_ids = [r.unique_id for r in rows]

            # 2. 标记为 processing
            repo.mark_zhihu_raw_status(processing_ids, "processing", session=session)
            session.commit()

            # 3. 提取数据用于分析（图片描述已在 attachments.caption 中）
            rows_data = [
                {
                    "unique_id": r.unique_id,
                    "title": r.title,
                    "body": reconstruct_body_with_captions(r.body, r.attachments),
                    "source_url": r.source_url,
                    "published_at": r.published_at,
                }
                for r in rows
            ]

            session.close()

            # 4. 分析每篇文章
            async def _analyze_one(row: dict) -> tuple[str, bool, str, str]:
                try:
                    # 1. 调用分析器获取JSON输出
                    llm_output = await analyzer.analyze_single(
                        title=row.get("title") or "",
                        body=row.get("body") or "",
                        source_url=row.get("source_url") or "",
                    )

                    # 2. 使用渲染器将JSON转换为Markdown
                    renderer = ZhihuDangReportRenderer()
                    markdown = renderer.render(
                        llm_output_json=llm_output,
                        source_url=row.get("source_url") or "",
                        published_at=row.get("published_at")
                    )

                    # 3. 保存Markdown文件
                    md_path = save_markdown_file(
                        title=row.get("title") or "",
                        published_at=row.get("published_at"),
                        markdown=markdown,
                        markdown_dir=MARKDOWN_DIR
                    )

                    # 4. 可选：保存原始JSON用于调试和未来分析
                    json_path = save_json_file(
                        title=row.get("title") or "",
                        published_at=row.get("published_at"),
                        json_content=llm_output,
                        json_dir=MARKDOWN_DIR / "raw_json"
                    )

                    return str(row.get("unique_id") or ""), True, md_path, ""
                except Exception as e:
                    return (
                        str(row.get("unique_id") or ""),
                        False,
                        "",
                        f"{type(e).__name__}: {e}"
                    )

            # 串行处理
            results: List[tuple[str, bool, str, str]] = []
            for row in rows_data:
                results.append(await _analyze_one(row))

            success_ids: List[str] = [rid for rid, ok, _, _ in results if ok]
            markdown_paths: dict[str, str] = {
                rid: path for rid, ok, path, _ in results if ok
            }

            # 打印失败的错误信息
            failed_results = [(rid, err) for rid, ok, _, err in results if not ok]
            if failed_results:
                print(f"[Processing] ❌ Failed items details:")
                for rid, err in failed_results:
                    print(f"  - {rid}: {err}")

            # 5. 更新状态
            session = db_manager.get_session()
            if success_ids:
                repo.mark_zhihu_raw_status(success_ids, "completed", session=session)

                # 更新 extra_data 记录 markdown 路径
                fresh_rows = (
                    session.query(ZhihuRawPost)
                    .filter(ZhihuRawPost.unique_id.in_(success_ids))
                    .all()
                )
                for fresh in fresh_rows:
                    md_path = markdown_paths.get(fresh.unique_id)
                    if md_path:
                        fresh.extra_data = {
                            **(fresh.extra_data or {}),
                            "analysis_markdown_path": md_path,
                            "analysis_saved_at": datetime.now().isoformat(),
                        }

            failed_ids = set(processing_ids) - set(success_ids)
            if failed_ids:
                # 获取失败记录的错误信息
                failed_errors = {rid: err for rid, ok, _, err in results if not ok}

                # 更新失败记录：增加重试计数，重置为 pending
                failed_rows = (
                    session.query(ZhihuRawPost)
                    .filter(ZhihuRawPost.unique_id.in_(list(failed_ids)))
                    .all()
                )
                for row in failed_rows:
                    retry_count = (row.extra_data or {}).get("retry_count", 0)
                    row.extra_data = {
                        **(row.extra_data or {}),
                        "retry_count": retry_count + 1,
                        "last_error": failed_errors.get(row.unique_id, "Unknown error"),
                        "last_retry_at": datetime.now().isoformat()
                    }

                # 重置为 pending，等待下次重试
                repo.mark_zhihu_raw_status(
                    list(failed_ids),
                    "pending",
                    session=session,
                )

            session.commit()
            session.close()

            print(f"[Processing] Completed: {len(success_ids)}, Failed: {len(failed_ids)}")

            # 6. 发送邮件通知
            if enable_email and not skip_email and success_ids:
                for rid in success_ids:
                    md_path = markdown_paths.get(rid)
                    if md_path:
                        await send_markdown_email(Path(md_path))

        except Exception as e:
            print(f"[Processing] Error: {e}")
            if session and session.is_active:
                session.rollback()
            # 重置处理中的任务
            if processing_ids:
                try:
                    sess2 = db_manager.get_session()
                    repo.mark_zhihu_raw_status(processing_ids, "pending", session=sess2)
                    sess2.commit()
                    sess2.close()
                except Exception:
                    pass
            await asyncio.sleep(10)
        finally:
            if session:
                session.close()


async def main(
    fetch_interval: int = 60 * 30,
    process_interval: int = 5,
    batch_size: int = 10,
    enable_email: bool = True,
    model_name: str = "gemini",
    enable_vision: bool = True,
    vision_model: str = "qwen-vl-plus"
):
    """
    主函数：运行知乎分析服务

    Args:
        fetch_interval: 抓取间隔（秒）
        process_interval: 处理轮询间隔（秒）
        batch_size: 每次处理的批次大小
        enable_email: 是否启用邮件通知
        model_name: 使用的模型名称
        enable_vision: 是否启用图片理解
        vision_model: 图片理解模型
    """
    # 确保数据库表存在
    db_manager.verify_and_create_tables()

    # 初始化守护进程（负责抓取和图片处理）
    daemon = ZhihuDaemonOrchestrator(
        fetch_interval=fetch_interval,
        enable_vision=enable_vision,
        vision_model=vision_model
    )

    print(f"\n🚀 Zhihu Analysis Service Started [PID: {os.getpid()}]")
    print(f"├─ 📡 Fetch Interval: {fetch_interval}s")
    print(f"├─ 🔄 Process Interval: {process_interval}s")
    print(f"├─ 📧 Email: {'Enabled' if enable_email else 'Disabled'}")
    print(f"├─ 🤖 Analysis Model: {model_name}")
    print(f"├─ 👁️  Vision: {'Enabled' if enable_vision else 'Disabled'} ({vision_model})")
    print("└─ 🛑 Press Ctrl+C to stop...\n")

    # 首次运行处理
    if not is_first_run_complete():
        print("🔄 First run detected - processing historical articles without email...")

        # 运行一次抓取
        new_ids = await daemon.run_acquisition_processing_once()
        if new_ids:
            print(f"📝 Created {len(new_ids)} records with status=pending")

        # 处理所有 pending 记录（不发送邮件）
        print("🔄 Processing pending records (no email)...")
        session = db_manager.get_session()
        pending_count = session.query(ZhihuRawPost).filter(
            ZhihuRawPost.status == "pending"
        ).count()
        session.close()

        if pending_count > 0:
            print(f"📝 Found {pending_count} pending records to process...")
            # 启动临时处理工作流（跳过邮件）
            temp_worker_task = asyncio.create_task(
                run_processing_worker(
                    batch_size=batch_size,
                    process_interval=1,  # 快速处理
                    model_name=model_name,
                    enable_email=enable_email,
                    skip_email=True  # 跳过邮件
                )
            )

            # 等待所有 pending 记录处理完成
            while True:
                session = db_manager.get_session()
                remaining = session.query(ZhihuRawPost).filter(
                    ZhihuRawPost.status == "pending"
                ).count()
                session.close()

                if remaining == 0:
                    temp_worker_task.cancel()
                    break

                print(f"⏳ Processing... {remaining} remaining")
                await asyncio.sleep(5)

        mark_first_run_complete()
        print("✅ First run completed. Future runs will send email notifications.\n")

    # 正常运行：启动并发任务
    print("🔁 Starting normal operation...\n")

    async def acquisition_loop():
        """抓取循环"""
        while True:
            await daemon.run_acquisition_processing_once()
            await asyncio.sleep(fetch_interval)

    # 启动并发任务
    await asyncio.gather(
        acquisition_loop(),
        run_processing_worker(
            batch_size=batch_size,
            process_interval=process_interval,
            model_name=model_name,
            enable_email=enable_email,
            skip_email=False
        )
    )


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Zhihu Analysis Service Stopped.")

