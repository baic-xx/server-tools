"""MongoDB 异步连接管理"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, MONGO_DB

client: AsyncIOMotorClient = None
db = None

MAX_RETRIES = 10
RETRY_DELAY = 3  # 秒


async def connect_db():
    """建立 MongoDB 连接（带重试）"""
    global client, db

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            # 测试连接是否真的可用
            await client.admin.command("ping")

            db = client[MONGO_DB]

            # 创建索引
            await db.servers.create_index("hostname", unique=True)
            await db.metrics.create_index([("hostname", 1), ("timestamp", -1)])

            print(f"[DB] 已连接 MongoDB: {MONGO_URI}/{MONGO_DB}")
            return

        except Exception as e:
            print(f"[DB] 连接失败 ({attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"[DB] 已达到最大重试次数，MongoDB 不可用")
                raise


async def close_db():
    """关闭 MongoDB 连接"""
    global client
    if client:
        client.close()
        print("[DB] 已关闭 MongoDB 连接")
