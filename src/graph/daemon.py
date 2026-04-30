"""建图守护进程 — 定点建图 + 周日定期描述更新"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from src.storage.graph_repository import load_pending_events, delete_expired_detained
from src.storage.remote_sync import push_to_remote
from src.graph.ingest import ingest_events
from src.graph.periodic_updater import PeriodicUpdater
from src.graph.config import DETAINED_EXPIRE_DAYS
from config.settings import GRAPH_DAEMON_CONFIG

logger = logging.getLogger("graph_daemon")


class GraphDaemon:
    def __init__(self, config: dict = None):
        cfg = config or GRAPH_DAEMON_CONFIG
        self.ingest_hours: list = cfg.get("ingest_hours", [0, 6, 12, 18])
        self.periodic_update_weekday: int = cfg.get("periodic_update_weekday", 6)
        self.periodic_update_hour: int = cfg.get("periodic_update_hour", 22)
        self._running = False

    async def run_once(self) -> dict:
        """执行一次建图流程"""
        expired = delete_expired_detained(DETAINED_EXPIRE_DAYS)
        if expired:
            logger.info(f"清理 {expired} 条超期 detained 事件 (>{DETAINED_EXPIRE_DAYS}天)")

        pending = load_pending_events()

        if not pending:
            logger.info("无 pending 事件，跳过")
            return {"status": "skipped", "pending": 0}

        logger.info(f"开始建图: {len(pending)} 个 pending 事件")
        result = await ingest_events(pending)

        # 入库完成后推送到远程
        try:
            push_result = await push_to_remote()
            result["remote_push"] = push_result
            if push_result.get("status") != "ok":
                logger.warning(f"远程推送未成功: {push_result}")
        except Exception as e:
            logger.error(f"远程推送异常（不影响建图流程）: {e}", exc_info=True)
            result["remote_push"] = {"status": "failed", "error": str(e)}

        return result

    async def run_periodic_update(self) -> dict:
        """执行周日定期描述更新"""
        logger.info("开始周日定期描述更新（大更新），暂停新事件入库")
        updater = PeriodicUpdater()
        try:
            result = await updater.run(force=False)
            logger.info(f"定期描述更新完成: {result}")

            # 描述更新后推送到远程
            try:
                push_result = await push_to_remote()
                result["remote_push"] = push_result
                if push_result.get("status") != "ok":
                    logger.warning(f"远程推送未成功: {push_result}")
            except Exception as e:
                logger.error(f"远程推送异常（不影响主流程）: {e}", exc_info=True)
                result["remote_push"] = {"status": "failed", "error": str(e)}

            return result
        except Exception as e:
            logger.error(f"定期描述更新异常: {e}", exc_info=True)
            return {"status": "failed", "error": str(e)}

    async def run(self):
        """主循环：定点建图 + 周日定期更新"""
        self._running = True
        logger.info(
            f"建图守护进程启动 (建图时间 UTC {self.ingest_hours}, "
            f"定期更新: 周{self.periodic_update_weekday} {self.periodic_update_hour}:00 UTC)"
        )

        while self._running:
            try:
                now = datetime.now(timezone.utc)
                next_task, next_dt = self._next_task(now)

                wait_seconds = (next_dt - now).total_seconds()
                if wait_seconds > 0:
                    logger.info(f"下次任务: {next_task} @ {next_dt.strftime('%Y-%m-%d %H:%M UTC')} ({wait_seconds/3600:.1f}h 后)")
                    await asyncio.sleep(wait_seconds)

                if not self._running:
                    break

                if next_task == "periodic_update":
                    await self.run_periodic_update()
                else:
                    await self.run_once()

            except Exception as e:
                logger.error(f"建图流程异常: {e}", exc_info=True)
                await asyncio.sleep(60)

    def _next_task(self, now: datetime) -> tuple:
        """计算下一个任务类型和时间: (task_name, datetime)

        优先级：如果当前是周日定期更新时间窗口，优先执行定期更新；
        否则找最近的建图时间点。
        """
        # 查找下一个建图时间
        next_ingest = self._next_ingest_time(now)

        # 查找下一个定期更新时间
        next_periodic = self._next_periodic_time(now)

        if next_periodic <= next_ingest:
            return "periodic_update", next_periodic
        else:
            return "ingest", next_ingest

    def _next_ingest_time(self, now: datetime) -> datetime:
        """查找从 now 起最近的建图时间点（UTC 0/6/12/18 点）"""
        today = now.date()
        for hour in self.ingest_hours:
            candidate = datetime(today.year, today.month, today.day, hour, 0, 0, tzinfo=timezone.utc)
            if candidate > now:
                return candidate
        # 今天已过完，取明天第一个
        tomorrow = today + timedelta(days=1)
        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, self.ingest_hours[0], 0, 0, 0, tzinfo=timezone.utc)

    def _next_periodic_time(self, now: datetime) -> datetime:
        """查找从 now 起最近的定期更新时间（每周日 22:00 UTC）"""
        # 计算到下一个目标星期几的天数
        days_ahead = (self.periodic_update_weekday - now.weekday()) % 7

        # 如果今天就是目标星期几，但时间已经过了，则设置为下周
        if days_ahead == 0 and now.hour >= self.periodic_update_hour:
            days_ahead = 7

        candidate = datetime(
            now.year, now.month, now.day,
            self.periodic_update_hour, 0, 0, tzinfo=timezone.utc
        ) + timedelta(days=days_ahead)

        return candidate

    def stop(self):
        self._running = False
        logger.info("建图守护进程停止")
