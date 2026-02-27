#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-09 01:19:33
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-02-27 23:43:56
# FilePath: \NewsPilot\config\settings.py
# Description: 
# 
# Copyright (c) 2026 by , All Rights Reserved. 

EMAIL_CONFIG = {
    "SMTP_SERVER": "smtp.163.com",
    "SMTP_PORT": 465,
    "SENDER_EMAIL": "newspilot@163.com",
    "SENDER_PASSWORD": "******",
    # fallback recipients when subscription DB has no active rows
    "RECEIVER_EMAILS": ["1835886867@qq.com"],
}


SUBSCRIPTION_ALLOWED_REPORT_KEYS = ["daily_report", "zhihu_dang_report"]
SUBSCRIPTION_ALLOWED_CHANNELS = ["email"]
