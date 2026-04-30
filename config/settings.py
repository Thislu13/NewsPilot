#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-09 01:19:33
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-09 00:32:42
# FilePath: \NewsPilot\config\settings.py
# Description: 
# 
# Copyright (c) 2026 by , All Rights Reserved. 


# 新闻源配置
NEWS_SOURCES_CONFIG = {
    "newsapi": {
        'flag': False,
    },
    "rsshub": {
        'flag': True,
        "choice": ["reuters", "bloomberg", "eastmoney", "cls", "bbc", "ftchinese", "10jqka", "wallstreetcn", "jin10"]
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

    # https://docs.rsshub.app/zh/routes/jin10
    # 金十数据
    'jin10': {
        'url':'/jin10',
        "options":[
        ]  
    },
}

ZHIHU_RSS_CONFIG = {
    # 知乎
    # https://docs.rsshub.app/routes/zhihu
    # 知乎
    # 用户动态（activities）示例：
    # http://localhost:1200/zhihu/people/activities/mr-dang-77
    'sources': {
        'zhihu_people': {
            'url': '/zhihu',
            'options': [
                '/people/activities/',
                # '/posts/people/mr-dang-77',  # 用户发布的文章
                # '/answers/people/mr-dang-77',  # 用户的回答
                # '/people/pins/mr-dang-77',  # 用户的想法
            ]
        }
    },
    'author_list': ['mr-dang-77']
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
        'model': "qwen",
        'model_id': "qwen-flash",
        'max_concurrent': 5
    },
    "embedding": {
        'flag': False,
        'model': "qwen",
        'model_id': "text-embedding-v4",
        'dimensions': 1024,
        'encoding_format': "float",
        'max_concurrent': 5
    },
    "event_extraction": {
        'flag': True,
        'model': "qwen",
        'model_id': "qwen-flash",
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


# ============================================================
# 建图配置
# ============================================================

# 建图守护进程
GRAPH_DAEMON_CONFIG = {
    "ingest_hours": [0, 6, 12, 18],  # UTC 定点建图时间
    "periodic_update_weekday": 6,     # UTC 周日=6, 定期描述更新
    "periodic_update_hour": 22,       # UTC 22:00 执行定期更新
}

# UMAP 全局模型
UMAP_GLOBAL_N_NEIGHBORS = 10
UMAP_GLOBAL_MIN_DIST = 0.0
UMAP_GLOBAL_METRIC = "cosine"
UMAP_GLOBAL_N_COMPONENTS = 30

# UMAP 分裂场景
UMAP_SPLIT_N_NEIGHBORS = 8
UMAP_SPLIT_N_COMPONENTS = 2

# HDBSCAN 初始聚类
HDBSCAN_MIN_CLUSTER_SIZE = 5
HDBSCAN_MIN_SAMPLES = 1
HDBSCAN_METRIC = "euclidean"

# HDBSCAN 分裂场景
HDBSCAN_SPLIT_MIN_CLUSTER_SIZE = 5
HDBSCAN_SPLIT_MIN_SAMPLES = 2

# 阈值
MATCH_THRESHOLD = 0.6
SPLIT_THRESHOLD = 100
MERGE_THRESHOLD_INNER = 0.85
MERGE_THRESHOLD_CROSS = 0.90
DEDUP_THRESHOLD = 0.95
MAX_MEMBERSHIPS = 5
BATCH_SIZE = 200

# Embedding
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_ENCODING_FORMAT = "float"

# 建图 LLM
GRAPH_LLM_MODEL = "qwen3.5-flash"
GRAPH_LLM_TIMEOUT = 90
GRAPH_LLM_MAX_RETRIES = 3
GRAPH_LLM_MAX_SAMPLE = 500

# 模型持久化
MODEL_DIR = "models"
UMAP_MODEL_FILE = "umap_global.pkl"
