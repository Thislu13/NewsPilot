#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-09 01:19:33
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-01 21:48:32
# FilePath: \NewsPilot\config\settings.py
# Description: 
# 
# Copyright (c) 2026 by , All Rights Reserved. 


# 新闻源配置
NEWS_SOURCES_CONFIG = {
    "newsapi": {
        'flag': True,
    },
    "reuters": {
        'flag': True,
        "choice": ["reuters", "bloomberg", "eastmoney", "cls", "bbc", "ftchinese", "10jqka", "wallstreetcn"]
    }
}

RSS_CONFIG = {
    # https://docs.rsshub.app/routes/reuters
    # 路透社
    'reuters': {
        'url':'/reuters',
        "options":[
            '/world', '/business', '/legal', '/markets', '/breakingviews', '/technology'
        ]
    },
    # https://docs.rsshub.app/routes/eastmoney
    # 东方财富网
    # 该处返回的是研报表（概述部分相对比较完整了） 
    # 其中link 中返回的直接是pdf文件链接，后续考虑增加到支撑文件中
    'eastmoney': {
        'url':'/eastmoney/report',
        "options":[
            "/strategyreport", "/macresearch", "/brokerreport", "/industry"
        ]  
    },
    # https://docs.rsshub.app/routes/bloomberg
    # 彭博社
    # 没有description 字段
    'bloomberg': {
        'url':'/bloomberg',
        "options":[
        ]  
    },
    # https://docs.rsshub.app/routes/cls
    # 财联社
    # description 字段基本基本是全文
    'cls': {
        'url':'/cls/telegraph',
        "options":[]  
    },
    # https://docs.rsshub.app/routes/bbc
    # BBC
    'bbc': {
        'url':'/bbc',
        "options":[
        ]  
    },

    # https://docs.rsshub.app/routes/ftchinese
    # FT中文网
    # description 字段基本基本是全文
    'ftchinese': {
        'url':'/ftchinese/simplified',
        "options":[
        ]  
    },
    # https://docs.rsshub.app/routes/10jqka
    # 同花顺
    '10jqka': {
        'url':'/10jqka/realtimenews',
        "options":[
        ]  
    },

    # https://docs.rsshub.app/routes/wallstreetcn
    #华尔街见闻
    'wallstreetcn': {
        'url':'/wallstreetcn',
        "options":[
            '/live'
        ]
    },
}
ZHIHU_RSS_CONFIG = {
    # 知乎
    # https://docs.rsshub.app/routes/zhihu
    # 知乎
    # 用户动态（activities）示例：
    # http://localhost:1200/zhihu/people/activities/mr-dang-77
    'zhihu_people': {
        'url':'/zhihu',
        "options":[
            '/people/activities/',
            # '/posts/people/mr-dang-77',  # 用户发布的文章
            # '/answers/people/mr-dang-77',  # 用户的回答
            # '/people/pins/mr-dang-77',  # 用户的想法
        ]
    }
}




# 新闻处理流水线默认配置
NewsProcessingPipeline_DEFAULT_CONFIG = {
    "image_vision": {
        'flag': True,
        'model': "qwen",
        'model_id': "qwen-vl-plus",
        'attachments_root': "data/attachments",
        'max_concurrent': 5
    },
    "translator": {
        'flag': True,
        'model': "qwen",
        'model_id': "qwen-flash",
        'target_language': "zh",
        'max_concurrent': 5
    },
    "summarizer": {
        'flag': True,
        'model': "deepseek",
        'model_id': "deepseek-chat",
        'max_concurrent': 5
    },
    "embedding": {
        'flag': True,
        'model': "qwen",
        'model_id': "text-embedding-v4",
        'dimensions': 1024,
        'encoding_format': "float",
        'max_concurrent': 5
    }
}

# 邮件部分配置
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
