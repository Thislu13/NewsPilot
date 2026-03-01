#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-27 23:01:55
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-03-01 16:42:18
# FilePath: \NewsPilot\src\workflows\run_zhihu_analysis_service.py
# Description: 
# 知乎分析服务 - 启动采集守护进程和处理工作器
# 对知乎的指定用户发帖进行监控和分析，生成 Markdown 格式的分析报告，并通过邮件发送给用户。
# 依赖于一个独立的守护进程进行数据采集，分析服务通过轮询数据库获取待分析的文章，调用 LLM 进行内容分析，并记录分析结果和状态。
# Copyright (c) 2026 by WangQiushuo, All Rights Reserved. 

"""
知乎分析服务 - 入口文件

解析命令行参数并启动主服务的轻量化包装器。
"""

import asyncio
import sys

from .utils import ZhihuServiceConfig
from .service import ZhihuAnalysisService


def main():
    """
    解析命令行参数并启动知乎分析服务。
    """
    # 在 Windows 上设置事件循环策略
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 从命令行参数解析配置
    config = ZhihuServiceConfig.from_cli()

    # 创建并启动服务
    service = ZhihuAnalysisService(config)

    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        print("\n知乎分析服务已停止。")


if __name__ == "__main__":
    main()
