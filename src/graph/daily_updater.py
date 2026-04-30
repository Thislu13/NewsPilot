"""Step 3：日描述更新 + 归属审核（三阶段：加载→并发LLM→顺序写回）"""
import asyncio
import json
import re
import time
from typing import List, Tuple
from datetime import datetime, timezone

from src.graph.client import get_shared_client
from src.graph.schema import ClusterItem
from src.storage.graph_repository import (
    load_cluster_info, load_event_texts_in_cluster,
    update_cluster_descriptions, delete_membership, check_memberships, get_membership_count,
    move_processed_to_detained,
)
from src.graph.time_utils import format_utc_date
from src.graph.config import LLM_MODEL, MAX_CONCURRENT
from config.prompts.daily_review_prompt import DAILY_UPDATE_PROMPT


class DailyUpdater:
    """Step 3：审核 checked=false 的归属记录 + 更新 recent_description"""

    def __init__(self):
        self._client = get_shared_client()
        self._rejected_event_ids: List[str] = []
        self._semaphore = asyncio.BoundedSemaphore(MAX_CONCURRENT)

    @property
    def rejected_event_ids(self) -> List[str]:
        return list(set(self._rejected_event_ids))

    async def run(self, affected_cluster_ids: List[str]):
        """
        三阶段处理：
        1. 顺序加载簇数据（快速 DB 查询，用裁剪查询不加载 embedding）
        2. 并发 LLM 审核
        3. 顺序写回结果
        """
        t0 = time.time()

        work_items: List[Tuple[ClusterItem, List[Tuple]]] = []
        for cluster_id in affected_cluster_ids:
            cluster = load_cluster_info(cluster_id)
            if not cluster:
                continue
            event_texts = load_event_texts_in_cluster(cluster_id, unchecked_only=True)
            if not event_texts:
                continue
            work_items.append((cluster, event_texts))

        print(f"  Step 3: {len(work_items)} 个簇需审核 (加载耗时 {time.time()-t0:.1f}s)")

        if not work_items:
            return

        async def _safe_review(cluster, texts):
            async with self._semaphore:
                try:
                    return await asyncio.wait_for(
                        self.review_cluster(cluster, texts),
                        timeout=90.0,
                    )
                except (asyncio.TimeoutError, Exception):
                    return None

        tasks = [_safe_review(c, t) for c, t in work_items]
        results = await asyncio.gather(*tasks)

        for (cluster, event_texts), result in zip(work_items, results):
            event_ids = [t[0] for t in event_texts]

            if result is None:
                for eid in event_ids:
                    delete_membership(eid, cluster.cluster_id)
                    self._rejected_event_ids.append(eid)
                print(f"  [SKIP] LLM 审核失败 {cluster.cluster_id[:8]}... {len(event_ids)} 事件回退到 detained")
                continue

            update_cluster_descriptions(
                cluster.cluster_id,
                recent_description=result["recent_description"],
            )

            rejected_ids = set(result["rejected_event_ids"])
            accepted_ids = [eid for eid in event_ids if eid not in rejected_ids]

            if accepted_ids:
                check_memberships(accepted_ids, cluster.cluster_id)

            for eid in rejected_ids:
                delete_membership(eid, cluster.cluster_id)
                self._rejected_event_ids.append(eid)

        elapsed = time.time() - t0
        print(f"  Step 3 完成: {len(work_items)} 簇, {len(self._rejected_event_ids)} 被剔除 ({elapsed:.0f}s)")

    async def review_cluster(
        self, cluster: ClusterItem, event_texts: List[Tuple]
    ) -> dict | None:
        """公开接口：LLM 审核一组事件（供 Step 5 Phase 4 调用）。"""
        for attempt in range(3):
            result = await self._review_cluster(cluster, event_texts)
            if result is not None:
                return result
        return None

    async def _review_cluster(
        self, cluster: ClusterItem, event_texts: List[Tuple]
    ) -> dict | None:
        """LLM 审核一组事件（使用裁剪查询结果，不加载 embedding）"""
        try:
            event_lines = []
            for i, (eid, text, pub) in enumerate(event_texts):
                pub_str = format_utc_date(pub)
                event_lines.append(f"[{i}] [{pub_str}] {text}")
            events_text = "\n".join(event_lines)

            prompt = DAILY_UPDATE_PROMPT.format(
                brief_description=cluster.brief_description,
                weekly_description=cluster.weekly_description or "暂无",
                recent_description=cluster.recent_description or "暂无",
                events_text=events_text,
            )

            messages = [{"role": "system", "content": prompt}]

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
                return None

            data = self._try_fix_json(json_text)
            if data is None:
                return None

            # 验证必需字段
            if not data.get("recent_description") or not str(data.get("recent_description", "")).strip():
                print(f"[WARN] Daily review LLM response missing required field: recent_description")
                return None

            rejected = set()
            for item in data.get("rejected_events", []):
                if isinstance(item, int) and 0 <= item < len(event_texts):
                    rejected.add(event_texts[item][0])
                elif isinstance(item, str):
                    rejected.add(item)

            return {
                "recent_description": data.get("recent_description", ""),
                "rejected_event_ids": list(rejected),
            }
        except Exception as e:
            print(f"[ERROR] Daily review failed for {cluster.cluster_id[:8]}: {e}")
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
        """尝试解析 JSON，失败时尝试修复常见问题"""
        import re as _re
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
            fixed2 = _re.sub(r',\s*([}\]])', r'\1', json_text)
            return json.loads(fixed2)
        except json.JSONDecodeError:
            pass
        return None
