#
# Author: WangQiushuo 185886867@qq.com
# Date: 2026-02-19 00:01:59
# LastEditors: WangQiushuo 185886867@qq.com
# LastEditTime: 2026-02-23 17:59:14
# FilePath: \NewsPilot\src\workflows\run_service.py
# Description: 
# 
# Copyright (c) 2026 by , All Rights Reserved. 

"""
统一服务启动入口。
根据配置文件启动：
- news: 原新闻抓取/翻译/摘要服务
- zhihu_analysis: 知乎抓取与隐含表达分析服务
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from src.data_acquisition.daemon_orchestrator import DaemonOrchestrator



def _load_config(config_path: str | None = None) -> Dict[str, Any]:
    path = Path(config_path or "config/workflow_service.json")
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.as_posix()}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def main(config_path: str | None = None):
    cfg = _load_config(config_path)
    service = (cfg.get("service") or "news").strip().lower()

    if service == "news":
        daemon = DaemonOrchestrator(
            fetch_interval=int(cfg.get("fetch_interval", 60 * 120)),
            process_interval=int(cfg.get("process_interval", 60)),
            batch_size=int(cfg.get("batch_size", 20)),
        )
        print(f"\n🚀 Unified Service Started [news] [PID: {os.getpid()}]")
    elif service == "zhihu_analysis":
        daemon = ZhihuAnalysisOrchestrator(
            fetch_interval=int(cfg.get("fetch_interval", 60 * 120)),
            process_interval=int(cfg.get("process_interval", 60)),
            batch_size=int(cfg.get("batch_size", 10)),
            model_name=str(cfg.get("model_name", "gemini")),
            markdown_output_dir=str(cfg.get("markdown_output_dir", "data/zhihu_analysis_md")),
        )
        print(f"\n🚀 Unified Service Started [zhihu_analysis] [PID: {os.getpid()}]")
    else:
        raise ValueError(f"Unsupported service type: {service}")

    print(f"├─ 📡 Auto-Fetch: Every {cfg.get('fetch_interval', 60 * 120)}s")
    print(f"├─ ⚙️ Worker Polling: Every {cfg.get('process_interval', 60)}s")
    print("└─ 🛑 Press Ctrl+C to stop...\n")

    await daemon.start()


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    arg_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        asyncio.run(main(arg_path))
    except KeyboardInterrupt:
        print("\n👋 Service Stopped.")
