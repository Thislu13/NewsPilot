import os
import smtplib
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

try:
    from config.settings import EMAIL_CONFIG
except Exception:
    try:
        from .email_config import EMAIL_CONFIG  # type: ignore
    except Exception:
        try:
            from email_config import EMAIL_CONFIG  # type: ignore
        except Exception:
            EMAIL_CONFIG = {}

try:
    from src.distribution.recipient_provider import resolve_email_recipients
except Exception:
    from .recipient_provider import resolve_email_recipients  # type: ignore


def send_daily_report_email(
    subject: str,
    html_body_path: Optional[str] = None,
    attachment_paths: Optional[List[str]] = None,
    service_name: Optional[str] = None,
):
    """
    Send report email with optional HTML body and attachments.
    """
    smtp_server = EMAIL_CONFIG.get("SMTP_SERVER")
    smtp_port = EMAIL_CONFIG.get("SMTP_PORT", 465)
    sender_email = EMAIL_CONFIG.get("SENDER_EMAIL")
    sender_password = EMAIL_CONFIG.get("SENDER_PASSWORD")

    receiver_emails = resolve_email_recipients(
        service_name=service_name,
        fallback=True,
    )

    if not sender_email or not sender_password or not receiver_emails:
        print(f"[email] config is incomplete or no recipients found. service={service_name}")
        return

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = ",".join(receiver_emails)
    message["Subject"] = Header(subject, "utf-8")

    if html_body_path and os.path.exists(html_body_path):
        try:
            with open(html_body_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            message.attach(MIMEText(html_content, "html", "utf-8"))
        except Exception as e:
            print(f"[email] failed to load HTML body: {e}")
            message.attach(MIMEText("Unable to load HTML body. Please check attachments.", "plain", "utf-8"))
    else:
        message.attach(MIMEText("Daily report generated. Please see attachments.", "plain", "utf-8"))

    if attachment_paths:
        for file_path in attachment_paths:
            if not file_path or not os.path.exists(file_path):
                print(f"[email] attachment not found, skipped: {file_path}")
                continue

            try:
                filename = os.path.basename(file_path)
                with open(file_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=("utf-8", "", filename),
                )
                message.attach(part)
                print(f"[email] attached: {filename}")
            except Exception as e:
                print(f"[email] failed to attach file ({file_path}): {e}")

    try:
        print(f"[email] sending via {smtp_server} to {len(receiver_emails)} recipients...")
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.send_message(message)
        print("[email] sent successfully.")
    except Exception as e:
        print(f"[email] failed to send: {e}")


if __name__ == "__main__":
    print("Testing email sender...")
