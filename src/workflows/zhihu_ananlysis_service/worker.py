# -*- coding: utf-8 -*-
"""
知乎分析服务处理工作器

处理获取、分析和持久化文章的核心轮询循环。
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.intelligence.zhihu_analyzer import ZhihuAnalyzer
from src.intelligence.renderers import ZhihuDangReportRenderer
from src.storage import db_manager, StorageRepository, ZhihuRawPost
from .utils import (
    reconstruct_body_with_captions,
    save_markdown_file,
    save_json_file,
    send_markdown_email,
    MARKDOWN_DIR,
    FIRST_RUN_FLAG,
)


class ZhihuProcessingWorker:
    """
    知乎文章处理工作器。

    从数据库轮询待处理文章，使用 LLM 分析，生成 Markdown，
    持久化输出，并发送邮件通知。
    """

    def __init__(
        self,
        batch_size: int = 10,
        process_interval: int = 5,
        model_name: str = "gemini",
        model_id: Optional[str] = None,
        enable_email: bool = True,
        skip_email: bool = False,
    ):
        """
        初始化处理工作器。

        参数：
            batch_size: 每批处理的文章数
            process_interval: 无任务时的休眠间隔（秒）
            model_name: 用于分析的 LLM 模型名称
            model_id: 可选的 LLM 模型 ID 覆盖
            enable_email: 是否启用邮件发送
            skip_email: 是否跳过此次运行的邮件
        """
        self.batch_size = batch_size
        self.process_interval = process_interval
        self.model_name = model_name
        self.model_id = model_id
        self.enable_email = enable_email
        self.skip_email = skip_email

        self.repo = StorageRepository()
        self.analyzer = ZhihuAnalyzer(model_name=model_name, model_id=model_id)

    async def run(self):
        """
        启动处理工作器循环。

        持续轮询待处理文章并分批处理。
        """
        print(
            f"[Processing] Worker started (batch_size={self.batch_size}, "
            f"interval={self.process_interval}s)"
        )

        while True:
            processing_ids: List[str] = []
            session = None

            try:
                session = db_manager.get_session()

                # 1. 查询待处理文章
                MAX_RETRIES = 3
                rows = (
                    session.query(ZhihuRawPost)
                    .filter(ZhihuRawPost.status == "pending")
                    .limit(self.batch_size * 2)  # Fetch extra for filtering
                    .all()
                )

                # 过滤有效行并标记超期重试为失败
                valid_rows = []
                skip_rows = []
                for r in rows:
                    retry_count = (r.extra_data or {}).get("retry_count", 0)
                    if retry_count >= MAX_RETRIES:
                        skip_rows.append(r)
                    else:
                        valid_rows.append(r)
                        if len(valid_rows) >= self.batch_size:
                            break

                # 标记超重试行为失败
                if skip_rows:
                    skip_ids = [r.unique_id for r in skip_rows]
                    self.repo.mark_zhihu_raw_status(skip_ids, "failed", session=session)
                    for r in skip_rows:
                        r.extra_data = {
                            **(r.extra_data or {}),
                            "failed_reason": "Max retries exceeded",
                            "failed_at": datetime.now().isoformat()
                        }
                    session.commit()
                    print(
                        f"[Processing] ⚠️  Marked {len(skip_rows)} items "
                        "as failed (max retries exceeded)"
                    )

                rows = valid_rows
                if not rows:
                    session.close()
                    await asyncio.sleep(self.process_interval)
                    continue

                print(f"[Processing] Picked up {len(rows)} pending items")
                processing_ids = [r.unique_id for r in rows]

                # 2. 标记为处理中
                self.repo.mark_zhihu_raw_status(processing_ids, "processing", session=session)
                session.commit()

                # 3. 使用说明组装数据
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

                # 4. 分析文章
                results: List[tuple[str, bool, str, str]] = []
                for row in rows_data:
                    results.append(await self._analyze_one(row))

                success_ids: List[str] = [rid for rid, ok, _, _ in results if ok]
                markdown_paths: dict[str, str] = {
                    rid: path for rid, ok, path, _ in results if ok
                }

                # 记录失败项
                failed_results = [(rid, err) for rid, ok, _, err in results if not ok]
                if failed_results:
                    print("[Processing] ❌ Failed items details:")
                    for rid, err in failed_results:
                        print(f"  - {rid}: {err}")

                # 5. 更新数据库状态
                session = db_manager.get_session()
                if success_ids:
                    self.repo.mark_zhihu_raw_status(
                        success_ids, "completed", session=session
                    )

                    # 用 Markdown 路径更新 extra_data
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
                    failed_errors = {rid: err for rid, ok, _, err in results if not ok}

                    # 增加重试计数并标记为待重试
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

                    # 标记为待重试
                    self.repo.mark_zhihu_raw_status(
                        list(failed_ids),
                        "pending",
                        session=session,
                    )

                session.commit()
                session.close()

                print(f"[Processing] Completed: {len(success_ids)}, Failed: {len(failed_ids)}")

                # 6. 发送邮件通知
                if self.enable_email and not self.skip_email and success_ids:
                    for rid in success_ids:
                        md_path = markdown_paths.get(rid)
                        if md_path:
                            await send_markdown_email(Path(md_path))

            except Exception as e:
                print(f"[Processing] Error: {e}")
                if session and session.is_active:
                    session.rollback()
                # 恢复处理项为待处理
                if processing_ids:
                    try:
                        sess2 = db_manager.get_session()
                        self.repo.mark_zhihu_raw_status(processing_ids, "pending", session=sess2)
                        sess2.commit()
                        sess2.close()
                    except Exception:
                        pass
                await asyncio.sleep(10)
            finally:
                if session:
                    session.close()

    async def _analyze_one(self, row: dict) -> tuple[str, bool, str, str]:
        """
        分析单个文章。

        参数：
            row: 文章数据字典

        返回：
            元组 (unique_id, 是否成功, markdown_路径, 错误消息)
        """
        try:
            # 1. 调用 LLM 分析
            llm_output = await self.analyzer.analyze_single(
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
