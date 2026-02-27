from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from src.storage import db_manager
from src.storage.subscription_repository import SubscriptionRepository


STATIC_HTML = Path(__file__).parent / "static" / "subscription_admin.html"


def parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    v = value.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def serialize_target(row) -> Dict[str, Any]:
    return {
        "id": row.id,
        "channel_type": row.channel_type,
        "account": row.account,
        "report_key": row.report_key,
        "active_from": row.active_from.isoformat() if row.active_from else None,
        "active_to": row.active_to.isoformat() if row.active_to else None,
        "is_enabled": bool(row.is_enabled),
        "extra_data": row.extra_data,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class SubscriptionAdminHandler(BaseHTTPRequestHandler):
    repo = SubscriptionRepository()

    def log_message(self, format: str, *args) -> None:
        return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, html_text: str) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _extract_id(self, path: str) -> Optional[str]:
        # /api/subscriptions/{id}
        # /api/subscriptions/{id}/enable
        # /api/subscriptions/{id}/disable
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "subscriptions":
            return parts[2]
        return None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in {"/", "/index.html"}:
            if not STATIC_HTML.exists():
                self._send_html(404, "subscription_admin.html not found")
                return
            self._send_html(200, STATIC_HTML.read_text(encoding="utf-8"))
            return

        if path == "/api/subscriptions":
            try:
                report_key = (query.get("report_key") or [None])[0]
                channel_type = (query.get("channel_type") or [None])[0]
                keyword = (query.get("keyword") or [None])[0]
                limit_raw = (query.get("limit") or ["200"])[0]
                is_enabled_raw = (query.get("is_enabled") or [None])[0]

                rows = self.repo.list_subscription_targets(
                    report_key=report_key or None,
                    channel_type=channel_type or None,
                    is_enabled=parse_bool(is_enabled_raw),
                    keyword=keyword or None,
                    limit=max(1, min(int(limit_raw), 1000)),
                )
                self._send_json(200, {"items": [serialize_target(r) for r in rows]})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        if path == "/api/recipients/preview":
            report_key = (query.get("report_key") or [None])[0]
            if not report_key:
                self._send_json(400, {"error": "report_key is required"})
                return
            try:
                recipients = self.repo.get_active_accounts(report_key=report_key, channel_type="email")
                self._send_json(
                    200,
                    {
                        "report_key": report_key,
                        "count": len(recipients),
                        "recipients": recipients,
                    },
                )
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        self._send_json(404, {"error": "Not Found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/subscriptions":
            try:
                body = self._read_json()
                row = self.repo.create_subscription_target(
                    channel_type=body.get("channel_type", "email"),
                    account=body["account"],
                    report_key=body["report_key"],
                    active_from=parse_iso_datetime(body.get("active_from")),
                    active_to=parse_iso_datetime(body.get("active_to")),
                    is_enabled=bool(body.get("is_enabled", True)),
                    extra_data=body.get("extra_data"),
                )
                self._send_json(201, {"item": serialize_target(row)})
            except KeyError as e:
                self._send_json(400, {"error": f"Missing required field: {e}"})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        if path.endswith("/enable") or path.endswith("/disable"):
            target_id = self._extract_id(path)
            if not target_id:
                self._send_json(400, {"error": "Invalid path"})
                return
            try:
                enabled = path.endswith("/enable")
                ok = self.repo.set_enabled(target_id, enabled)
                if not ok:
                    self._send_json(404, {"error": "target not found"})
                    return
                row = self.repo.get_subscription_target_by_id(target_id)
                if row is None:
                    self._send_json(404, {"error": "target not found"})
                    return
                self._send_json(200, {"item": serialize_target(row)})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        self._send_json(404, {"error": "Not Found"})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        target_id = self._extract_id(path)
        if not target_id or not path.startswith("/api/subscriptions/"):
            self._send_json(404, {"error": "Not Found"})
            return
        try:
            body = self._read_json()
            updates = {}
            if "channel_type" in body:
                updates["channel_type"] = body["channel_type"]
            if "account" in body:
                updates["account"] = body["account"]
            if "report_key" in body:
                updates["report_key"] = body["report_key"]
            if "active_from" in body:
                updates["active_from"] = parse_iso_datetime(body["active_from"])
            if "active_to" in body:
                updates["active_to"] = parse_iso_datetime(body["active_to"])
            if "is_enabled" in body:
                updates["is_enabled"] = body["is_enabled"]
            if "extra_data" in body:
                updates["extra_data"] = body["extra_data"]

            row = self.repo.update_subscription_target(
                target_id=target_id,
                **updates,
            )
            if row is None:
                self._send_json(404, {"error": "target not found"})
                return
            self._send_json(200, {"item": serialize_target(row)})
        except Exception as e:
            self._send_json(400, {"error": str(e)})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        target_id = self._extract_id(path)
        if not target_id or not path.startswith("/api/subscriptions/"):
            self._send_json(404, {"error": "Not Found"})
            return
        try:
            ok = self.repo.delete_subscription_target(target_id)
            if not ok:
                self._send_json(404, {"error": "target not found"})
                return
            self._send_json(200, {"ok": True})
        except Exception as e:
            self._send_json(400, {"error": str(e)})


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    db_manager.verify_and_create_tables()
    server = ThreadingHTTPServer((host, port), SubscriptionAdminHandler)
    print(f"[subscription_admin] server running at http://{host}:{port}")
    server.serve_forever()
