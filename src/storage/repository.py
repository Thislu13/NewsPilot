from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.db_config import db_manager
from src.storage.models import RawNews, RawNewsStaging, RefinedNews, SupportingDocument
from src.storage.models import ZhihuRawPost


class StorageRepository:
    """
    统一封装简单读写操作。
    - 支持外部传入 session（用于事务合并）
    - 不传 session 则内部自行创建并提交
    """

    def _get_session(self, session: Optional[Session]) -> Tuple[Session, bool]:
        """
        Args:
            session: 外部传入的 SQLAlchemy Session。

        Returns:
            (session, owns_session): 是否由本仓储创建。
        """
        if session is not None:
            return session, False
        return db_manager.get_session(), True

    def _finalize(self, session: Session, owns_session: bool, *, commit: bool = True) -> None:
        """
        Args:
            session: 当前 Session。
            owns_session: 是否由本仓储创建。
            commit: 是否提交事务（仅 owns_session=True 时生效）。
        """
        if not owns_session:
            return
        try:
            if commit:
                session.commit()
        finally:
            session.close()

    def _apply_date_range(self, stmt, field, date_from: Optional[datetime], date_to: Optional[datetime]):
        """
        Args:
            stmt: SQLAlchemy 查询语句。
            field: 用于筛选的时间字段。
            date_from: 起始时间（包含）。
            date_to: 结束时间（包含）。

        Returns:
            追加时间范围条件后的查询语句。
        """
        if date_from is not None:
            stmt = stmt.where(field >= date_from)
        if date_to is not None:
            stmt = stmt.where(field <= date_to)
        return stmt

    # ========================
    # RawNews
    # ========================
    def upsert_raw_news(self, items: Sequence[RawNews], session: Optional[Session] = None) -> None:
        """
        Args:
            items: RawNews ORM 对象列表。
            session: 可选外部 Session。
        """
        sess, owns = self._get_session(session)
        try:
            for item in items:
                sess.merge(item)
            self._finalize(sess, owns)
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def get_raw_news_by_id(self, unique_id: str, session: Optional[Session] = None) -> Optional[RawNews]:
        """
        Args:
            unique_id: RawNews 主键 ID。
            session: 可选外部 Session。

        Returns:
            RawNews 或 None。
        """
        sess, owns = self._get_session(session)
        try:
            stmt = select(RawNews).where(RawNews.unique_id == unique_id)
            result = sess.execute(stmt).scalar_one_or_none()
            return result
        finally:
            if owns:
                sess.close()

    def get_raw_news_by_ids(
        self,
        ids: Iterable[str],
        session: Optional[Session] = None,
    ) -> List[RawNews]:
        """
        Args:
            ids: RawNews 主键 ID 列表。
            session: 可选外部 Session。

        Returns:
            RawNews 列表。
        """
        sess, owns = self._get_session(session)
        try:
            id_list = list(ids)
            if not id_list:
                return []
            stmt = select(RawNews).where(RawNews.unique_id.in_(id_list))
            return list(sess.execute(stmt).scalars().all())
        finally:
            if owns:
                sess.close()

    def exists_raw_by_source_url(self, source_url: str, session: Optional[Session] = None) -> bool:
        """
        Args:
            source_url: 原始新闻 URL。
            session: 可选外部 Session。

        Returns:
            是否存在。
        """
        sess, owns = self._get_session(session)
        try:
            stmt = select(RawNews.unique_id).where(RawNews.source_url == source_url)
            return sess.execute(stmt).first() is not None
        finally:
            if owns:
                sess.close()

    def list_raw_news(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        *,
        date_field: str = "published_at",
        limit: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> List[RawNews]:
        """
        Args:
            date_from: 起始时间（包含）。
            date_to: 结束时间（包含）。
            date_field: 使用的时间字段（published_at/fetched_at）。
            limit: 返回数量上限。
            session: 可选外部 Session。

        Returns:
            RawNews 列表。
        """
        sess, owns = self._get_session(session)
        try:
            field = RawNews.published_at if date_field == "published_at" else RawNews.fetched_at
            stmt = select(RawNews)
            stmt = self._apply_date_range(stmt, field, date_from, date_to)
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(sess.execute(stmt).scalars().all())
        finally:
            if owns:
                sess.close()

    # ========================
    # RawNewsStaging
    # ========================
    def add_raw_news_staging(self, items: Sequence[RawNewsStaging], session: Optional[Session] = None) -> None:
        """
        Args:
            items: RawNewsStaging ORM 对象列表。
            session: 可选外部 Session。
        """
        sess, owns = self._get_session(session)
        try:
            for item in items:
                sess.add(item)
            self._finalize(sess, owns)
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def fetch_staging_pending(self, limit: int = 20, session: Optional[Session] = None) -> List[RawNewsStaging]:
        """
        Args:
            limit: 拉取条数。
            session: 可选外部 Session。

        Returns:
            RawNewsStaging 列表。
        """
        sess, owns = self._get_session(session)
        try:
            stmt = (
                select(RawNewsStaging)
                .where(RawNewsStaging.processing_status == "pending")
                .limit(limit)
            )
            return list(sess.execute(stmt).scalars().all())
        finally:
            if owns:
                sess.close()

    def reset_staging_statuses(
        self,
        from_statuses: Iterable[str],
        to_status: str = "pending",
        session: Optional[Session] = None,
    ) -> int:
        """
        Args:
            from_statuses: 需要重置的状态列表。
            to_status: 目标状态。
            session: 可选外部 Session。

        Returns:
            更新条数。
        """
        sess, owns = self._get_session(session)
        try:
            statuses = list(from_statuses)
            if not statuses:
                return 0
            count = (
                sess.query(RawNewsStaging)
                .filter(RawNewsStaging.processing_status.in_(statuses))
                .update({RawNewsStaging.processing_status: to_status}, synchronize_session=False)
            )
            self._finalize(sess, owns)
            return count
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def mark_staging_status(
        self,
        ids: Iterable[str],
        status: str,
        *,
        last_error: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> int:
        """
        Args:
            ids: staging 主键 ID 列表。
            status: 目标状态。
            last_error: 错误信息（可选）。
            session: 可选外部 Session。

        Returns:
            更新条数。
        """
        sess, owns = self._get_session(session)
        try:
            ids = list(ids)
            if not ids:
                return 0
            q = sess.query(RawNewsStaging).filter(RawNewsStaging.unique_id.in_(ids))
            values = {RawNewsStaging.processing_status: status}
            if last_error is not None:
                values[RawNewsStaging.last_error] = last_error
            count = q.update(values, synchronize_session=False)
            self._finalize(sess, owns)
            return count
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def delete_staging_by_ids(self, ids: Iterable[str], session: Optional[Session] = None) -> int:
        """
        Args:
            ids: staging 主键 ID 列表。
            session: 可选外部 Session。

        Returns:
            删除条数。
        """
        sess, owns = self._get_session(session)
        try:
            ids = list(ids)
            if not ids:
                return 0
            count = (
                sess.query(RawNewsStaging)
                .filter(RawNewsStaging.unique_id.in_(ids))
                .delete(synchronize_session=False)
            )
            self._finalize(sess, owns)
            return count
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def exists_staging_by_source_url(self, source_url: str, session: Optional[Session] = None) -> bool:
        """
        Args:
            source_url: 原始新闻 URL。
            session: 可选外部 Session。

        Returns:
            是否存在。
        """
        sess, owns = self._get_session(session)
        try:
            stmt = select(RawNewsStaging.unique_id).where(RawNewsStaging.source_url == source_url)
            return sess.execute(stmt).first() is not None
        finally:
            if owns:
                sess.close()

    # ========================
    # RefinedNews
    # ========================
    def upsert_refined_news(self, items: Sequence[RefinedNews], session: Optional[Session] = None) -> None:
        """
        Args:
            items: RefinedNews ORM 对象列表。
            session: 可选外部 Session。
        """
        sess, owns = self._get_session(session)
        try:
            for item in items:
                sess.merge(item)
            self._finalize(sess, owns)
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def get_refined_by_raw_id(self, raw_id: str, session: Optional[Session] = None) -> Optional[RefinedNews]:
        """
        Args:
            raw_id: RawNews 主键 ID。
            session: 可选外部 Session。

        Returns:
            RefinedNews 或 None。
        """
        sess, owns = self._get_session(session)
        try:
            stmt = select(RefinedNews).where(RefinedNews.news_item_raw_id == raw_id)
            return sess.execute(stmt).scalar_one_or_none()
        finally:
            if owns:
                sess.close()

    def list_refined_news(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        *,
        date_field: str = "published_at",
        limit: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> List[RefinedNews]:
        """
        Args:
            date_from: 起始时间（包含）。
            date_to: 结束时间（包含）。
            date_field: 使用的时间字段（published_at/fetched_at）。
            limit: 返回数量上限。
            session: 可选外部 Session。

        Returns:
            RefinedNews 列表。
        """
        sess, owns = self._get_session(session)
        try:
            field = RefinedNews.published_at if date_field == "published_at" else RefinedNews.fetched_at
            stmt = select(RefinedNews)
            stmt = self._apply_date_range(stmt, field, date_from, date_to)
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(sess.execute(stmt).scalars().all())
        finally:
            if owns:
                sess.close()

    # ========================
    # SupportingDocument
    # ========================
    def add_supporting_documents(
        self,
        items: Sequence[SupportingDocument],
        session: Optional[Session] = None,
    ) -> None:
        """
        Args:
            items: SupportingDocument ORM 对象列表。
            session: 可选外部 Session。
        """
        sess, owns = self._get_session(session)
        try:
            for item in items:
                sess.add(item)
            self._finalize(sess, owns)
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def get_supporting_by_url(self, source_url: str, session: Optional[Session] = None) -> Optional[SupportingDocument]:
        """
        Args:
            source_url: 文档 URL。
            session: 可选外部 Session。

        Returns:
            SupportingDocument 或 None。
        """
        sess, owns = self._get_session(session)
        try:
            stmt = select(SupportingDocument).where(SupportingDocument.source_url == source_url)
            return sess.execute(stmt).scalar_one_or_none()
        finally:
            if owns:
                sess.close()

    def list_supporting_documents(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        *,
        date_field: str = "published_at",
        limit: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> List[SupportingDocument]:
        """
        Args:
            date_from: 起始时间（包含）。
            date_to: 结束时间（包含）。
            date_field: 使用的时间字段（published_at/fetched_at）。
            limit: 返回数量上限。
            session: 可选外部 Session。

        Returns:
            SupportingDocument 列表。
        """
        sess, owns = self._get_session(session)
        try:
            field = SupportingDocument.published_at if date_field == "published_at" else SupportingDocument.fetched_at
            stmt = select(SupportingDocument)
            stmt = self._apply_date_range(stmt, field, date_from, date_to)
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(sess.execute(stmt).scalars().all())
        finally:
            if owns:
                sess.close()

    # ========================
    # ZhihuRawPost
    # ========================
    def add_zhihu_raw_posts(self, items: Sequence[ZhihuRawPost], session: Optional[Session] = None) -> None:
        sess, owns = self._get_session(session)
        try:
            for item in items:
                sess.add(item)
            self._finalize(sess, owns)
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def exists_zhihu_raw_by_source_url(self, source_url: str, session: Optional[Session] = None) -> bool:
        sess, owns = self._get_session(session)
        try:
            stmt = select(ZhihuRawPost.unique_id).where(ZhihuRawPost.source_url == source_url)
            return sess.execute(stmt).first() is not None
        finally:
            if owns:
                sess.close()

    def fetch_zhihu_raw_pending(self, limit: int = 20, session: Optional[Session] = None) -> List[ZhihuRawPost]:
        sess, owns = self._get_session(session)
        try:
            stmt = (
                select(ZhihuRawPost)
                .where(ZhihuRawPost.status == "pending")
                .limit(limit)
            )
            return list(sess.execute(stmt).scalars().all())
        finally:
            if owns:
                sess.close()

    def reset_zhihu_raw_statuses(
        self,
        from_statuses: Iterable[str],
        to_status: str = "pending",
        session: Optional[Session] = None,
    ) -> int:
        sess, owns = self._get_session(session)
        try:
            statuses = list(from_statuses)
            if not statuses:
                return 0
            count = (
                sess.query(ZhihuRawPost)
                .filter(ZhihuRawPost.status.in_(statuses))
                .update({ZhihuRawPost.status: to_status}, synchronize_session=False)
            )
            self._finalize(sess, owns)
            return count
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def mark_zhihu_raw_status(
        self,
        ids: Iterable[str],
        status: str,
        *,
        session: Optional[Session] = None,
    ) -> int:
        sess, owns = self._get_session(session)
        try:
            ids = list(ids)
            if not ids:
                return 0
            q = sess.query(ZhihuRawPost).filter(ZhihuRawPost.unique_id.in_(ids))
            values = {ZhihuRawPost.status: status}
            count = q.update(values, synchronize_session=False)
            self._finalize(sess, owns)
            return count
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

