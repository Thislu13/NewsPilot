#
# Author: Claude Code
# Date: 2026-02-22
# Description: 知乎分析服务 - 启动采集守护进程和处理工作器
#              1. Acquisition Daemon: 抓取知乎文章，状态标记为 pending
#              2. Processing Worker: 处理 pending 的文章，调用 LLM 生成 Markdown 分析报告

import argparse
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

# Markdown 输出目录
MARKDOWN_DIR = Path("data/zhihu_analysis_md")
FIRST_RUN_FLAG = MARKDOWN_DIR / ".first_run_complete"


def parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def is_first_run_complete() -> bool:
    """Check whether first-run bootstrap is complete."""
    return FIRST_RUN_FLAG.exists()


def mark_first_run_complete():
    """Mark first-run bootstrap as complete."""
    FIRST_RUN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    FIRST_RUN_FLAG.write_text(datetime.now().isoformat(), encoding="utf-8")
    print(f"First run completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def normalize_title_for_filename(title: str) -> str:
    """Normalize title into a safe filename fragment."""
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
    published_at: datetime | None,
    markdown: str,
    markdown_dir: Path
) -> str:
    """Save markdown output and return file path."""
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
    """Save raw JSON output and return file path."""
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
    """Replace attachment placeholders with readable caption markers."""
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
                # Keep an explicit marker even if caption is missing.
                result_body = result_body.replace(
                    placeholder,
                    f"[image{i}: no caption available]"
                )

    return result_body


def extract_source_url(markdown_content: str) -> str:
    """Extract zhihu source URL from markdown content."""
    url_pattern = r'https?://[^\s\)]+zhihu\.com[^\s\)]*'
    match = re.search(url_pattern, markdown_content)
    if match:
        return match.group(0)
    return ""


async def send_markdown_email(md_file: Path):
    """Send one markdown analysis file as email."""
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
                            <strong>:</strong> <a href="{source_url}">{source_url}</a>
                        </div>
                        {html_content}
                        <div class="footer">
                            发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
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

        print(f"📧 Email sent: {md_file.name}")
        return True

    except Exception as e:
        print(f"❌ Failed to send email for {md_file.name}: {e}")
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
    处理知乎待分析文章的工作器函数。
    从 zhihu_raw_posts 表中获取 pending 状态的文章，调用 LLM 生成 Markdown 分析报告。

    依赖 Acquisition Daemon 进行数据采集。

    Args:
        batch_size: 每次处理的文章数量
        process_interval: 没有任务时的休眠间隔（秒）
        model_name: 使用的 LLM 模型名称
        model_id: 使用的 LLM 模型 ID
        enable_email: 是否启用邮件发送功能
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

            # 1. 查询 pending 状态的文章
            MAX_RETRIES = 3
            rows = (
                session.query(ZhihuRawPost)
                .filter(ZhihuRawPost.status == "pending")
                .limit(batch_size * 2)  # 多查一些用于过滤超重试次数的记录
                .all()
            )

            # 过滤出有效记录和超重试次数需要跳过的记录
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

            # 标记超重试次数的记录为 failed
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
                print(f"[Processing] ⚠️ Marked {len(skip_rows)} items as failed (max retries exceeded)")

            rows = valid_rows
            if not rows:
                session.close()
                await asyncio.sleep(process_interval)
                continue

            print(f"[Processing] Picked up {len(rows)} pending items")
            processing_ids = [r.unique_id for r in rows]

            # 2. 标记为 processing 状态
            repo.mark_zhihu_raw_status(processing_ids, "processing", session=session)
            session.commit()

            # 3. 组装数据，使用 caption 重建正文
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

            # 4. 并发调用 LLM 分析
            async def _analyze_one(row: dict) -> tuple[str, bool, str, str]:
                try:
                    # 1. 调用 LLM 分析
                    llm_output = await analyzer.analyze_single(
                        title=row.get("title") or "",
                        body=row.get("body") or "",
                        source_url=row.get("source_url") or "",
                    )

                    # 2. 渲染为 Markdown
                    renderer = ZhihuDangReportRenderer()
                    markdown = renderer.render(
                        llm_output_json=llm_output,
                        source_url=row.get("source_url") or "",
                        published_at=row.get("published_at")
                    )

                    # 3. 保存 Markdown 文件
                    md_path = save_markdown_file(
                        title=row.get("title") or "",
                        published_at=row.get("published_at"),
                        markdown=markdown,
                        markdown_dir=MARKDOWN_DIR
                    )

                    # 4. 保存原始 JSON
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

            # 收集分析结果
            results: List[tuple[str, bool, str, str]] = []
            for row in rows_data:
                results.append(await _analyze_one(row))

            success_ids: List[str] = [rid for rid, ok, _, _ in results if ok]
            markdown_paths: dict[str, str] = {
                rid: path for rid, ok, path, _ in results if ok
            }

            # 记录失败项目详情
            failed_results = [(rid, err) for rid, ok, _, err in results if not ok]
            if failed_results:
                print(f"[Processing] ❌Failed items details:")
                for rid, err in failed_results:
                    print(f"  - {rid}: {err}")

            # 5. 更新数据库状态
            session = db_manager.get_session()
            if success_ids:
                repo.mark_zhihu_raw_status(success_ids, "completed", session=session)

                # 更新 extra_data，记录 Markdown 文件路径
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
                # 收集错误信息
                failed_errors = {rid: err for rid, ok, _, err in results if not ok}

                # 处理失败记录，增加重试次数并恢复为 pending 状态
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

                # 恢复为 pending 状态以便重试
                repo.mark_zhihu_raw_status(
                    list(failed_ids),
                    "pending",
                    session=session,
                )

            session.commit()
            session.close()

            print(f"[Processing] Completed: {len(success_ids)}, Failed: {len(failed_ids)}")

            # 6. 
            if enable_email and not skip_email and success_ids:
                for rid in success_ids:
                    md_path = markdown_paths.get(rid)
                    if md_path:
                        await send_markdown_email(Path(md_path))

        except Exception as e:
            print(f"[Processing] Error: {e}")
            if session and session.is_active:
                session.rollback()
            # 恢复 processing 状态的任务为 pending
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
    知乎分析服务主入口函数。

    Args:
        fetch_interval: 抓取间隔（秒），默认 30 分钟
        process_interval: 处理间隔（秒），默认 5 秒
        batch_size: 每次处理的文章数量，默认 10
        enable_email: 是否启用邮件发送，默认 True
        model_name: 使用的 LLM 模型名称，默认 gemini
        enable_vision: 是否启用图片理解功能，默认 True
        vision_model: 视觉理解模型，默认 qwen-vl-plus
    """
    # 初始化数据库表
    db_manager.verify_and_create_tables()

    # 初始化守护进程编排器
    daemon = ZhihuDaemonOrchestrator(
        fetch_interval=fetch_interval,
        enable_vision=enable_vision,
        vision_model=vision_model
    )

    print(f"\n🚀 Zhihu Analysis Service Started [PID: {os.getpid()}]")
    print(f"  📡 Fetch Interval: {fetch_interval}s")
    print(f"  ⚙️ Process Interval: {process_interval}s")
    print(f"  📧 Email: {'Enabled' if enable_email else 'Disabled'}")
    print(f"  🤖 Analysis Model: {model_name}")
    print(f"  👁️  Vision: {'Enabled' if enable_vision else 'Disabled'} ({vision_model})")
    print("  🛑 Press Ctrl+C to stop...\n")

    # 首次运行处理历史数据
    if not is_first_run_complete():
        print("🔔 First run detected - processing historical articles without email...")

        # 执行一次抓取
        new_ids = await daemon.run_acquisition_processing_once()
        if new_ids:
            print(f"✅ Created {len(new_ids)} records with status=pending")

        # 处理 pending 记录
        print("⚙️ Processing pending records (no email)...")
        session = db_manager.get_session()
        pending_count = session.query(ZhihuRawPost).filter(
            ZhihuRawPost.status == "pending"
        ).count()
        session.close()

        if pending_count > 0:
            print(f"📋 Found {pending_count} pending records to process...")
            # 启动临时工作器处理历史数据
            temp_worker_task = asyncio.create_task(
                run_processing_worker(
                    batch_size=batch_size,
                    process_interval=1,  # 快速轮询
                    model_name=model_name,
                    enable_email=enable_email,
                    skip_email=True  # 首次运行不发送邮件
                )
            )

            # 等待 pending 和 processing 状态都处理完成
            while True:
                session = db_manager.get_session()
                remaining = session.query(ZhihuRawPost).filter(
                    ZhihuRawPost.status.in_(["pending", "processing"])
                ).count()
                session.close()

                if remaining == 0:
                    temp_worker_task.cancel()
                    break

                print(f"⚙️ Processing... {remaining} remaining")
                await asyncio.sleep(5)

        mark_first_run_complete()
        print("✅ First run completed. Future runs will send email notifications.\n")

    # 启动正常循环模式
    print("🚀 Starting normal operation...\n")

    async def acquisition_loop():
        """Polling loop for acquisition daemon."""
        while True:
            await daemon.run_acquisition_processing_once()
            await asyncio.sleep(fetch_interval)

    # 并发运行采集循环和处理工作器
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

    parser = argparse.ArgumentParser(description="Run zhihu analysis service.")
    parser.add_argument("--fetch-interval", type=int, default=60 * 30)
    parser.add_argument("--process-interval", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--enable-email", type=parse_bool, default=True)
    parser.add_argument("--model-name", type=str, default="gemini")
    parser.add_argument("--enable-vision", type=parse_bool, default=True)
    parser.add_argument("--vision-model", type=str, default="qwen-vl-plus")
    args = parser.parse_args()

    try:
        asyncio.run(
            main(
                fetch_interval=args.fetch_interval,
                process_interval=args.process_interval,
                batch_size=args.batch_size,
                enable_email=args.enable_email,
                model_name=args.model_name,
                enable_vision=args.enable_vision,
                vision_model=args.vision_model,
            )
        )
    except KeyboardInterrupt:
        print("\nZhihu Analysis Service Stopped.")
