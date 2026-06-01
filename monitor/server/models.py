"""数据模型定义"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ─── GPU 相关 ───

class GpuMetric(BaseModel):
    gpu_id: int
    compute_util: int
    mem_util: int
    mem_used_mb: int
    mem_total_mb: int
    temp_c: int
    power_w: float


# ─── 服务器注册 ───

class ServerRegister(BaseModel):
    hostname: str
    ip: str
    os: str
    cpu_count: int
    gpu_count: int = 0
    gpu_models: list[str] = []


# ─── 监控数据上报 ───

class MetricUpload(BaseModel):
    timestamp: Optional[datetime] = None
    cpu_pct: float
    mem_pct: float
    mem_used_gb: float
    mem_total_gb: float
    disk_pct: float
    disk_used_gb: float
    disk_total_gb: float
    load_1m: float
    load_5m: float
    load_15m: float
    net_rx_mb: float = 0
    net_tx_mb: float = 0
    gpus: list[GpuMetric] = []


# ─── API 响应 ───

class ServerInfo(BaseModel):
    hostname: str
    ip: str
    os: str
    cpu_count: int
    gpu_count: int
    gpu_models: list[str]
    registered_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    online: bool = False
    # 最新指标摘要（可选）
    latest_cpu: Optional[float] = None
    latest_mem: Optional[float] = None
    latest_gpus: Optional[list[GpuMetric]] = None


class OverviewStats(BaseModel):
    total_servers: int
    online_servers: int
    offline_servers: int
    avg_cpu: Optional[float] = None
    avg_mem: Optional[float] = None
    total_gpus: int = 0
