"""Step 2：FAISS 事件匹配簇"""
import json
from typing import List, Tuple, Dict, Set

import numpy as np
import faiss

from src.graph.schema import EventItem, ClusterItem
from src.storage.graph_repository import load_cluster_centroids, load_all_clusters
from src.graph.config import MATCH_THRESHOLD, MAX_MEMBERSHIPS


# ============================================================
# 父子簇去重 (1.12)
# ============================================================

def build_parent_map(clusters: List[ClusterItem]) -> Dict[str, Set[str]]:
    """构建 cluster_id → 所有祖先id 的映射"""
    cluster_by_id = {c.cluster_id: c for c in clusters}
    parent_map: Dict[str, Set[str]] = {}

    def _get_ancestors(cid: str) -> Set[str]:
        if cid in parent_map:
            return parent_map[cid]
        ancestors = set()
        cluster = cluster_by_id.get(cid)
        if cluster and cluster.parent_cluster_id:
            ancestors.add(cluster.parent_cluster_id)
            ancestors.update(_get_ancestors(cluster.parent_cluster_id))
        parent_map[cid] = ancestors
        return ancestors

    for c in clusters:
        _get_ancestors(c.cluster_id)

    return parent_map


def dedup_keep_deepest(
    candidate_ids: List[str],
    parent_map: Dict[str, Set[str]],
) -> List[str]:
    """父子簇去重：候选列表中存在父子依赖关系时，去掉有后代在列表中的簇，只保留最深的。"""
    result = []
    for cid in candidate_ids:
        has_descendant = False
        for other_id in candidate_ids:
            if other_id == cid:
                continue
            if cid in parent_map.get(other_id, set()):
                has_descendant = True
                break
        if not has_descendant:
            result.append(cid)
    return result


# ============================================================
# Step 2：事件匹配簇
# ============================================================

class ClusterMatcher:
    """FAISS 加速的簇匹配"""

    def __init__(self):
        self._index: faiss.IndexFlatIP = None
        self._cluster_ids: List[str] = []
        self._clusters: List[ClusterItem] = []
        self._parent_map: Dict[str, Set[str]] = {}

    def build_index(self):
        """构建 FAISS 索引"""
        ids, centroids = load_cluster_centroids()
        if not ids:
            self._index = None
            return

        self._cluster_ids = ids
        self._clusters = load_all_clusters()
        self._parent_map = build_parent_map(self._clusters)

        vectors = np.array(centroids, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vectors = vectors / norms

        dim = vectors.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(vectors)

    @property
    def has_clusters(self) -> bool:
        return self._index is not None and self._index.ntotal > 0

    def match_event(self, event: EventItem) -> List[Tuple[str, float]]:
        """匹配单个事件到已有簇。返回 [(cluster_id, sim_score), ...]，已去重和 top5。"""
        if not self.has_clusters or not event.embedding:
            return []

        vec = np.array([event.embedding], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm == 0:
            return []
        vec = vec / norm

        k = self._index.ntotal
        scores, indices = self._index.search(vec, k)

        candidates = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            if score >= MATCH_THRESHOLD:
                candidates.append((self._cluster_ids[idx], float(score)))

        if not candidates:
            return []

        candidates.sort(key=lambda x: x[1], reverse=True)

        candidate_ids = [c[0] for c in candidates]
        kept_ids = dedup_keep_deepest(candidate_ids, self._parent_map)
        kept_set = set(kept_ids)

        result = [(cid, score) for cid, score in candidates if cid in kept_set]
        return result[:MAX_MEMBERSHIPS]
