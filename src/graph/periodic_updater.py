"""Step 6：周期描述更新（周描述 + 整体描述，自底向上）"""
import asyncio
import json
import re
import time
from typing import List, Optional
from datetime import datetime, timezone

from src.graph.client import get_shared_client
from src.graph.schema import ClusterItem
from src.storage.graph_repository import (
    load_clusters_by_depth, get_max_depth,
    get_cluster_update_info, load_recent_event_texts,
    update_cluster_descriptions, update_cluster_dirty,
)
from src.graph.time_utils import format_utc_date, utc_now
from src.graph.config import LLM_MODEL, MAX_CONCURRENT
from config.prompts.periodic_update_prompt import PERIODIC_UPDATE_PROMPT


class PeriodicUpdater:
    """Step 6：周描述 + 整体描述同步更新，自底向上遍历"""

    def __init__(self):
        self._client = get_shared_client()
        self._semaphore = asyncio.BoundedSemaphore(MAX_CONCURRENT)

    async def run(self, force: bool = False) -> dict:
        """执行周期描述更新。force=True 时更新所有簇。返回计时统计。"""
        max_depth = get_max_depth()
        t0 = time.time()
        total_updated = 0
        total_failed = 0
        total_llm_calls = 0
        total_llm_time = 0.0
        total_db_load_time = 0.0
        total_db_write_time = 0.0

        for depth in range(max_depth, -1, -1):
            t_load = time.time()
            clusters = load_clusters_by_depth(depth)
            if not clusters:
                continue

            work_items = []
            for cluster in clusters:
                since = cluster.description_updated_at
                info = get_cluster_update_info(cluster.cluster_id, since=since)
                if not force and not info["needs_update"]:
                    continue
                work_items.append((cluster, info, since))

            db_load_time = time.time() - t_load
            total_db_load_time += db_load_time

            if not work_items:
                continue

            print(f"  Depth {depth}: {len(work_items)}/{len(clusters)} 需更新 (加载 {db_load_time:.1f}s)")

            t_llm = time.time()
            tasks = [self._safe_update(c, i, s) for c, i, s in work_items]
            results = await asyncio.gather(*tasks)
            llm_time = time.time() - t_llm
            total_llm_time += llm_time
            total_llm_calls += len(tasks) * 3

            t_write = time.time()
            depth_updated = 0
            depth_failed = 0
            for (cluster, info, _since), result in zip(work_items, results):
                if result is None:
                    failure_note = self._build_failure_note()
                    update_cluster_descriptions(
                        cluster.cluster_id,
                        weekly_description=self._append_failure_note(cluster.weekly_description, failure_note),
                        detailed_description=self._append_failure_note(cluster.detailed_description, failure_note),
                    )
                    depth_failed += 1
                    total_failed += 1
                    continue

                update_cluster_descriptions(
                    cluster.cluster_id,
                    weekly_description=result["weekly_description"],
                    detailed_description=result["detailed_description"],
                    dirty=True,
                    description_updated_at=result["description_updated_at"],
                )

                for child_id in cluster.child_cluster_ids:
                    update_cluster_dirty(child_id, False)

                depth_updated += 1
                total_updated += 1

            db_write_time = time.time() - t_write
            total_db_write_time += db_write_time

            elapsed = time.time() - t0
            print(f"  Depth {depth} done: success={depth_updated}, failed={depth_failed}, LLM={llm_time:.1f}s, write={db_write_time:.1f}s ({elapsed:.0f}s)")

        elapsed = time.time() - t0
        print(f"  Step 6 完成: {total_updated} 簇更新, {total_failed} 失败备注 ({elapsed:.0f}s)")
        print(f"    DB加载={total_db_load_time:.1f}s, LLM={total_llm_calls}次/{total_llm_time:.1f}s, DB写入={total_db_write_time:.1f}s")

        return {
            "total_updated": total_updated,
            "total_failed": total_failed,
            "total_llm_calls": total_llm_calls,
            "total_llm_time": round(total_llm_time, 1),
            "total_db_load_time": round(total_db_load_time, 1),
            "total_db_write_time": round(total_db_write_time, 1),
            "elapsed_seconds": round(elapsed),
        }

    async def _safe_update(self, cluster: ClusterItem, info: dict, since: Optional[datetime]) -> Optional[dict]:
        async with self._semaphore:
            try:
                return await asyncio.wait_for(
                    self._update_cluster(cluster, info, since),
                    timeout=90.0,
                )
            except (asyncio.TimeoutError, Exception) as e:
                print(f"[ERROR] Periodic update failed for {cluster.cluster_id[:8]}: {e}")
                return None

    async def _update_cluster(self, cluster: ClusterItem, info: dict, since: Optional[datetime]) -> Optional[dict]:
        """LLM 更新单个簇的描述（Qwen 最多 3 次）"""
        recent_events = load_recent_event_texts(cluster.cluster_id, since=since)
        recent_lines = []
        latest_published_at = since
        for _eid, text, pub in recent_events:
            if pub and (latest_published_at is None or pub > latest_published_at):
                latest_published_at = pub
            pub_str = format_utc_date(pub)
            recent_lines.append(f"[{pub_str}] {text}")
        recent_events_text = "\n".join(recent_lines) if recent_lines else "暂无"

        child_section = ""
        for child in info["dirty_children"]:
            child_section += f"\n- 子簇「{child['brief_description']}」周描述：{child['weekly_description'] or '暂无'}"

        if not child_section:
            child_section = "\n（无子簇更新）"

        prompt = PERIODIC_UPDATE_PROMPT.format(
            brief_description=cluster.brief_description,
            weekly_description=cluster.weekly_description or "暂无",
            detailed_description=cluster.detailed_description or "暂无",
            recent_events=recent_events_text,
            child_clusters_section=child_section,
        )
        messages = [{"role": "system", "content": prompt}]

        for attempt in range(3):
            try:
                response = await self._client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=messages,
                    temperature=0.1,
                    timeout=25.0,
                    response_format={"type": "json_object"},
                    extra_body={"enable_thinking": False},
                )
                content = (response.choices[0].message.content or "").strip()
                json_text = self._extract_json(content)
                if not json_text:
                    continue

                data = self._try_fix_json(json_text)
                if data is None:
                    continue

                # 验证必需字段
                required_fields = ["weekly_description", "detailed_description"]
                for field in required_fields:
                    if not data.get(field) or not str(data.get(field, "")).strip():
                        print(f"[WARN] Periodic update LLM response missing required field: {field}")
                        data = None
                        break
                if data is None:
                    continue

                return {
                    "weekly_description": data.get("weekly_description", ""),
                    "detailed_description": data.get("detailed_description", ""),
                    "description_updated_at": latest_published_at or utc_now(),
                }
            except Exception as e:
                if attempt == 2:
                    print(f"[ERROR] Periodic update failed for {cluster.cluster_id[:8]} after 3 attempts: {e}")
        return None

    @staticmethod
    def _extract_json(text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        match = re.search(r"\{[\s\S]*\}", text)
        return match.group(0) if match else ""

    @staticmethod
    def _try_fix_json(json_text: str):
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass
        fixed = json_text.replace("：", ":").replace("，", ",").replace('“', '"').replace('”', '"')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        try:
            fixed2 = re.sub(r',\s*([}\]])', r'\1', json_text)
            return json.loads(fixed2)
        except json.JSONDecodeError:
            pass
        return None

    @staticmethod
    def _build_failure_note() -> str:
        now = datetime.now(timezone.utc)
        return f"[系统备注] {now.strftime('%Y-%m-%d')} 描述更新失败，待下次重试。"

    @classmethod
    def _append_failure_note(cls, text: Optional[str], failure_note: str) -> str:
        base = (text or "").strip()
        base = re.sub(r"\n\n\[系统备注\] \d{4}-\d{2}-\d{2} 描述更新失败，待下次重试。$", "", base)
        return f"{base}\n\n{failure_note}" if base else failure_note
