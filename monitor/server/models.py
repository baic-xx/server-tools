"""数据模型定义"""
import re
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
    # 管理信息（JSON 导入）
    public_ip: Optional[str] = None
    users: list[str] = []
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


# ─── 工具函数 ───

# 已知 GPU 型号对应的显存大小 (MB)
KNOWN_GPU_VRAM: dict[str, int] = {
    "5090": 32607,
    "H100": 81559,
    "A100": 81920,
}


def derive_gpu_type(gpu_models: list[str]) -> str:
    """从 GPU 型号列表推导短类型名，如 'NVIDIA A100-SXM4-40GB' → 'A100'"""
    if not gpu_models:
        return "CPU"
    model = gpu_models[0]
    # 匹配已知 GPU 型号标识
    m = re.search(r'(A100|H100|5090|V100|4090|3090)', model, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # 兜底：取厂商前缀后的第一段
    if " " in model:
        model = model.split(" ", 1)[1]
    return model.split("-")[0].split()[0]


def build_full_hostname(short_hostname: str, gpu_models: list[str]) -> str:
    """从短 hostname + GPU 型号构建完整 hostname，如 'node01' + A100 → 'node01-A100'
    如果 hostname 已经包含已知 GPU 后缀（-A100, -H100, -5090, -CPU 等）则不重复添加。
    """
    # hostname 已带已知 GPU 后缀 → 直接返回
    if _extract_gpu_type_from_hostname(short_hostname) is not None:
        return short_hostname
    if short_hostname.endswith("-CPU"):
        return short_hostname

    gpu_type = derive_gpu_type(gpu_models)
    suffix = f"-{gpu_type}"
    return f"{short_hostname}{suffix}"


def _extract_gpu_type_from_hostname(hostname: str) -> str | None:
    """从完整 hostname 中提取 GPU 类型后缀，如 'node01-A100' → 'A100'"""
    for gpu_type in KNOWN_GPU_VRAM:
        if hostname.endswith(f"-{gpu_type}"):
            return gpu_type
    if hostname.endswith("-CPU"):
        return "CPU"
    return None


def match_server_by_hostname(
    candidates: list[dict],
    metrics_data,
    client_ip: str | None = None,
) -> dict | None:
    """从同名服务器列表中匹配正确的一个（三步策略）
    1. 只有一个候选 → 直接返回
    2. 按 GPU 显存(mem_total_mb)匹配已知型号
    3. 按 IP 匹配
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # 第二步：按 GPU 显存匹配 —— 找候选中 hostname 后缀对应的显存最接近 metrics 的
    gpus = metrics_data.gpus if metrics_data and metrics_data.gpus else []
    if gpus:
        vram = gpus[0].mem_total_mb
        best, best_diff = None, float("inf")
        for s in candidates:
            gpu_type = _extract_gpu_type_from_hostname(s.get("hostname", ""))
            expected = KNOWN_GPU_VRAM.get(gpu_type or "")
            if expected:
                diff = abs(vram - expected)
                if diff < best_diff:
                    best, best_diff = s, diff
        if best and best_diff < 2000:
            return best

    # 第三步：按 IP 匹配
    if client_ip:
        for s in candidates:
            if s.get("ip") == client_ip:
                return s

    # 兜底：返回第一个
    return candidates[0]
