"""单独启动建图守护进程"""
import asyncio
import logging

from src.graph.daemon import GraphDaemon
from src.storage.db_config import db_manager
from src.storage.graph_repository import init_graph_extensions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


async def main():
    db_manager.verify_and_create_tables()
    init_graph_extensions()
    daemon = GraphDaemon()
    try:
        await daemon.run()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    asyncio.run(main())
