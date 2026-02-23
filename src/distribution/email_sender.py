import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from typing import List, Optional
try:
    from .email_config import EMAIL_CONFIG
except ImportError:
    # Fallback for direct execution
    from email_config import EMAIL_CONFIG

def send_daily_report_email(
    subject: str,
    html_body_path: Optional[str] = None,
    attachment_paths: Optional[List[str]] = None,
    service_name: Optional[str] = None  # 新增参数
):
    """
    发送日报邮件
    :param subject: 邮件主题
    :param html_body_path: 作为邮件正文的 HTML 文件路径
    :param attachment_paths: 需要作为附件发送的文件路径列表 (PDF等)
    :param service_name: 服务名称（如 'zhihu_analysis', 'daily_report'），用于选择特定收件人
    """
    smtp_server = EMAIL_CONFIG.get("SMTP_SERVER")
    smtp_port = EMAIL_CONFIG.get("SMTP_PORT", 465)
    sender_email = EMAIL_CONFIG.get("SENDER_EMAIL")
    sender_password = EMAIL_CONFIG.get("SENDER_PASSWORD")

    # 根据service_name选择收件人
    if service_name and "SERVICE_RECEIVERS" in EMAIL_CONFIG:
        receiver_emails = EMAIL_CONFIG["SERVICE_RECEIVERS"].get(
            service_name,
            EMAIL_CONFIG.get("RECEIVER_EMAILS", [])  # 回退到默认
        )
    else:
        receiver_emails = EMAIL_CONFIG.get("RECEIVER_EMAILS", [])

    if not sender_email or not sender_password or not receiver_emails:
        print(f"⚠️ 邮件配置不完整 (service: {service_name})，跳过邮件发送。")
        return

    # 构建邮件
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = ",".join(receiver_emails)
    message["Subject"] = Header(subject, "utf-8")

    # 1. 设置正文 (HTML)
    if html_body_path and os.path.exists(html_body_path):
        try:
            with open(html_body_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            message.attach(MIMEText(html_content, "html", "utf-8"))
        except Exception as e:
            print(f"❌ 读取 HTML 正文失败: {e}")
            message.attach(MIMEText("无法读取 HTML 正文，请查看附件。", "plain", "utf-8"))
    else:
        message.attach(MIMEText("今日日报已生成，请查看附件。", "plain", "utf-8"))

    # 2. 添加附件
    if attachment_paths:
        for file_path in attachment_paths:
            if not file_path or not os.path.exists(file_path):
                print(f"⚠️ 附件不存在，跳过: {file_path}")
                continue
            
            try:
                # 获取文件名 (如果是中文文件名，Header会自动处理吗？通常需要特别处理)
                filename = os.path.basename(file_path)
                
                with open(file_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                
                encoders.encode_base64(part)
                # 处理中文文件名乱码问题 (使用 Header 编码) or standard RFC2231
                # method 1: Header object
                # part.add_header("Content-Disposition", f"attachment; filename={filename}")
                # method 2: explicit encoding for non-ascii
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=("utf-8", "", filename)
                )
                
                message.attach(part)
                print(f"📎 已添加附件: {filename}")
            except Exception as e:
                print(f"❌ 添加附件失败 ({file_path}): {e}")

    # 3. 发送邮件
    try:
        print(f"📧 正在通过 {smtp_server} 发送邮件给 {len(receiver_emails)} 位收件人...")
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.send_message(message) # send_message handles list of recipients better than sendmail with string
        print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {str(e)}")

if __name__ == "__main__":
    # Test
    print("Testing email sender...")
    # You can uncomment below to test if config is filled
    # send_daily_report_email("Test Subject", None, None)
