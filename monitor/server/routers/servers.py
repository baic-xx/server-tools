"""客户端上报 API — 服务器注册 & 监控数据上传"""
import re
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, status
import database
from models import ServerRegister, MetricUpload, build_full_hostname, match_server_by_hostname

router = APIRouter(prefix="/servers", tags=["上报"])


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_server(data: ServerRegister):
    """服务器注册或更新硬件信息
    - 如果 hostname 已经是完整形式（如 node01-A100），直接使用
    - 如果 hostname 是短形式（如 node01），自动拼接 GPU 类型 → node01-A100
    """
    now = datetime.now()
    full_hostname = build_full_hostname(data.hostname, data.gpu_models)

    doc = data.model_dump()
    doc["hostname"] = full_hostname
    doc["last_seen"] = now

    existing = await database.db.servers.find_one({"hostname": full_hostname})
    if existing:
        await database.db.servers.update_one(
            {"hostname": full_hostname},
            {"$set": {k: v for k, v in doc.items() if k != "registered_at"}},
        )
        return {"message": "服务器信息已更新", "action": "updated"}
    else:
        doc["registered_at"] = now
        await database.db.servers.insert_one(doc)
        return {"message": "服务器注册成功", "action": "registered"}


@router.post("/{hostname}/metrics", status_code=status.HTTP_201_CREATED)
async def upload_metrics(hostname: str, data: MetricUpload, request: Request):
    """接收客户端上报的监控数据
    客户端可能发短 hostname（node01）或完整 hostname（node01-A100），
    服务端用前缀匹配找到候选，再通过显存/IP 区分。
    """
    # 前缀匹配：精确匹配或以 "{hostname}-" 开头
    #   "node01"       → 匹配 "node01", "node01-A100", "node01-H100"
    #   "node01-A100"  → 匹配 "node01-A100"（精确）
    pattern = re.compile(f"^{re.escape(hostname)}(-|$)")
    cursor = database.db.servers.find({"hostname": pattern})
    candidates = await cursor.to_list(length=10)

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"服务器 {hostname} 尚未注册，请先调用 /api/servers/register",
        )

    # 三步匹配：唯一性 → GPU 显存 → IP
    client_ip = request.client.host if request.client else None
    server = match_server_by_hostname(candidates, data, client_ip)
    full_hostname = server["hostname"]

    now = datetime.now()
    doc = data.model_dump()
    doc["hostname"] = full_hostname
    doc["timestamp"] = now

    await database.db.metrics.insert_one(doc)

    await database.db.servers.update_one(
        {"hostname": full_hostname},
        {"$set": {"last_seen": now}},
    )

    return {"message": "数据已接收", "timestamp": doc["timestamp"].isoformat()}
