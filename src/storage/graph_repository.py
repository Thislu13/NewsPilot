"""建图模块数据库操作层 — 基于 SQLAlchemy 原生 SQL

所有向量查询使用 session.execute(text(...)) 以保留 pgvector 原生支持。
"""
import json
import warnings
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.storage.db_config import db_manager
from src.graph.schema import EventItem, ClusterItem

warnings.filterwarnings("ignore", message=".*collation version.*")


def _get_session() -> Session:
    return db_manager.get_session()


def _ensure_utc(dt) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, str):
        from dateutil.parser import parse
        dt = parse(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# 建表 & 扩展
# ============================================================

def init_graph_extensions():
    """确保 pgvector 扩展已安装"""
    with db_manager.engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()


# ============================================================
# 行转换
# ============================================================

def _row_to_event(row) -> EventItem:
    categories = row[4]
    if isinstance(categories, str):
        categories = json.loads(categories)
    embedding = row[6]
    if isinstance(embedding, str):
        embedding = json.loads(embedding)
    return EventItem(
        event_id=row[0],
        source_news_id=row[1],
        source_channel=row[2],
        source_url=row[3],
        categories=categories,
        event_text=row[5] or "",
        embedding=embedding,
        published_at=_ensure_utc(row[7]),
        fetched_at=_ensure_utc(row[8]),
        status=row[9] if len(row) > 9 else "pending",
        created_at=_ensure_utc(row[10]) if len(row) > 10 else None,
    )


def _row_to_cluster(row) -> ClusterItem:
    centroid = row[2]
    if isinstance(centroid, str):
        centroid = json.loads(centroid)
    child_ids = row[3]
    if isinstance(child_ids, str):
        child_ids = json.loads(child_ids)
    return ClusterItem(
        cluster_id=row[0],
        parent_cluster_id=row[1],
        centroid=centroid,
        child_cluster_ids=child_ids or [],
        depth=row[4],
        dirty=row[5] if row[5] is not None else True,
        splittable=row[6] if row[6] is not None else True,
        brief_description=row[7] or "",
        detailed_description=row[8] or "",
        weekly_description=row[9] or "",
        recent_description=row[10] or "",
        status=row[11] or "active",
        created_at=_ensure_utc(row[12]),
        updated_at=_ensure_utc(row[13]),
        description_updated_at=_ensure_utc(row[14] if len(row) > 14 else row[13]),
    )


# ============================================================
# 事件加载（全字段，含 embedding）
# ============================================================

def load_pending_events() -> List[EventItem]:
    """加载所有 pending 事件（供建图守护进程使用）"""
    session = _get_session()
    try:
        result = session.execute(text("""
            SELECT event_id, source_news_id, source_channel, source_url,
                   categories, event_text, embedding, published_at, fetched_at,
                   status, created_at
            FROM candidate_events
            WHERE status = 'pending'
            ORDER BY published_at ASC;
        """))
        return [_row_to_event(row) for row in result.fetchall()]
    finally:
        session.close()


def load_detained_events() -> List[EventItem]:
    """加载所有 detained 事件（含 embedding，用于聚类）"""
    session = _get_session()
    try:
        result = session.execute(text("""
            SELECT event_id, source_news_id, source_channel, source_url,
                   categories, event_text, embedding, published_at, fetched_at,
                   status, created_at
            FROM candidate_events
            WHERE status = 'detained'
            ORDER BY published_at ASC;
        """))
        return [_row_to_event(row) for row in result.fetchall()]
    finally:
        session.close()


def load_events_in_cluster(cluster_id: str) -> List[EventItem]:
    """加载簇内所有事件（含 embedding，用于分裂）"""
    session = _get_session()
    try:
        result = session.execute(text("""
            SELECT pe.event_id, pe.source_news_id, pe.source_channel, pe.source_url,
                   pe.categories, pe.event_text, pe.embedding, pe.published_at, pe.fetched_at,
                   'processed' as status, pe.created_at
            FROM processed_events pe
            JOIN event_membership em ON pe.event_id = em.event_id
            WHERE em.cluster_id = :cluster_id;
        """), {"cluster_id": cluster_id})
        return [_row_to_event(row) for row in result.fetchall()]
    finally:
        session.close()


# ============================================================
# 事件加载（裁剪查询）
# ============================================================

def load_event_texts_in_cluster(cluster_id: str, unchecked_only: bool = True) -> List[Tuple[str, str, datetime]]:
    """加载簇内事件的 event_id, event_text, published_at"""
    session = _get_session()
    try:
        if unchecked_only:
            result = session.execute(text("""
                SELECT pe.event_id, pe.event_text, pe.published_at
                FROM processed_events pe
                JOIN event_membership em ON pe.event_id = em.event_id
                WHERE em.cluster_id = :cluster_id AND em.checked = FALSE;
            """), {"cluster_id": cluster_id})
        else:
            result = session.execute(text("""
                SELECT pe.event_id, pe.event_text, pe.published_at
                FROM processed_events pe
                JOIN event_membership em ON pe.event_id = em.event_id
                WHERE em.cluster_id = :cluster_id;
            """), {"cluster_id": cluster_id})
        return result.fetchall()
    finally:
        session.close()


def load_recent_event_texts(cluster_id: str, since: Optional[datetime] = None, days: int = 7) -> List[Tuple[str, str, datetime]]:
    """加载簇内近期事件"""
    session = _get_session()
    try:
        if since is not None:
            result = session.execute(text("""
                SELECT pe.event_id, pe.event_text, pe.published_at
                FROM processed_events pe
                JOIN event_membership em ON pe.event_id = em.event_id
                WHERE em.cluster_id = :cluster_id AND pe.published_at > :since
                ORDER BY pe.published_at ASC;
            """), {"cluster_id": cluster_id, "since": since})
        else:
            result = session.execute(text("""
                SELECT pe.event_id, pe.event_text, pe.published_at
                FROM processed_events pe
                JOIN event_membership em ON pe.event_id = em.event_id
                WHERE em.cluster_id = :cluster_id
                  AND pe.published_at >= NOW() - MAKE_INTERVAL(days => :days)
                ORDER BY pe.published_at ASC;
            """), {"cluster_id": cluster_id, "days": days})
        return result.fetchall()
    finally:
        session.close()


# ============================================================
# 事件移动（批量 + 事务）
# ============================================================

def _attr(obj, name, default=None):
    """统一访问 dataclass 或 dict"""
    if hasattr(obj, name):
        return getattr(obj, name)
    return obj.get(name, default)


def batch_move_to_processed(events: list):
    """candidate_events → processed_events"""
    if not events:
        return
    session = _get_session()
    try:
        for e in events:
            session.execute(text("""
                INSERT INTO processed_events
                (event_id, source_news_id, source_channel, source_url, categories,
                 event_text, embedding, published_at, fetched_at, created_at)
                VALUES (:event_id, :source_news_id, :source_channel, :source_url, :categories,
                        :event_text, CAST(:embedding AS vector), :published_at, :fetched_at, :created_at)
                ON CONFLICT (event_id) DO NOTHING;
            """), {
                "event_id": _attr(e, "event_id"),
                "source_news_id": _attr(e, "source_news_id"),
                "source_channel": _attr(e, "source_channel"),
                "source_url": _attr(e, "source_url"),
                "categories": json.dumps(_attr(e, "categories"), ensure_ascii=False) if _attr(e, "categories") else None,
                "event_text": _attr(e, "event_text"),
                "embedding": str(_attr(e, "embedding")) if _attr(e, "embedding") else None,
                "published_at": _ensure_utc(_attr(e, "published_at")),
                "fetched_at": _ensure_utc(_attr(e, "fetched_at")),
                "created_at": _ensure_utc(_attr(e, "created_at")) or _utc_now(),
            })

        ids = [_attr(e, "event_id") for e in events]
        session.execute(text("DELETE FROM candidate_events WHERE event_id = ANY(:ids);"), {"ids": ids})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def move_to_detained(event_ids: List[str]):
    """将事件标记为 detained"""
    if not event_ids:
        return
    session = _get_session()
    try:
        session.execute(text("""
            UPDATE candidate_events SET status = 'detained'
            WHERE event_id = ANY(:ids);
        """), {"ids": event_ids})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def move_processed_to_detained(event_ids: List[str]):
    """从 processed_events 移回 candidate_events 标记 detained"""
    if not event_ids:
        return
    session = _get_session()
    try:
        rows = session.execute(text("""
            SELECT event_id, source_news_id, source_channel, source_url,
                   categories, event_text, embedding, published_at, fetched_at, created_at
            FROM processed_events
            WHERE event_id = ANY(:ids);
        """), {"ids": event_ids}).fetchall()

        for row in rows:
            cats = row[4]
            if isinstance(cats, str):
                cats = json.loads(cats)
            emb = row[6]
            if isinstance(emb, str):
                emb = json.loads(emb)

            session.execute(text("""
                INSERT INTO candidate_events
                (event_id, source_news_id, source_channel, source_url, categories,
                 event_text, embedding, published_at, fetched_at, status, created_at)
                VALUES (:eid, :sid, :sch, :sur, :cats, :et, CAST(:emb AS vector), :pa, :fa, 'detained', :ca)
                ON CONFLICT (event_id) DO UPDATE SET status = 'detained';
            """), {
                "eid": row[0], "sid": row[1], "sch": row[2], "sur": row[3],
                "cats": json.dumps(cats, ensure_ascii=False) if cats else None,
                "et": row[5], "emb": str(emb) if emb else None,
                "pa": row[7], "fa": row[8], "ca": row[9],
            })

        session.execute(text("DELETE FROM processed_events WHERE event_id = ANY(:ids);"), {"ids": event_ids})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================
# 簇操作
# ============================================================

def write_clusters(clusters: list):
    """批量写入簇"""
    if not clusters:
        return
    session = _get_session()
    try:
        for c in clusters:
            centroid = _attr(c, "centroid")
            session.execute(text("""
                INSERT INTO event_clusters
                (cluster_id, parent_cluster_id, centroid, child_cluster_ids, depth,
                 dirty, splittable, brief_description, detailed_description, weekly_description,
                 recent_description, status, created_at, updated_at, description_updated_at)
                VALUES (:cid, :pcid, CAST(:centroid AS vector), :child_ids, :depth,
                        :dirty, :splittable, :bd, :dd, :wd, :rd, :status, :ca, :ua, :dua);
            """), {
                "cid": _attr(c, "cluster_id"),
                "pcid": _attr(c, "parent_cluster_id"),
                "centroid": str(centroid) if centroid else None,
                "child_ids": json.dumps(_attr(c, "child_cluster_ids", [])),
                "depth": _attr(c, "depth", 0),
                "dirty": _attr(c, "dirty", True),
                "splittable": _attr(c, "splittable", True),
                "bd": _attr(c, "brief_description"),
                "dd": _attr(c, "detailed_description"),
                "wd": _attr(c, "weekly_description"),
                "rd": _attr(c, "recent_description"),
                "status": _attr(c, "status", "active"),
                "ca": _ensure_utc(_attr(c, "created_at")) or _utc_now(),
                "ua": _ensure_utc(_attr(c, "updated_at")) or _utc_now(),
                "dua": _ensure_utc(_attr(c, "description_updated_at")) or _ensure_utc(_attr(c, "updated_at")) or _utc_now(),
            })
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_cluster_children(cluster_id: str, child_ids: List[str]):
    """更新父簇的 child_cluster_ids"""
    session = _get_session()
    try:
        session.execute(text("""
            UPDATE event_clusters
            SET child_cluster_ids = :child_ids, updated_at = :now
            WHERE cluster_id = :cluster_id;
        """), {"child_ids": json.dumps(child_ids), "now": _utc_now(), "cluster_id": cluster_id})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_cluster_descriptions(
    cluster_id: str,
    recent_description: Optional[str] = None,
    weekly_description: Optional[str] = None,
    detailed_description: Optional[str] = None,
    dirty: Optional[bool] = None,
    description_updated_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
):
    """更新簇的描述字段"""
    updates = []
    params = {"cluster_id": cluster_id}
    if recent_description is not None:
        updates.append("recent_description = :recent_description")
        params["recent_description"] = recent_description
    if weekly_description is not None:
        updates.append("weekly_description = :weekly_description")
        params["weekly_description"] = weekly_description
    if detailed_description is not None:
        updates.append("detailed_description = :detailed_description")
        params["detailed_description"] = detailed_description
    if dirty is not None:
        updates.append("dirty = :dirty")
        params["dirty"] = dirty
    if description_updated_at is not None:
        updates.append("description_updated_at = :description_updated_at")
        params["description_updated_at"] = description_updated_at
    if updated_at is not None:
        updates.append("updated_at = :updated_at")
        params["updated_at"] = updated_at

    if not updates:
        return

    session = _get_session()
    try:
        session.execute(text(f"UPDATE event_clusters SET {', '.join(updates)} WHERE cluster_id = :cluster_id;"), params)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_cluster_dirty(cluster_id: str, dirty: bool):
    update_cluster_descriptions(cluster_id, dirty=dirty)


def update_cluster_splittable(cluster_id: str, splittable: bool):
    session = _get_session()
    try:
        session.execute(text("UPDATE event_clusters SET splittable = :splittable WHERE cluster_id = :cluster_id;"),
                        {"splittable": splittable, "cluster_id": cluster_id})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def mark_clusters_splittable(cluster_ids: List[str]):
    if not cluster_ids:
        return
    session = _get_session()
    try:
        session.execute(text("UPDATE event_clusters SET splittable = TRUE WHERE cluster_id = ANY(:ids);"), {"ids": cluster_ids})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_all_splittable():
    """将所有簇的 splittable 重置为 TRUE（每次入库开始时调用）"""
    session = _get_session()
    try:
        session.execute(text("UPDATE event_clusters SET splittable = TRUE;"))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================
# 簇查询
# ============================================================

def load_all_clusters() -> List[ClusterItem]:
    session = _get_session()
    try:
        result = session.execute(text("""
            SELECT cluster_id, parent_cluster_id, centroid, child_cluster_ids,
                   depth, dirty, splittable, brief_description, detailed_description,
                   weekly_description, recent_description, status, created_at, updated_at,
                   description_updated_at
            FROM event_clusters;
        """))
        return [_row_to_cluster(row) for row in result.fetchall()]
    finally:
        session.close()


def load_cluster_centroids() -> Tuple[List[str], List[List[float]]]:
    session = _get_session()
    try:
        result = session.execute(text("SELECT cluster_id, centroid FROM event_clusters WHERE centroid IS NOT NULL;"))
        ids, centroids = [], []
        for row in result.fetchall():
            ids.append(row[0])
            c = row[1]
            if isinstance(c, str):
                c = json.loads(c)
            centroids.append(c)
        return ids, centroids
    finally:
        session.close()


def load_cluster_info(cluster_id: str) -> Optional[ClusterItem]:
    session = _get_session()
    try:
        result = session.execute(text("""
            SELECT cluster_id, parent_cluster_id, centroid, child_cluster_ids,
                   depth, dirty, splittable, brief_description, detailed_description,
                   weekly_description, recent_description, status, created_at, updated_at,
                   description_updated_at
            FROM event_clusters
            WHERE cluster_id = :cluster_id;
        """), {"cluster_id": cluster_id})
        row = result.fetchone()
        if not row:
            return None
        return _row_to_cluster(row)
    finally:
        session.close()


def get_all_clusters_with_count(splittable_only: bool = False) -> List[Dict]:
    session = _get_session()
    try:
        where = "WHERE ec.splittable = TRUE" if splittable_only else ""
        result = session.execute(text(f"""
            SELECT ec.cluster_id, ec.parent_cluster_id, ec.depth,
                   ec.brief_description, ec.dirty, ec.splittable,
                   COUNT(em.event_id) as event_count
            FROM event_clusters ec
            LEFT JOIN event_membership em ON ec.cluster_id = em.cluster_id
            {where}
            GROUP BY ec.cluster_id, ec.parent_cluster_id, ec.depth,
                     ec.brief_description, ec.dirty, ec.splittable
            ORDER BY ec.depth ASC;
        """))
        return [
            {"cluster_id": r[0], "parent_cluster_id": r[1], "depth": r[2],
             "brief_description": r[3], "dirty": r[4],
             "splittable": r[5], "event_count": r[6]}
            for r in result.fetchall()
        ]
    finally:
        session.close()


def load_clusters_by_depth(depth: int) -> List[ClusterItem]:
    session = _get_session()
    try:
        result = session.execute(text("""
            SELECT cluster_id, parent_cluster_id, centroid, child_cluster_ids,
                   depth, dirty, splittable, brief_description, detailed_description,
                   weekly_description, recent_description, status, created_at, updated_at,
                   description_updated_at
            FROM event_clusters WHERE depth = :depth;
        """), {"depth": depth})
        return [_row_to_cluster(row) for row in result.fetchall()]
    finally:
        session.close()


def get_max_depth() -> int:
    session = _get_session()
    try:
        result = session.execute(text("SELECT COALESCE(MAX(depth), 0) FROM event_clusters;"))
        return result.fetchone()[0]
    finally:
        session.close()


def load_all_embeddings() -> list:
    import numpy as np
    session = _get_session()
    try:
        result = session.execute(text("SELECT embedding FROM processed_events WHERE embedding IS NOT NULL;"))
        rows = result.fetchall()
        return np.array([row[0] for row in rows], dtype=np.float32)
    finally:
        session.close()


def get_cluster_update_info(cluster_id: str, since: Optional[datetime] = None, days: int = 7) -> dict:
    session = _get_session()
    try:
        if since is not None:
            result = session.execute(text("""
                SELECT COUNT(*) FROM processed_events pe
                JOIN event_membership em ON pe.event_id = em.event_id
                WHERE em.cluster_id = :cluster_id AND pe.published_at > :since;
            """), {"cluster_id": cluster_id, "since": since})
        else:
            result = session.execute(text("""
                SELECT COUNT(*) FROM processed_events pe
                JOIN event_membership em ON pe.event_id = em.event_id
                WHERE em.cluster_id = :cluster_id AND pe.published_at >= NOW() - MAKE_INTERVAL(days => :days);
            """), {"cluster_id": cluster_id, "days": days})
        recent_count = result.fetchone()[0]

        dirty_result = session.execute(text("""
            SELECT cluster_id, brief_description, weekly_description
            FROM event_clusters WHERE parent_cluster_id = :cluster_id AND dirty = TRUE;
        """), {"cluster_id": cluster_id})
        dirty_children = dirty_result.fetchall()

        return {
            "has_recent_events": recent_count > 0,
            "recent_events": None,
            "dirty_children": [
                {"cluster_id": r[0], "brief_description": r[1] or "", "weekly_description": r[2] or ""}
                for r in dirty_children
            ],
            "needs_update": recent_count > 0 or len(dirty_children) > 0,
        }
    finally:
        session.close()


# ============================================================
# 归属关系操作
# ============================================================

def write_memberships(memberships: list):
    if not memberships:
        return
    session = _get_session()
    try:
        for m in memberships:
            session.execute(text("""
                INSERT INTO event_membership (event_id, cluster_id, sim_score, checked, created_at)
                VALUES (:eid, :cid, :ss, :ch, :ca)
                ON CONFLICT (event_id, cluster_id) DO NOTHING;
            """), {
                "eid": _attr(m, "event_id"),
                "cid": _attr(m, "cluster_id"),
                "ss": _attr(m, "sim_score"),
                "ch": _attr(m, "checked", False),
                "ca": _ensure_utc(_attr(m, "created_at")) or _utc_now(),
            })
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_membership(event_id: str, cluster_id: str):
    session = _get_session()
    try:
        session.execute(text("DELETE FROM event_membership WHERE event_id = :eid AND cluster_id = :cid;"),
                        {"eid": event_id, "cid": cluster_id})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def batch_delete_memberships(event_ids: List[str], cluster_id: str):
    if not event_ids:
        return
    session = _get_session()
    try:
        session.execute(text("DELETE FROM event_membership WHERE cluster_id = :cid AND event_id = ANY(:eids);"),
                        {"cid": cluster_id, "eids": event_ids})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_membership_count(event_id: str) -> int:
    session = _get_session()
    try:
        result = session.execute(text("SELECT COUNT(*) FROM event_membership WHERE event_id = :eid;"), {"eid": event_id})
        return result.fetchone()[0]
    finally:
        session.close()


def check_memberships(event_ids: List[str], cluster_id: str):
    if not event_ids:
        return
    session = _get_session()
    try:
        session.execute(text("""
            UPDATE event_membership SET checked = TRUE
            WHERE cluster_id = :cid AND event_id = ANY(:eids);
        """), {"cid": cluster_id, "eids": event_ids})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def load_existing_event_embeddings() -> Tuple[List[str], List[List[float]]]:
    """加载 candidate_events 中已有事件的 embedding（用于去重）"""
    session = _get_session()
    try:
        result = session.execute(text("SELECT event_id, embedding FROM candidate_events WHERE embedding IS NOT NULL;"))
        ids, embeddings = [], []
        for row in result.fetchall():
            ids.append(row[0])
            emb = row[1]
            if isinstance(emb, str):
                emb = json.loads(emb)
            embeddings.append(emb)
        return ids, embeddings
    finally:
        session.close()


def write_candidate_event(event_id: str, source_news_id: str, source_channel: str,
                          source_url: str, categories, event_text: str,
                          embedding, published_at, fetched_at):
    """写入单条 candidate_event"""
    session = _get_session()
    try:
        cats = json.dumps(categories, ensure_ascii=False) if categories else None
        session.execute(text("""
            INSERT INTO candidate_events
            (event_id, source_news_id, source_channel, source_url, categories,
             event_text, embedding, published_at, fetched_at, status)
            VALUES (:eid, :sid, :sch, :sur, :cats, :et, CAST(:emb AS vector), :pa, :fa, 'pending')
            ON CONFLICT (event_id) DO NOTHING;
        """), {
            "eid": event_id, "sid": source_news_id, "sch": source_channel,
            "sur": source_url, "cats": cats, "et": event_text,
            "emb": str(embedding) if embedding else None,
            "pa": _ensure_utc(published_at), "fa": _ensure_utc(fetched_at),
        })
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================
# 过期清理
# ============================================================

def delete_expired_detained(days: int = 14) -> int:
    """删除 detained 状态超过 N 天的事件，返回删除数量"""
    session = _get_session()
    try:
        result = session.execute(text("""
            DELETE FROM candidate_events
            WHERE status = 'detained'
              AND created_at < NOW() - MAKE_INTERVAL(days => :days);
        """), {"days": days})
        session.commit()
        return result.rowcount
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ============================================================
# 统计
# ============================================================

def count_pending() -> int:
    session = _get_session()
    try:
        result = session.execute(text("SELECT COUNT(*) FROM candidate_events WHERE status = 'pending';"))
        return result.fetchone()[0]
    finally:
        session.close()


def count_detained() -> int:
    session = _get_session()
    try:
        result = session.execute(text("SELECT COUNT(*) FROM candidate_events WHERE status = 'detained';"))
        return result.fetchone()[0]
    finally:
        session.close()


def count_processed() -> int:
    session = _get_session()
    try:
        result = session.execute(text("SELECT COUNT(*) FROM processed_events;"))
        return result.fetchone()[0]
    finally:
        session.close()


def count_clusters() -> int:
    session = _get_session()
    try:
        result = session.execute(text("SELECT COUNT(*) FROM event_clusters;"))
        return result.fetchone()[0]
    finally:
        session.close()
