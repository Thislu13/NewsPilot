"""ingest_events() — 事件入库主流程（v4, SQLAlchemy 版）

流程：Step 2 → Step 3 → Step 4 → Step 5(聚类+批次内去重) → Step 6(跨批合并+LLM审核) → Step 8(分裂)"""
import asyncio
import uuid
import time
from datetime import datetime, timezone
from typing import List, Set, Dict, Tuple

from src.graph.schema import EventItem, ClusterItem, MembershipItem, ClusterGroup
from src.graph.clusterer import EventClusterer
from src.graph.matcher import ClusterMatcher
from src.graph.daily_updater import DailyUpdater
from src.storage.graph_repository import (
    load_detained_events, load_events_in_cluster, get_all_clusters_with_count,
    load_cluster_centroids, load_cluster_info,
    batch_move_to_processed, move_to_detained, move_processed_to_detained,
    write_clusters, write_memberships, update_cluster_children,
    batch_delete_memberships,
    delete_membership,
    get_membership_count, check_memberships,
    count_processed, count_detained, count_clusters,
    update_cluster_splittable, mark_clusters_splittable,
    update_cluster_descriptions,
)
from src.graph.embedder import generate_embedding
from src.graph.client import close_shared_client
from src.graph.config import SPLIT_THRESHOLD, MERGE_THRESHOLD_INNER, MERGE_THRESHOLD_CROSS
import numpy as np


async def ingest_events(events: List[EventItem]) -> dict:
    """入口函数：接收事件列表，执行完整入库流程。"""
    t0 = time.time()
    timings = {}
    print("=" * 60)
    print(f"ingest_events: {len(events)} 个事件")
    print("=" * 60)

    try:
        clusterer = EventClusterer()
        matcher = ClusterMatcher()
        daily_updater = DailyUpdater()

        # ==== 加载 UMAP 模型 ====
        models_loaded = clusterer.ensure_models()

        # ==== Step 2：逐事件匹配簇 ====
        print("\n[Step 2] 事件匹配簇...")
        t2 = time.time()
        matcher.build_index()
        build_index_time = time.time() - t2
        if not matcher.has_clusters:
            print("  冷启动：无已有簇，所有事件将进入 detained")

        match_t0 = time.time()
        matched_events = []
        detained_ids = []
        all_memberships = []
        affected_clusters: Set[str] = set()

        for event in events:
            matches = matcher.match_event(event)
            if matches:
                for cluster_id, sim_score in matches:
                    all_memberships.append(MembershipItem(
                        event_id=event.event_id,
                        cluster_id=cluster_id,
                        sim_score=sim_score,
                        checked=False,
                        created_at=datetime.now(timezone.utc),
                    ))
                matched_events.append(event)
                affected_clusters.update(cid for cid, _ in matches)
            else:
                detained_ids.append(event.event_id)

        match_elapsed = time.time() - match_t0

        # 批量写入
        t_write = time.time()
        if all_memberships:
            write_memberships(all_memberships)
        if matched_events:
            batch_move_to_processed(matched_events)
            mark_clusters_splittable(list(affected_clusters))
        if detained_ids:
            move_to_detained(detained_ids)
        write_elapsed = time.time() - t_write

        timings["step2_build_index"] = round(build_index_time, 2)
        timings["step2_match"] = round(match_elapsed, 2)
        timings["step2_write"] = round(write_elapsed, 2)
        print(f"  Step 2 完成: 匹配 {len(matched_events)}, Detained {len(detained_ids)}"
              f" (index={build_index_time:.1f}s, match={match_elapsed:.1f}s, write={write_elapsed:.1f}s)")

        # ==== Step 3：日描述更新 + 归属审核 ====
        if affected_clusters:
            print(f"\n[Step 3] 审核归属 ({len(affected_clusters)} 个簇)...")
            t3 = time.time()
            await daily_updater.run(list(affected_clusters))
            timings["step3"] = round(time.time() - t3, 2)
        else:
            print("\n[Step 3] 无需审核")
            timings["step3"] = 0

        # ==== Step 4：处理被剔除事件 ====
        t4 = time.time()
        rejected_ids = daily_updater.rejected_event_ids
        if rejected_ids:
            print(f"\n[Step 4] 处理被剔除事件 ({len(rejected_ids)})...")
            to_detain = [eid for eid in rejected_ids if get_membership_count(eid) == 0]
            if to_detain:
                move_processed_to_detained(to_detain)
                print(f"  移回 detained: {len(to_detain)}")
        else:
            print("\n[Step 4] 无被剔除事件")
        timings["step4"] = round(time.time() - t4, 2)

        # ==== Step 5：detained 事件聚类 ====
        new_cluster_ids: List[str] = []
        t5_load = time.time()
        detained_events = load_detained_events()
        detained_load_time = time.time() - t5_load

        if detained_events:
            print(f"\n[Step 5] detained 事件聚类 ({len(detained_events)})...")
            t5 = time.time()

            if not models_loaded and not clusterer.models_ready:
                print("  冷启动：用 detained 事件 fit UMAP...")
                all_embeddings = np.array(
                    [e.embedding for e in detained_events if e.embedding is not None],
                    dtype=np.float32,
                )
                if len(all_embeddings) >= 10:
                    clusterer.fit_and_save_models(all_embeddings)
                else:
                    print(f"  事件太少({len(all_embeddings)}), 跳过模型 fit")

            cluster_result = await _cluster_detained(clusterer, daily_updater, detained_events)
            new_cluster_ids = cluster_result.get("new_cluster_ids", [])
            timings["step5_load"] = round(detained_load_time, 2)
            timings["step5_cluster"] = round(time.time() - t5, 2)
            timings["step5_new_clusters"] = cluster_result.get("new_clusters", 0)
            timings["step5_clustered"] = cluster_result.get("clustered", 0)
            timings["step5_merged"] = cluster_result.get("merged_old_clusters", 0)
        else:
            print("\n[Step 5] 无 detained 事件")
            timings["step5_load"] = round(detained_load_time, 2)
            timings["step5_cluster"] = 0

        # ==== Step 8：分裂检查 ====
        # 每次入库开始时重置所有簇为可分裂，只对分裂失败（HDBSCAN无法拆分）的标记为不可分裂
        from src.storage.graph_repository import reset_all_splittable
        reset_all_splittable()
        print("\n[Step 8] 分裂检查...")
        t_val = time.time()
        await _validation_loop(clusterer)
        timings["step8_split"] = round(time.time() - t_val, 2)

        # ==== 统计 ====
        total = time.time() - t0
        result = {
            "matched": len(matched_events),
            "detained": len(detained_ids),
            "processed": count_processed(),
            "clusters": count_clusters(),
            "detained_remaining": count_detained(),
            "elapsed_seconds": round(total),
            "timings": timings,
        }
        print("\n" + "=" * 60)
        print(f"ingest_events 完成 ({total:.0f}s)")
        print(f"  匹配: {result['matched']}, Detained: {result['detained']}")
        print(f"  总 processed: {result['processed']}, 总 clusters: {result['clusters']}")
        print("=" * 60)
        return result

    finally:
        await close_shared_client()


# ============================================================
# Step 5-7：detained 事件聚类
# ============================================================

async def _cluster_detained(
    clusterer: EventClusterer, daily_updater: DailyUpdater, events: List[EventItem]
) -> dict:
    """Step 5(聚类+批次内去重) → Step 6(跨批合并+Phase 3 A类新建LLM) → Step 7(B类合并LLM审核)"""

    # --- Phase 1: Step 5 聚类 + 质心（无 LLM）---
    print(f"  [Phase 1] 聚类 {len(events)} 个事件...")
    result = await clusterer.cluster(events, clear_event_embeddings=False)

    if not result.groups:
        print("  未能生成任何候选组")
        return {"new_clusters": 0, "clustered": 0, "new_cluster_ids": [], "merged_old_clusters": 0}

    print(f"  Phase 1: {len(result.groups)} 个候选组")

    # --- Phase 2: Step 6 跨批合并（无 LLM）---
    a_groups, b_merge_map = _merge_candidates(result.groups)
    print(f"  Phase 2: {len(a_groups)} A类(待建簇), {len(b_merge_map)} B类(合并进旧簇)")

    # --- Phase 3: Step 6 A类新建簇（LLM）---
    a_ids, a_count = await _process_new_clusters(clusterer, a_groups)

    # --- Phase 4: Step 7 B类合并审核（LLM）---
    b_count = await _process_merged_clusters(daily_updater, b_merge_map)

    total = a_count + b_count
    print(f"  Step 5-7 完成: {len(a_ids)} 新建簇, {len(b_merge_map)} 旧簇接收合并, 共 {total} 事件归入")

    return {
        "new_clusters": len(a_ids),
        "clustered": total,
        "new_cluster_ids": a_ids,
        "merged_old_clusters": len(b_merge_map),
    }


def _merge_candidates(
    groups: List[ClusterGroup],
) -> Tuple[List[ClusterGroup], Dict[str, List[EventItem]]]:
    """Phase 2: 批次内去重 + 跨批次合并"""

    # --- 2a: 批次内去重 ---
    groups = _dedup_within_batch(groups)

    # --- 2b: 跨批次合并 ---
    existing_ids, existing_centroids = load_cluster_centroids()

    b_merge_map: Dict[str, List[EventItem]] = {}

    if not existing_ids:
        return groups, b_merge_map

    ex_mat = np.array(existing_centroids, dtype=np.float32)
    ex_norms = np.linalg.norm(ex_mat, axis=1, keepdims=True)
    ex_norms[ex_norms == 0] = 1
    ex_mat_norm = ex_mat / ex_norms

    a_groups: List[ClusterGroup] = []

    for group in groups:
        if group.centroid is None:
            a_groups.append(group)
            continue

        vec = np.array(group.centroid, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm == 0:
            a_groups.append(group)
            continue
        vec_norm = vec / norm

        sims = ex_mat_norm @ vec_norm
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        best_old_cid = existing_ids[best_idx]

        if best_sim >= MERGE_THRESHOLD_CROSS:
            if best_old_cid not in b_merge_map:
                b_merge_map[best_old_cid] = []
            b_merge_map[best_old_cid].extend(group.events)
            print(f"  跨批次合并: {len(group.events)} 事件 → {best_old_cid[:8]}... (sim={best_sim:.4f})")
        else:
            a_groups.append(group)

    return a_groups, b_merge_map


def _dedup_within_batch(groups: List[ClusterGroup]) -> List[ClusterGroup]:
    """Phase 2a: 批次内去重 — 质心相似度 >= 0.85 合并"""
    if len(groups) <= 1:
        return groups

    centroids = []
    for g in groups:
        if g.centroid:
            centroids.append(np.array(g.centroid, dtype=np.float32))
        else:
            centroids.append(np.zeros(768, dtype=np.float32))

    mat = np.array(centroids, dtype=np.float32)
    sim_matrix = mat @ mat.T
    np.fill_diagonal(sim_matrix, 0)

    from collections import defaultdict
    graph = defaultdict(set)
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            if sim_matrix[i, j] >= MERGE_THRESHOLD_INNER:
                graph[i].add(j)
                graph[j].add(i)

    visited = set()
    components = []
    for node in range(len(groups)):
        if node not in visited and node in graph:
            comp = set()
            stack = [node]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                comp.add(n)
                stack.extend(graph[n] - visited)
            components.append(comp)

    merged_indices = set()
    result = []

    for comp in components:
        merged_events = []
        emb_arrays = []
        for idx in comp:
            merged_events.extend(groups[idx].events)
            if groups[idx].centroid:
                emb_arrays.append(np.array(groups[idx].centroid, dtype=np.float32))

        new_centroid = None
        if emb_arrays:
            mean_vec = np.mean(emb_arrays, axis=0)
            norm = np.linalg.norm(mean_vec)
            if norm > 0:
                new_centroid = (mean_vec / norm).tolist()

        result.append(ClusterGroup(events=merged_events, centroid=new_centroid))
        merged_indices.update(comp)

    for i in range(len(groups)):
        if i not in merged_indices:
            result.append(groups[i])

    print(f"  [Phase 2a] 批次内去重: {len(groups)} → {len(result)} 组")
    return result


async def _process_new_clusters(
    clusterer: EventClusterer, groups: List[ClusterGroup]
) -> Tuple[List[str], int]:
    """Phase 3: LLM 分析 A 类组，写新建簇"""
    if not groups:
        return [], 0

    print(f"  [Phase 3] LLM 分析 {len(groups)} 个候选组...")

    tasks = [clusterer.analyze_group(g.events) for g in groups]
    results = await asyncio.gather(*tasks)

    new_cluster_ids: List[str] = []
    clustered_count = 0
    embed_times = []

    for group, llm_result in zip(groups, results):
        if llm_result is None:
            print(f"  [SKIP] LLM 失败 ({len(group.events)} 事件留在 detained)")
            continue

        outlier_set = set(llm_result["outlier_event_ids"])
        valid_events = [e for e in group.events if e.event_id not in outlier_set]
        if not valid_events:
            continue

        cluster_id = str(uuid.uuid4())

        t_emb = time.time()
        centroid = await generate_embedding(llm_result["brief_description"])
        embed_times.append(time.time() - t_emb)

        now = datetime.now(timezone.utc)
        cluster = ClusterItem(
            cluster_id=cluster_id,
            parent_cluster_id=None,
            centroid=centroid,
            depth=0,
            dirty=True,
            brief_description=llm_result["brief_description"],
            detailed_description=llm_result["detailed_description"],
            weekly_description=llm_result["weekly_description"],
            recent_description=llm_result["recent_description"],
            created_at=now,
            updated_at=now,
            description_updated_at=now,
        )
        write_clusters([cluster])

        memberships = [
            MembershipItem(
                event_id=e.event_id,
                cluster_id=cluster_id,
                sim_score=None,
                checked=True,
                created_at=datetime.now(timezone.utc),
            )
            for e in valid_events
        ]
        write_memberships(memberships)
        batch_move_to_processed(valid_events)
        clustered_count += len(valid_events)
        new_cluster_ids.append(cluster_id)

        desc = llm_result["brief_description"][:50] if llm_result["brief_description"] else ""
        print(f"  新建簇 {cluster_id[:8]}...: {len(valid_events)} 事件 - {desc}")

    if embed_times:
        avg = sum(embed_times) / len(embed_times)
        print(f"  Phase 3: {len(embed_times)} 次 embedding, 平均 {avg:.1f}s, 共 {sum(embed_times):.1f}s")

    return new_cluster_ids, clustered_count


async def _process_merged_clusters(
    daily_updater: DailyUpdater, b_merge_map: Dict[str, List[EventItem]]
) -> int:
    """Phase 4: B 类事件合并进旧簇后 LLM 审核"""
    if not b_merge_map:
        return 0

    total_reviewed = 0

    for old_cid, merged_events in b_merge_map.items():
        cluster = load_cluster_info(old_cid)
        if not cluster:
            print(f"  [WARN] 旧簇 {old_cid[:8]}... 不存在，跳过")
            continue

        batch_move_to_processed(merged_events)
        memberships = [
            MembershipItem(
                event_id=e.event_id,
                cluster_id=old_cid,
                sim_score=None,
                checked=False,
                created_at=datetime.now(timezone.utc),
            )
            for e in merged_events
        ]
        write_memberships(memberships)

        event_texts = [(e.event_id, e.event_text, e.published_at) for e in merged_events]
        review_result = await daily_updater.review_cluster(cluster, event_texts)

        if review_result is None:
            event_ids = [e.event_id for e in merged_events]
            for eid in event_ids:
                delete_membership(eid, old_cid)
            move_processed_to_detained(event_ids)
            print(f"  [SKIP] 审核失败 {old_cid[:8]}..., {len(merged_events)} 事件回退 detained")
            continue

        update_cluster_descriptions(
            old_cid,
            recent_description=review_result["recent_description"],
            updated_at=datetime.now(timezone.utc),
        )

        rejected_ids = set(review_result["rejected_event_ids"])
        accepted_ids = [e.event_id for e in merged_events if e.event_id not in rejected_ids]

        if accepted_ids:
            check_memberships(accepted_ids, old_cid)

        for eid in rejected_ids:
            delete_membership(eid, old_cid)
            if get_membership_count(eid) == 0:
                move_processed_to_detained([eid])

        mark_clusters_splittable([old_cid])
        total_reviewed += len(merged_events)

        print(f"  审核旧簇 {old_cid[:8]}...: 接受 {len(accepted_ids)}, 拒绝 {len(rejected_ids)}")

    return total_reviewed


# ============================================================
# Step 8：分裂检查
# ============================================================

async def _validation_loop(clusterer: EventClusterer, max_iterations: int = 5):
    iteration = 0

    while iteration < max_iterations:
        big = [c for c in get_all_clusters_with_count(splittable_only=True)
               if c["event_count"] >= SPLIT_THRESHOLD]
        if not big:
            break

        iteration += 1
        print(f"  第 {iteration} 轮分裂: {len(big)} 个超大簇")

        for ci in big:
            cid = ci["cluster_id"]
            n = ci["event_count"]
            d = ci["depth"]
            print(f"  分裂 {cid[:8]}... ({n} 个事件, depth={d})")
            split_ok = await _split_cluster(clusterer, cid, d)
            if not split_ok:
                update_cluster_splittable(cid, False)
                print(f"  标记 {cid[:8]}... 为不可分裂")

    if iteration == 0:
        print("  无需分裂")
    elif iteration >= max_iterations:
        remaining = [c for c in get_all_clusters_with_count(splittable_only=True)
                     if c["event_count"] >= SPLIT_THRESHOLD]
        print(f"  达到最大分裂轮数 ({max_iterations}), 仍有 {len(remaining)} 个大簇待下次处理")


async def _split_cluster(clusterer: EventClusterer, parent_id: str, parent_depth: int) -> bool:
    """分裂单个簇"""
    events = load_events_in_cluster(parent_id)
    if len(events) < SPLIT_THRESHOLD:
        return False

    result = await clusterer.cluster(events, splitting=True)
    if len(result.groups) < 2:
        return False

    tasks = [clusterer.analyze_group(g.events) for g in result.groups]
    llm_results = await asyncio.gather(*tasks)

    child_ids = []
    moved_ids: List[str] = []

    for group, llm_result in zip(result.groups, llm_results):
        if llm_result is None:
            print(f"  [SKIP] 分裂 LLM 失败 ({len(group.events)} 事件留在父簇)")
            continue

        outlier_set = set(llm_result["outlier_event_ids"])
        valid = [e for e in group.events if e.event_id not in outlier_set]
        if not valid:
            continue

        cid = str(uuid.uuid4())
        centroid = await generate_embedding(llm_result["brief_description"])

        now = datetime.now(timezone.utc)
        cluster = ClusterItem(
            cluster_id=cid,
            parent_cluster_id=parent_id,
            centroid=centroid,
            depth=parent_depth + 1,
            dirty=True,
            brief_description=llm_result["brief_description"],
            detailed_description=llm_result["detailed_description"],
            weekly_description=llm_result["weekly_description"],
            recent_description=llm_result["recent_description"],
            created_at=now,
            updated_at=now,
            description_updated_at=now,
        )
        write_clusters([cluster])
        child_ids.append(cid)

        memberships = [
            MembershipItem(
                event_id=e.event_id,
                cluster_id=cid,
                sim_score=None,
                checked=True,
                created_at=datetime.now(timezone.utc),
            )
            for e in valid
        ]
        write_memberships(memberships)
        moved_ids.extend(e.event_id for e in valid)

    if not child_ids:
        return False

    batch_delete_memberships(moved_ids, parent_id)
    update_cluster_children(parent_id, child_ids)
    update_cluster_splittable(parent_id, False)
    return True