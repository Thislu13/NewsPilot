"""核心聚类方法 (2.1)：全局 UMAP + HDBSCAN + 并发 LLM 分析

三种运行模式：
  冷启动：UMAP.fit + 持久化
  增量聚类：UMAP.transform
  簇分裂：UMAP.fit(2D)
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import List, Optional

import joblib
import numpy as np
from hdbscan import HDBSCAN

from src.graph.schema import EventItem, ClusterGroup, ClusterResult
from src.graph.client import get_shared_client
from src.graph.time_utils import UTC_MIN, format_utc_date
from src.graph.config import (
    UMAP_GLOBAL_N_NEIGHBORS, UMAP_GLOBAL_MIN_DIST, UMAP_GLOBAL_METRIC, UMAP_GLOBAL_N_COMPONENTS,
    UMAP_SPLIT_N_NEIGHBORS, UMAP_SPLIT_N_COMPONENTS,
    HDBSCAN_MIN_CLUSTER_SIZE, HDBSCAN_MIN_SAMPLES, HDBSCAN_METRIC,
    HDBSCAN_SPLIT_MIN_CLUSTER_SIZE, HDBSCAN_SPLIT_MIN_SAMPLES,
    MIN_CLUSTER_SIZE, MAX_CONCURRENT, LLM_MODEL,
    LLM_SAMPLE_THRESHOLD, LLM_SAMPLE_SIZE,
    MODEL_DIR, UMAP_MODEL_FILE,
)
from config.prompts.cluster_analysis_prompt import CLUSTER_ANALYSIS_PROMPT


def _model_path(filename: str) -> str:
    return os.path.join(MODEL_DIR, filename)


class EventClusterer:
    """核心聚类方法 2.1（v3：768D 直连 UMAP）"""

    def __init__(self):
        self._client = get_shared_client()
        self._semaphore = asyncio.BoundedSemaphore(MAX_CONCURRENT)
        self._umap_global = None  # umap.UMAP 实例
        self._models_loaded = False

    def ensure_models(self) -> bool:
        """加载已有模型。返回 True 表示加载成功，False 表示需要冷启动 fit。"""
        umap_path = _model_path(UMAP_MODEL_FILE)

        if os.path.exists(umap_path):
            self._umap_global = joblib.load(umap_path)
            self._models_loaded = True
            print(f"  模型加载: UMAP({umap_path})")
            return True

        print("  未找到持久化模型，需要冷启动 fit")
        return False

    def fit_and_save_models(self, embeddings: np.ndarray):
        """用全量 embedding 数据 fit UMAP，并持久化。"""
        import umap

        os.makedirs(MODEL_DIR, exist_ok=True)

        # L2 归一化
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        embeddings_normed = embeddings / norms

        # UMAP fit: 768D -> 30D
        n_neighbors = min(UMAP_GLOBAL_N_NEIGHBORS, len(embeddings_normed) - 1)
        print(f"  UMAP.fit: {embeddings_normed.shape[1]}D -> {UMAP_GLOBAL_N_COMPONENTS}D (nn={n_neighbors})...")
        self._umap_global = umap.UMAP(
            n_components=UMAP_GLOBAL_N_COMPONENTS,
            n_neighbors=n_neighbors,
            min_dist=UMAP_GLOBAL_MIN_DIST,
            metric=UMAP_GLOBAL_METRIC,
        )
        self._umap_global.fit(embeddings_normed)
        joblib.dump(self._umap_global, _model_path(UMAP_MODEL_FILE))
        print(f"  UMAP 已保存: {_model_path(UMAP_MODEL_FILE)}")

        self._models_loaded = True

    @property
    def models_ready(self) -> bool:
        return self._models_loaded

    def _apply_global_umap(self, embeddings_normed: np.ndarray) -> np.ndarray:
        """UMAP transform: 768D -> 30D（增量模式）"""
        return self._umap_global.transform(embeddings_normed)

    def _fit_split_umap(self, embeddings_normed: np.ndarray) -> np.ndarray:
        """UMAP fit_transform: 768D -> 2D（分裂模式，局部 re-fit）"""
        import umap

        n_neighbors = min(UMAP_SPLIT_N_NEIGHBORS, len(embeddings_normed) - 1)
        reducer = umap.UMAP(
            n_components=UMAP_SPLIT_N_COMPONENTS,
            n_neighbors=n_neighbors,
            min_dist=0.0,
            metric="cosine",
        )
        return reducer.fit_transform(embeddings_normed)

    async def cluster(self, events: List[EventItem], splitting: bool = False, clear_event_embeddings: bool = True) -> ClusterResult:
        """
        UMAP + HDBSCAN 聚类（不含 LLM）。
        返回候选组（含事件 embedding 均值质心），供后续合并和 LLM 分析。

        splitting=True 时：UMAP.fit(2D) + HDBSCAN(激进参数)
        splitting=False 时：UMAP.transform(30D) + HDBSCAN(标准参数)
        """
        min_cluster = HDBSCAN_SPLIT_MIN_CLUSTER_SIZE if splitting else MIN_CLUSTER_SIZE

        if len(events) < min_cluster:
            return ClusterResult(groups=[], outlier_events=events)

        valid_events = [e for e in events if e.embedding is not None]
        no_embed_events = [e for e in events if e.embedding is None]

        if len(valid_events) < min_cluster:
            return ClusterResult(groups=[], outlier_events=events)

        embeddings = np.array(
            [e.embedding for e in valid_events],
            dtype=np.float32,
        )

        # L2 归一化
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        embeddings_normed = embeddings / norms

        # UMAP (增量->transform 30D / 分裂->fit 2D)
        if splitting:
            print(f"  UMAP(分裂): 768D -> {UMAP_SPLIT_N_COMPONENTS}D ({len(valid_events)} events)")
            try:
                embeddings_for_hdbscan = self._fit_split_umap(embeddings_normed)
            except Exception as e:
                print(f"[ERROR] UMAP split failed: {e}, falling back to raw embeddings")
                embeddings_for_hdbscan = embeddings_normed
        else:
            print(f"  UMAP(增量): 768D -> {UMAP_GLOBAL_N_COMPONENTS}D ({len(valid_events)} events)")
            try:
                embeddings_for_hdbscan = self._apply_global_umap(embeddings_normed)
            except Exception as e:
                print(f"[ERROR] UMAP transform failed: {e}, falling back to raw embeddings")
                embeddings_for_hdbscan = embeddings_normed

        # HDBSCAN
        if splitting:
            hdb_min_cs = HDBSCAN_SPLIT_MIN_CLUSTER_SIZE
            hdb_min_s = HDBSCAN_SPLIT_MIN_SAMPLES
        else:
            hdb_min_cs = HDBSCAN_MIN_CLUSTER_SIZE
            hdb_min_s = HDBSCAN_MIN_SAMPLES

        clusterer = HDBSCAN(
            min_cluster_size=hdb_min_cs,
            min_samples=hdb_min_s,
            metric=HDBSCAN_METRIC,
        )
        labels = clusterer.fit_predict(embeddings_for_hdbscan)

        event_by_label: dict = {}
        embedding_by_label: dict = {}  # label -> embedding matrix
        for idx, label in enumerate(labels):
            if label == -1:
                continue
            if label not in event_by_label:
                event_by_label[label] = []
                embedding_by_label[label] = []
            event_by_label[label].append(valid_events[idx])
            embedding_by_label[label].append(embeddings[idx])

        valid_groups = {k: v for k, v in event_by_label.items() if len(v) >= min_cluster}

        if not valid_groups:
            if clear_event_embeddings:
                for e in valid_events:
                    e.embedding = None
            return ClusterResult(groups=[], outlier_events=events)

        # 计算每组的事件 embedding 均值（在清空前）
        group_centroids = {}
        for label in valid_groups:
            embs = np.array(embedding_by_label[label], dtype=np.float32)
            group_centroids[label] = (embs.mean(axis=0) / np.linalg.norm(embs.mean(axis=0))).tolist()

        # UMAP 降维完成，按需释放原始 768D embedding 节省内存
        embeddings_normed = None
        embeddings = None
        embedding_by_label = None
        if clear_event_embeddings:
            for e in valid_events:
                e.embedding = None

        small_group_events = [e for k, v in event_by_label.items() if k not in valid_groups for e in v]
        noise_events = [valid_events[i] for i, label in enumerate(labels) if label == -1]
        noise_events.extend(no_embed_events)

        # 构建候选组（含质心，不含 LLM 结果）
        print(f"  HDBSCAN 产出 {len(valid_groups)} 个候选簇")

        groups: List[ClusterGroup] = []
        for label, ge in valid_groups.items():
            group = ClusterGroup(
                events=ge,
                centroid=group_centroids.get(label),
            )
            groups.append(group)

        # 未聚类事件
        all_outlier: List[EventItem] = []
        seen_ids: set = set()
        for e in noise_events:
            if e.event_id not in seen_ids:
                all_outlier.append(e)
                seen_ids.add(e.event_id)
        for e in small_group_events:
            if e.event_id not in seen_ids:
                all_outlier.append(e)
                seen_ids.add(e.event_id)

        return ClusterResult(groups=groups, outlier_events=all_outlier)

    async def analyze_group(self, events: List[EventItem], max_retries: int = 2) -> Optional[dict]:
        """公开接口：LLM 分析一组事件，供 Step 5 Phase 3 调用。"""
        return await self._analyze_group(events, max_retries)

    async def _analyze_group(self, events: List[EventItem], max_retries: int = 3) -> Optional[dict]:
        """LLM 分析一组事件（信号量控制并发，大组等距采样，失败自动重试）
        LLM 彻底失败时返回 None，调用方应跳过该组不建簇，事件留在 detained 下次重试。
        """
        async with self._semaphore:
            for attempt in range(1 + max_retries):
                try:
                    result = await self._call_llm(events)
                    if result is not None:
                        return result
                except Exception as e:
                    if attempt < max_retries:
                        print(f"[WARN] Cluster analysis attempt {attempt+1} failed: {e}, retrying...")
                    else:
                        print(f"[ERROR] Cluster analysis failed after {1+max_retries} attempts: {e}")
            # 不建簇，事件留在 detained，下次入库自动重试
            print(f"  [SKIP] LLM 彻底失败，{len(events)} 个事件留在 detained 待下次重试")
            return None

    async def _call_llm(self, events: List[EventItem]) -> Optional[dict]:
        """单次 LLM 调用"""
        sampled = events
        is_sampled = False

        # 大组等距采样
        if len(events) > LLM_SAMPLE_THRESHOLD:
            sorted_events = sorted(events, key=lambda e: e.published_at or UTC_MIN)
            step = len(sorted_events) / LLM_SAMPLE_SIZE
            sampled = [sorted_events[int(i * step)] for i in range(LLM_SAMPLE_SIZE)]
            is_sampled = True

        event_lines = []
        for i, e in enumerate(sampled):
            pub = format_utc_date(e.published_at)
            event_lines.append(f"[{i}] [{pub}] {e.event_text}")
        events_text = "\n".join(event_lines)

        if is_sampled:
            events_text = f"（共 {len(events)} 个事件，以下为等距采样 {len(sampled)} 条）\n{events_text}"

        messages = [
            {"role": "system", "content": CLUSTER_ANALYSIS_PROMPT},
            {"role": "user", "content": f"事件列表：\n{events_text}"},
        ]

        response = await self._client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.1,
            timeout=120.0,
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
        required_fields = ["brief_description", "detailed_description", "weekly_description", "recent_description"]
        for field in required_fields:
            if not data.get(field) or not str(data.get(field, "")).strip():
                print(f"[WARN] LLM response missing required field: {field}")
                return None

        # outlier 只在未采样时执行
        outlier_ids = set()
        if not is_sampled:
            for item in data.get("outlier_events", []):
                if isinstance(item, int) and 0 <= item < len(events):
                    outlier_ids.add(events[item].event_id)
                elif isinstance(item, str):
                    outlier_ids.add(item)

        return {
            "brief_description": data.get("brief_description", ""),
            "detailed_description": data.get("detailed_description", ""),
            "weekly_description": data.get("weekly_description", ""),
            "recent_description": data.get("recent_description", ""),
            "outlier_event_ids": list(outlier_ids),
        }

    @staticmethod
    def _extract_json(text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        # 去除 markdown 代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        match = re.search(r"\{[\s\S]*\}", text)
        return match.group(0) if match else ""

    @staticmethod
    def _try_fix_json(json_text: str) -> Optional[dict]:
        """尝试解析 JSON，失败时尝试修复常见问题"""
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
    def _make_fallback_description(events: List[EventItem]) -> dict:
        """LLM 失败时的简单 fallback：取前几条事件文本拼接"""
        texts = [e.event_text[:50] for e in events[:5] if e.event_text]
        brief = "；".join(texts[:3]) if texts else "未知事件簇"
        return {
            "brief_description": brief,
            "detailed_description": "",
            "weekly_description": "暂无近期发展",
            "recent_description": "",
            "outlier_event_ids": [],
        }
