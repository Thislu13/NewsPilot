"""远程数据库推送模块

每次入库完成后调用 push_to_remote()，触发 scripts/sync_to_server.sh：
  - pg_dump 3 张表（processed_events, event_clusters, event_membership）
  - 本地生成 digest_cache.json（new_signals 已过滤 depth=0）
  - scp 同时上传 dump + json 到远程
  - SSH 远程 pg_restore + 原子 mv json
"""
import asyncio
import os
import shlex
import subprocess
import time
from typing import Optional

from src.custom_logging import get_logger

logger = get_logger(__name__)

REMOTE_USER = os.environ.get("NEWSPILOT_REMOTE_USER", "root")
REMOTE_IP = os.environ.get("NEWSPILOT_REMOTE_IP", "47.239.188.192")
SYNC_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "sync_to_server.sh",
)


def push_to_remote_sync(timeout: int = 600) -> dict:
    """同步推送数据库到远程（阻塞）。返回 {"status", "elapsed_seconds", "stdout", "stderr"}。"""
    if not os.path.exists(SYNC_SCRIPT):
        return {"status": "failed", "error": f"sync script not found: {SYNC_SCRIPT}"}

    cmd = ["bash", SYNC_SCRIPT, REMOTE_USER, REMOTE_IP]
    logger.info(f"远程推送: {' '.join(shlex.quote(c) for c in cmd)}")
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - t0
        if proc.returncode == 0:
            logger.info(f"远程推送完成 ({elapsed:.1f}s)")
            return {"status": "ok", "elapsed_seconds": round(elapsed, 1), "stdout": proc.stdout}
        logger.error(f"远程推送失败 (rc={proc.returncode}): {proc.stderr[-500:] if proc.stderr else ''}")
        return {
            "status": "failed",
            "elapsed_seconds": round(elapsed, 1),
            "returncode": proc.returncode,
            "stderr": proc.stderr,
            "stdout": proc.stdout,
        }
    except subprocess.TimeoutExpired:
        logger.error(f"远程推送超时 (>{timeout}s)")
        return {"status": "failed", "error": "timeout"}
    except Exception as e:
        logger.error(f"远程推送异常: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def push_to_remote(timeout: int = 600) -> dict:
    """异步包装 push_to_remote_sync，避免阻塞事件循环"""
    return await asyncio.to_thread(push_to_remote_sync, timeout)
