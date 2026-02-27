from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from src.storage.subscription_repository import SubscriptionRepository

try:
    from config.settings import EMAIL_CONFIG
except Exception:
    EMAIL_CONFIG = {}


DEFAULT_FALLBACK_RECEIVERS = ["1835886867@qq.com"]


def normalize_service_to_report_key(service_name: Optional[str]) -> str:
    value = (service_name or "daily_report").strip().lower()
    mapping = {
        "daily_report": "daily_report",
        "zhihu_dang_report": "zhihu_dang_report",
        "zhihu_analysis": "zhihu_dang_report",
    }
    return mapping.get(value, "daily_report")


def resolve_email_recipients(
    service_name: Optional[str],
    at_time: Optional[datetime] = None,
    fallback: bool = True,
) -> List[str]:
    report_key = normalize_service_to_report_key(service_name)
    repo = SubscriptionRepository()
    try:
        recipients = repo.get_active_accounts(
            report_key=report_key,
            channel_type="email",
            at_time=at_time,
        )
        if recipients:
            return recipients
    except Exception:
        # Keep email sending available even if DB lookup has issues.
        pass

    if not fallback:
        return []

    config_receivers = EMAIL_CONFIG.get("RECEIVER_EMAILS", [])
    if isinstance(config_receivers, list):
        cleaned = [str(x).strip() for x in config_receivers if str(x).strip()]
        if cleaned:
            return cleaned

    return DEFAULT_FALLBACK_RECEIVERS.copy()
