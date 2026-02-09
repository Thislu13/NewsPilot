#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-09 23:47:08
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-02-09 23:51:22
# FilePath: \NewsPilot\src\distribution\email_config.py
# Description: 
# 
# Copyright (c) 2026 by , All Rights Reserved. 

# Email Configuration
# 请在此处填写您的邮箱配置信息
EMAIL_CONFIG = {
    # SMTP 服务器地址
    "SMTP_SERVER": "smtp.163.com",
    
    # SMTP 服务器端口 
    "SMTP_PORT": 465,
    
    # 发件人邮箱地址
    "SENDER_EMAIL": "newspilot@163.com",
    
    # 发件人邮箱授权码 (不是登录密码，是 SMTP 服务开启时生成的授权码)
    "SENDER_PASSWORD": "TAUt7ESnM4VZk65v",
    
    # 收件人邮箱列表
    "RECEIVER_EMAILS": [
        "1835886867@qq.com",
    ]
}
