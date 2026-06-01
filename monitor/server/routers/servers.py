"""客户端上报 API — 服务器注册 & 监控数据上传"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
import database
from models import ServerRegister, MetricUpload

router = APIRouter(prefix="/servers", tags=["上报"])


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_server(data: ServerRegister):
    """服务器注册或更新硬件信息"""
    now = datetime.now()
    doc = data.model_dump()
    doc["last_seen"] = now

    existing = await database.db.servers.find_one({"hostname": data.hostname})
    if existing:
        # 更新已有服务器信息
        await database.db.servers.update_one(
            {"hostname": data.hostname},
            {"$set": {k: v for k, v in doc.items() if k != "registered_at"}},
        )
        return {"message": "服务器信息已更新", "action": "updated"}
    else:
        # 首次注册
        doc["registered_at"] = now
        await database.db.servers.insert_one(doc)
        return {"message": "服务器注册成功", "action": "registered"}


@router.post("/{hostname}/metrics", status_code=status.HTTP_201_CREATED)
async def upload_metrics(hostname: str, data: MetricUpload):
    """接收客户端上报的监控数据"""
    # 检查服务器是否已注册
    server = await database.db.servers.find_one({"hostname": hostname})
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"服务器 {hostname} 尚未注册，请先调用 /api/servers/register",
        )

    now = datetime.now()
    doc = data.model_dump()
    doc["hostname"] = hostname
    if doc["timestamp"] is None:
        doc["timestamp"] = now

    await database.db.metrics.insert_one(doc)

    # 更新服务器最后活跃时间
    await database.db.servers.update_one(
        {"hostname": hostname},
        {"$set": {"last_seen": now}},
    )

    return {"message": "数据已接收", "timestamp": doc["timestamp"].isoformat()}
