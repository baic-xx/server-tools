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
    since = datetime.now() - timedelta(hours=hours)
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


@router.get("/offline-events")
async def get_offline_events(days: int = Query(default=7, ge=1, le=90)):
    """获取所有服务器的离线记录（超过 20 分钟无上报视为离线，每次离线一条记录）"""
    since = datetime.now() - timedelta(days=days)
    offline_events = []
    OFFLINE_GAP = 20 * 60  # 20 分钟

    async for server_doc in database.db.servers.find():
        hostname = server_doc["hostname"]
        cursor = database.db.metrics.find(
            {"hostname": hostname, "timestamp": {"$gte": since}},
            {"timestamp": 1, "_id": 0},
        ).sort("timestamp", 1)
        timestamps = [doc["timestamp"] async for doc in cursor]

        if not timestamps:
            if not _is_online(server_doc.get("last_seen")):
                registered = server_doc.get("registered_at")
                if registered:
                    offline_events.append({
                        "hostname": hostname,
                        "offline_from": registered,
                        "offline_to": None,
                    })
            continue

        # 同一台服务器的 metrics 内部检测间隔，不受时区影响
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]).total_seconds()
            if gap > OFFLINE_GAP:
                offline_events.append({
                    "hostname": hostname,
                    "offline_from": timestamps[i - 1],
                    "offline_to": timestamps[i],
                })

        # 当前是否离线：用 last_seen（服务端时间，时区一致）
        if not _is_online(server_doc.get("last_seen")):
            offline_events.append({
                "hostname": hostname,
                "offline_from": server_doc.get("last_seen") or timestamps[-1],
                "offline_to": None,
            })

    offline_events.sort(key=lambda e: e["offline_from"], reverse=True)
    return offline_events


@router.get("/gpu-overall")
async def get_gpu_overall(hours: int = Query(default=12, ge=1, le=168)):
    """所有服务器 GPU 平均使用率曲线（10 分钟刻度，每个桶取各服务器最近一次上报）"""
    now = datetime.now()
    since = now - timedelta(hours=hours)
    BUCKET_MIN = 10

    # 从现在开始往过去方向生成 10 分钟对齐的桶
    aligned_now = now.replace(minute=(now.minute // BUCKET_MIN) * BUCKET_MIN, second=0, microsecond=0)
    buckets = []
    t = aligned_now
    while t > since:
        bucket_start = t - timedelta(minutes=BUCKET_MIN)
        buckets.append((bucket_start, t))
        t = bucket_start

    data = []
    for bucket_start, bucket_end in buckets:
        # 获取该桶内每台服务器的最新一条 metric
        latest_per_server = {}
        cursor = database.db.metrics.find(
            {"timestamp": {"$gte": bucket_start, "$lt": bucket_end}, "gpus": {"$ne": []}},
            {"hostname": 1, "gpus": 1, "_id": 0},
        ).sort("timestamp", -1)

        async for doc in cursor:
            h = doc["hostname"]
            if h not in latest_per_server:
                gpu_avg = sum(g.get("compute_util", 0) for g in doc.get("gpus", [])) / len(doc["gpus"]) if doc.get("gpus") else 0
                latest_per_server[h] = gpu_avg

        if latest_per_server:
            overall_avg = round(sum(latest_per_server.values()) / len(latest_per_server), 1)
            data.append({
                "timestamp": bucket_start,
                "avg_util": overall_avg,
            })

    # 结果按时间正序（从早到晚）
    data.reverse()
    return data


@router.get("/gpu-ranking")
async def get_gpu_ranking(hours: int = Query(default=6, ge=1, le=168)):
    """GPU 使用率排行（所有服务器，按平均 GPU 利用率降序）"""
    since = datetime.now() - timedelta(hours=hours)
    ranking = []

    async for server_doc in database.db.servers.find():
        hostname = server_doc["hostname"]
        gpu_count = server_doc.get("gpu_count", 0)
        if gpu_count == 0:
            continue

        # 获取该时间段内所有含 GPU 数据的 metrics
        cursor = database.db.metrics.find(
            {"hostname": hostname, "timestamp": {"$gte": since}, "gpus": {"$ne": []}},
            {"gpus": 1, "_id": 0},
        )
        gpu_values = []
        async for doc in cursor:
            for gpu in doc.get("gpus", []):
                gpu_values.append(gpu.get("compute_util", 0))

        avg_util = round(sum(gpu_values) / len(gpu_values), 1) if gpu_values else 0
        ranking.append({
            "hostname": hostname,
            "gpu_count": gpu_count,
            "avg_util": avg_util,
            "sample_count": len(gpu_values),
        })

    # 按平均利用率降序
    ranking.sort(key=lambda x: x["avg_util"], reverse=True)
    # 加排名
    for i, r in enumerate(ranking):
        r["rank"] = i + 1
    return ranking
