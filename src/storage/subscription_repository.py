from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.module.utils import generate_uuid7
from src.storage.db_config import db_manager
from src.storage.models import SubscriptionTarget

try:
    from config.settings import (
        SUBSCRIPTION_ALLOWED_CHANNELS,
        SUBSCRIPTION_ALLOWED_REPORT_KEYS,
    )
except Exception:
    SUBSCRIPTION_ALLOWED_REPORT_KEYS = ["daily_report", "zhihu_dang_report"]
    SUBSCRIPTION_ALLOWED_CHANNELS = ["email"]


_UNSET = object()


class SubscriptionRepository:
    def _get_session(self, session: Optional[Session]) -> Tuple[Session, bool]:
        if session is not None:
            return session, False
        return db_manager.get_session(), True

    def _finalize(self, session: Session, owns_session: bool, *, commit: bool = True) -> None:
        if not owns_session:
            return
        try:
            if commit:
                session.commit()
        finally:
            session.close()

    @staticmethod
    def _validate_channel_type(channel_type: str) -> str:
        value = (channel_type or "").strip().lower()
        if value not in SUBSCRIPTION_ALLOWED_CHANNELS:
            raise ValueError(f"Unsupported channel_type: {channel_type}")
        return value

    @staticmethod
    def _validate_report_key(report_key: str) -> str:
        value = (report_key or "").strip().lower()
        if value not in SUBSCRIPTION_ALLOWED_REPORT_KEYS:
            raise ValueError(f"Unsupported report_key: {report_key}")
        return value

    @staticmethod
    def _normalize_account(account: str) -> str:
        value = (account or "").strip()
        if not value:
            raise ValueError("account cannot be empty")
        return value

    @staticmethod
    def _validate_time_range(active_from: Optional[datetime], active_to: Optional[datetime]) -> None:
        if active_from is not None and active_to is not None and active_from > active_to:
            raise ValueError("active_from must be earlier than or equal to active_to")

    def create_subscription_target(
        self,
        *,
        channel_type: str = "email",
        account: str,
        report_key: str,
        active_from: Optional[datetime] = None,
        active_to: Optional[datetime] = None,
        is_enabled: bool = True,
        extra_data: Optional[Dict[str, Any]] = None,
        target_id: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> SubscriptionTarget:
        channel = self._validate_channel_type(channel_type)
        report = self._validate_report_key(report_key)
        normalized_account = self._normalize_account(account)
        self._validate_time_range(active_from, active_to)

        sess, owns = self._get_session(session)
        try:
            row = SubscriptionTarget(
                id=target_id or generate_uuid7(),
                channel_type=channel,
                account=normalized_account,
                report_key=report,
                active_from=active_from,
                active_to=active_to,
                is_enabled=bool(is_enabled),
                extra_data=extra_data or None,
            )
            sess.add(row)
            sess.flush()
            row_id = row.id
            self._finalize(sess, owns)
            if owns:
                fresh = self.get_subscription_target_by_id(row_id)
                if fresh is None:
                    raise RuntimeError("Failed to load created subscription target")
                return fresh
            return row
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def get_subscription_target_by_id(
        self,
        target_id: str,
        session: Optional[Session] = None,
    ) -> Optional[SubscriptionTarget]:
        sess, owns = self._get_session(session)
        try:
            stmt = select(SubscriptionTarget).where(SubscriptionTarget.id == target_id)
            return sess.execute(stmt).scalar_one_or_none()
        finally:
            if owns:
                sess.close()

    def update_subscription_target(
        self,
        target_id: str,
        *,
        channel_type: Any = _UNSET,
        account: Any = _UNSET,
        report_key: Any = _UNSET,
        active_from: Any = _UNSET,
        active_to: Any = _UNSET,
        is_enabled: Any = _UNSET,
        extra_data: Any = _UNSET,
        session: Optional[Session] = None,
    ) -> Optional[SubscriptionTarget]:
        sess, owns = self._get_session(session)
        try:
            row = self.get_subscription_target_by_id(target_id, session=sess)
            if row is None:
                return None

            if channel_type is not _UNSET:
                row.channel_type = self._validate_channel_type(channel_type)
            if account is not _UNSET:
                row.account = self._normalize_account(account)
            if report_key is not _UNSET:
                row.report_key = self._validate_report_key(report_key)
            if active_from is not _UNSET:
                row.active_from = active_from
            if active_to is not _UNSET:
                row.active_to = active_to
            if is_enabled is not _UNSET:
                row.is_enabled = bool(is_enabled)
            if extra_data is not _UNSET:
                row.extra_data = extra_data

            self._validate_time_range(row.active_from, row.active_to)
            row_id = row.id
            self._finalize(sess, owns)
            if owns:
                return self.get_subscription_target_by_id(row_id)
            return row
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def delete_subscription_target(self, target_id: str, session: Optional[Session] = None) -> bool:
        sess, owns = self._get_session(session)
        try:
            row = self.get_subscription_target_by_id(target_id, session=sess)
            if row is None:
                return False
            sess.delete(row)
            self._finalize(sess, owns)
            return True
        except Exception:
            if owns:
                sess.rollback()
                sess.close()
            raise

    def list_subscription_targets(
        self,
        report_key: Optional[str] = None,
        channel_type: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        keyword: Optional[str] = None,
        limit: int = 200,
        session: Optional[Session] = None,
    ) -> List[SubscriptionTarget]:
        sess, owns = self._get_session(session)
        try:
            stmt = select(SubscriptionTarget)
            if report_key:
                stmt = stmt.where(SubscriptionTarget.report_key == self._validate_report_key(report_key))
            if channel_type:
                stmt = stmt.where(SubscriptionTarget.channel_type == self._validate_channel_type(channel_type))
            if is_enabled is not None:
                stmt = stmt.where(SubscriptionTarget.is_enabled == bool(is_enabled))
            if keyword:
                stmt = stmt.where(SubscriptionTarget.account.ilike(f"%{keyword.strip()}%"))
            stmt = stmt.order_by(SubscriptionTarget.created_at.desc(), SubscriptionTarget.account.asc()).limit(limit)
            return list(sess.execute(stmt).scalars().all())
        finally:
            if owns:
                sess.close()

    def get_active_accounts(
        self,
        report_key: str,
        channel_type: str = "email",
        at_time: Optional[datetime] = None,
        session: Optional[Session] = None,
    ) -> List[str]:
        report = self._validate_report_key(report_key)
        channel = self._validate_channel_type(channel_type)
        now = at_time or datetime.now(timezone.utc)

        sess, owns = self._get_session(session)
        try:
            stmt = (
                select(SubscriptionTarget.account)
                .where(SubscriptionTarget.report_key == report)
                .where(SubscriptionTarget.channel_type == channel)
                .where(SubscriptionTarget.is_enabled.is_(True))
                .where(or_(SubscriptionTarget.active_from.is_(None), SubscriptionTarget.active_from <= now))
                .where(or_(SubscriptionTarget.active_to.is_(None), SubscriptionTarget.active_to >= now))
            )
            accounts = [r[0] for r in sess.execute(stmt).all()]
            return sorted(set(accounts))
        finally:
            if owns:
                sess.close()

    def set_enabled(
        self,
        target_id: str,
        is_enabled: bool,
        session: Optional[Session] = None,
    ) -> bool:
        row = self.update_subscription_target(
            target_id=target_id,
            is_enabled=is_enabled,
            session=session,
        )
        return row is not None
