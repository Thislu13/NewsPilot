"""探索远程数据库 172.17.18.108 的表结构

运行：python scripts/inspect_remote_db.py
"""
import sys
from sqlalchemy import create_engine, text, inspect


REMOTE_URL = "postgresql+psycopg://postgres:postgres123@47.239.188.192:5432/newspilot"


def main():
    print(f"连接远程数据库: {REMOTE_URL}")
    try:
        engine = create_engine(REMOTE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 10})
        with engine.connect() as conn:
            print("\n=== 1. 所有表列表 ===")
            tables = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)).fetchall()
            for (name,) in tables:
                print(f"  - {name}")

            print("\n=== 2. 查找 hot/new/signal/topic 相关表 ===")
            keywords = ["hot", "new", "signal", "topic"]
            for (name,) in tables:
                if any(k in name.lower() for k in keywords):
                    print(f"\n[表] {name}")
                    cols = conn.execute(text("""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = :tn
                        ORDER BY ordinal_position;
                    """), {"tn": name}).fetchall()
                    for col in cols:
                        print(f"    {col[0]:30s} {col[1]:20s} nullable={col[2]:5s} default={col[3]}")
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
                    print(f"    行数: {count}")
                    if count > 0:
                        sample = conn.execute(text(f"SELECT * FROM {name} LIMIT 3")).fetchall()
                        print(f"    样本数据:")
                        for row in sample:
                            print(f"      {row}")

            print("\n=== 3. event_clusters 表 ===")
            try:
                count = conn.execute(text("SELECT COUNT(*) FROM event_clusters")).scalar()
                print(f"  行数: {count}")
                if count > 0:
                    by_depth = conn.execute(text("""
                        SELECT depth, COUNT(*) FROM event_clusters
                        GROUP BY depth ORDER BY depth;
                    """)).fetchall()
                    print(f"  按 depth 分布: {by_depth}")
            except Exception as e:
                print(f"  event_clusters 表不存在或访问异常: {e}")

    except Exception as e:
        print(f"\n[ERROR] 连接失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
