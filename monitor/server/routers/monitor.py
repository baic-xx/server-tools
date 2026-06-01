"""前端查询 API — 服务器列表、详情、历史数据（仅用于 Web 前端读取展示）"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, HTTPException
import database
from models import ServerInfo, OverviewStats
from config import ONLINE_THRESHOLD

router = APIRouter(tags=["查询"])


def _is_online(last_seen: datetime | None) -> bool:
    """判断服务器是否在线"""
    if last_seen is None:
        return False
    delta = (datetime.now() - last_seen).total_seconds()
    return delta < ONLINE_THRESHOLD


@router.get("/servers", response_model=list[ServerInfo])
async def list_servers():
    """获取所有服务器列表（含在线状态和最新指标摘要）"""
    servers = []
    async for doc in database.db.servers.find().sort("hostname", 1):
        latest = await database.db.metrics.find_one(
            {"hostname": doc["hostname"]},
            sort=[("timestamp", -1)],
        )
        info = ServerInfo(
            hostname=doc["hostname"],
            ip=doc["ip"],
            os=doc["os"],
            cpu_count=doc["cpu_count"],
            gpu_count=doc["gpu_count"],
            gpu_models=doc["gpu_models"],
            registered_at=doc.get("registered_at"),
            last_seen=doc.get("last_seen"),
            online=_is_online(doc.get("last_seen")),
            latest_cpu=latest["cpu_pct"] if latest else None,
            latest_mem=latest["mem_pct"] if latest else None,
            latest_gpus=latest["gpus"] if latest and latest.get("gpus") else None,
        )
        servers.append(info)
    return servers


@router.get("/servers/{hostname}", response_model=ServerInfo)
async def get_server(hostname: str):
    """获取单台服务器详情"""
    doc = await database.db.servers.find_one({"hostname": hostname})
    if not doc:
        raise HTTPException(status_code=404, detail=f"服务器 {hostname} 不存在")

    latest = await database.db.metrics.find_one(
        {"hostname": hostname},
        sort=[("timestamp", -1)],
    )
    return ServerInfo(
        hostname=doc["hostname"],
        ip=doc["ip"],
        os=doc["os"],
        cpu_count=doc["cpu_count"],
        gpu_count=doc["gpu_count"],
        gpu_models=doc["gpu_models"],
        registered_at=doc.get("registered_at"),
        last_seen=doc.get("last_seen"),
        online=_is_online(doc.get("last_seen")),
        latest_cpu=latest["cpu_pct"] if latest else None,
        latest_mem=latest["mem_pct"] if latest else None,
        latest_gpus=latest["gpus"] if latest and latest.get("gpus") else None,
    )


@router.get("/servers/{hostname}/metrics")
async def get_metrics(hostname: str, hours: int = Query(default=24, ge=1, le=168)):
    """获取服务器历史监控数据（默认最近 24 小时）"""
    since = datetime.utcnow() - timedelta(hours=hours)
    cursor = database.db.metrics.find(
        {"hostname": hostname, "timestamp": {"$gte": since}},
        {"_id": 0},
    ).sort("timestamp", 1)
    return await cursor.to_list(length=10000)


@router.get("/servers/{hostname}/metrics/latest")
async def get_latest_metrics(hostname: str):
    """获取服务器最新一条监控数据"""
    metric = await database.db.metrics.find_one(
        {"hostname": hostname},
        {"_id": 0},
        sort=[("timestamp", -1)],
    )
    if not metric:
        raise HTTPException(status_code=404, detail=f"服务器 {hostname} 暂无监控数据")
    return metric


@router.get("/stats/overview", response_model=OverviewStats)
async def get_overview():
    """获取总览统计"""
    total = await database.db.servers.count_documents({})
    online = 0
    cpu_values = []
    mem_values = []
    total_gpus = 0

    async for doc in database.db.servers.find():
        if _is_online(doc.get("last_seen")):
            online += 1
        total_gpus += doc.get("gpu_count", 0)

        latest = await database.db.metrics.find_one(
            {"hostname": doc["hostname"]},
            sort=[("timestamp", -1)],
        )
        if latest:
            cpu_values.append(latest["cpu_pct"])
            mem_values.append(latest["mem_pct"])

    return OverviewStats(
        total_servers=total,
        online_servers=online,
        offline_servers=total - online,
        avg_cpu=round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else None,
        avg_mem=round(sum(mem_values) / len(mem_values), 1) if mem_values else None,
        total_gpus=total_gpus,
    )
