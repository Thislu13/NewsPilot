"""Generate daily digest snapshot JSON from local PostgreSQL.

本地版本：连接 localhost:5432 (docker 暴露端口) 生成 digest_cache.json，
由 sync_to_server.sh 调用，再随 dump 一起 scp 到远程。

new_signals 已过滤 depth=0（避免新分裂簇被统计为 new）。

用法:
    python scripts/generate_digest_json.py --output /tmp/digest_cache.json
"""
import argparse
import json
import os
from datetime import datetime, timezone

import psycopg


DB_CONFIG = {
    "host": os.environ.get("NEWSPILOT_DB_HOST", "localhost"),
    "port": int(os.environ.get("NEWSPILOT_DB_PORT", "5432")),
    "database": os.environ.get("NEWSPILOT_DB_NAME", "newspilot"),
    "user": os.environ.get("NEWSPILOT_DB_USER", "postgres"),
    "password": os.environ.get("NEWSPILOT_DB_PASSWORD", "postgres123"),
}


def parse_args():
    parser = argparse.ArgumentParser(description="Generate daily digest snapshot JSON")
    parser.add_argument('--date', dest='target_date', default=None, help='Snapshot date in YYYY-MM-DD format')
    parser.add_argument('--output', default='/tmp/digest_cache.json', help='Output JSON path')
    parser.add_argument('--limit-new', dest='limit_new', type=int, default=None, help='Limit new_signals count')
    parser.add_argument('--limit-hot', dest='limit_hot', type=int, default=None, help='Limit hot_signals count')
    return parser.parse_args()


def build_new_signals(cur, snapshot_date, limit):
    sql = """
        SELECT ec.cluster_id,
               COALESCE(total_cnt.c, 0) AS new_events_count,
               ec.created_at
        FROM event_clusters ec
        LEFT JOIN (
            SELECT cluster_id, COUNT(*) AS c
            FROM event_membership
            GROUP BY cluster_id
        ) total_cnt ON ec.cluster_id = total_cnt.cluster_id
        WHERE ec.created_at >= %s::date AND ec.depth = 0
          AND ec.created_at < %s::date + INTERVAL '1 day'
        ORDER BY ec.created_at DESC, ec.cluster_id
    """
    params = [snapshot_date, snapshot_date]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    return [{
        'cluster_id': row[0],
        'new_events_count': int(row[1] or 0),
        'rank': idx,
        'created_at': row[2].isoformat() if row[2] else None,
    } for idx, row in enumerate(rows, start=1)]


def build_hot_signals(cur, snapshot_date, limit):
    sql = """
        SELECT ec.cluster_id,
               COUNT(*) AS new_events_count,
               MAX(pe.published_at) AS latest_published_at
        FROM processed_events pe
        JOIN event_membership em ON pe.event_id = em.event_id
        JOIN event_clusters ec ON ec.cluster_id = em.cluster_id
        WHERE pe.published_at >= %s::date
          AND pe.published_at < %s::date + INTERVAL '1 day'
        GROUP BY ec.cluster_id, ec.created_at
        ORDER BY new_events_count DESC, ec.created_at DESC, ec.cluster_id
    """
    params = [snapshot_date, snapshot_date]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    return [{
        'cluster_id': row[0],
        'new_events_count': int(row[1] or 0),
        'rank': idx,
        'latest_published_at': row[2].isoformat() if row[2] else None,
    } for idx, row in enumerate(rows, start=1)]


def main():
    args = parse_args()
    snapshot_date = args.target_date or datetime.now(timezone.utc).date().isoformat()

    conn = psycopg.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        dbname=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        options='-c client_min_messages=ERROR',
    )
    try:
        with conn.cursor() as cur:
            new_signals = build_new_signals(cur, snapshot_date, args.limit_new)
            hot_signals = build_hot_signals(cur, snapshot_date, args.limit_hot)

        payload = {
            'date': snapshot_date,
            'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
            'new_signals': new_signals,
            'hot_signals': hot_signals,
            'total_new_signals': len(new_signals),
            'total_hot_signals': len(hot_signals),
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[generate_digest_json] wrote {args.output} (new={len(new_signals)}, hot={len(hot_signals)})")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
