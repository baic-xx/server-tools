"""服务器监控客户端 — 采集系统指标并定时上报到监控服务端

使用方式:
  # 默认每 10 分钟上报一次
  python3 monitor_client.py --server http://your-monitor-server:30252

  # 自定义上报间隔（秒）
  python3 monitor_client.py --server http://your-monitor-server:30252 --interval 600

  # 指定客户端 IP（用于在服务端展示）
  python3 monitor_client.py --server http://your-monitor-server:30252 --ip 10.0.0.5

  # 后台运行
  nohup python3 monitor_client.py --server http://your-monitor-server:30252 &
"""

import argparse
import os
import platform
import signal
import socket
import subprocess
import time
from datetime import datetime

import psutil
import requests


# ─── 全局变量 ───

running = True
SERVER_URL = ""
REPORT_INTERVAL = 600  # 默认 10 分钟
MAX_RETRY_WAIT = 60  # 最大重试等待秒数


# ─── 信号处理 ───

def handle_signal(sig, frame):
    """优雅退出"""
    global running
    print(f"\n[{now()}] 收到退出信号，正在停止...")
    running = False


def now():
    """当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─── 硬件信息采集 ───

def get_hostname():
    return socket.gethostname()


def get_ip():
    """获取本机 IP（优先取外网可达的 IP）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def get_os_info():
    """获取操作系统信息"""
    return f"{platform.system()} {platform.release()}"


def get_cpu_count():
    return psutil.cpu_count(logical=True)


def get_gpu_info():
    """查询 GPU 信息（复用 gpu_monitor.py 的 nvidia-smi 查询模式）
    如果没有 GPU 则返回空列表
    """
    gpus = []
    try:
        output = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=index,gpu_name,utilization.gpu,utilization.memory,"
            "memory.used,memory.total,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits"
        ], timeout=10).decode().strip()

        models = []
        for line in output.split("\n"):
            parts = [x.strip() for x in line.split(",")]
            gpu_id = int(parts[0])
            gpu_name = parts[1]
            models.append(gpu_name)
            gpus.append({
                "gpu_id": gpu_id,
                "compute_util": int(parts[2]),
                "mem_util": int(parts[3]),
                "mem_used_mb": int(parts[4]),
                "mem_total_mb": int(parts[5]),
                "temp_c": int(parts[6]),
                "power_w": float(parts[7]),
            })
        return gpus, list(dict.fromkeys(models))  # 去重保留顺序
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return [], []


# ─── 系统指标采集 ───

def collect_metrics():
    """采集所有系统指标"""
    # CPU
    cpu_pct = psutil.cpu_percent(interval=1)

    # 内存
    mem = psutil.virtual_memory()

    # 磁盘（根分区）
    disk = psutil.disk_usage("/")

    # 系统负载
    load_1m, load_5m, load_15m = os.getloadavg()

    # 网络（累计值，转为 MB）
    net = psutil.net_io_counters()
    net_rx_mb = round(net.bytes_recv / 1024 / 1024, 2)
    net_tx_mb = round(net.bytes_sent / 1024 / 1024, 2)

    # GPU
    gpus, _ = get_gpu_info()

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "cpu_pct": round(cpu_pct, 1),
        "mem_pct": round(mem.percent, 1),
        "mem_used_gb": round(mem.used / 1024 / 1024 / 1024, 2),
        "mem_total_gb": round(mem.total / 1024 / 1024 / 1024, 2),
        "disk_pct": round(disk.percent, 1),
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
        "load_1m": round(load_1m, 2),
        "load_5m": round(load_5m, 2),
        "load_15m": round(load_15m, 2),
        "net_rx_mb": net_rx_mb,
        "net_tx_mb": net_tx_mb,
        "gpus": gpus,
    }
    return metrics


# ─── 网络通信 ───

def register_server(ip_override=None):
    """向服务端注册本机硬件信息"""
    _, gpu_models = get_gpu_info()
    gpus, _ = get_gpu_info()

    payload = {
        "hostname": get_hostname(),
        "ip": ip_override or get_ip(),
        "os": get_os_info(),
        "cpu_count": get_cpu_count(),
        "gpu_count": len(gpus) if gpus else 0,
        "gpu_models": gpu_models if gpu_models else [],
    }

    resp = requests.post(
        f"{SERVER_URL}/api/servers/register",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def upload_metrics(metrics):
    """上报监控数据"""
    hostname = get_hostname()
    resp = requests.post(
        f"{SERVER_URL}/api/servers/{hostname}/metrics",
        json=metrics,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def request_with_retry(fn, max_retries=5, description="操作"):
    """带指数退避的重试包装"""
    wait = 1
    for attempt in range(max_retries):
        try:
            return fn()
        except requests.ConnectionError:
            print(f"[{now()}] {description}失败：无法连接服务器 {SERVER_URL}，{wait}s 后重试 ({attempt + 1}/{max_retries})")
        except requests.Timeout:
            print(f"[{now()}] {description}失败：请求超时，{wait}s 后重试 ({attempt + 1}/{max_retries})")
        except requests.HTTPError as e:
            print(f"[{now()}] {description}失败：HTTP {e.response.status_code}，{wait}s 后重试 ({attempt + 1}/{max_retries})")
        except Exception as e:
            print(f"[{now()}] {description}失败：{e}，{wait}s 后重试 ({attempt + 1}/{max_retries})")

        time.sleep(wait)
        wait = min(wait * 2, MAX_RETRY_WAIT)

    print(f"[{now()}] {description}已达到最大重试次数，本次跳过")
    return None


# ─── 主循环 ───

def main():
    global SERVER_URL, REPORT_INTERVAL, running

    parser = argparse.ArgumentParser(
        description="服务器监控客户端 — 采集系统指标并定时上报",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python3 monitor_client.py --server http://monitor.example.com:30252\n"
               "  python3 monitor_client.py --server http://10.0.0.1:30252 --interval 600\n",
    )
    parser.add_argument("--server", required=True, help="监控服务端地址（如 http://10.0.0.1:30252）")
    parser.add_argument("--interval", type=int, default=600, help="上报间隔秒数（默认 600 = 10 分钟）")
    parser.add_argument("--ip", type=str, default=None, help="指定本机 IP（可选，用于服务端展示）")
    args = parser.parse_args()

    SERVER_URL = args.server.rstrip("/")
    REPORT_INTERVAL = max(args.interval, 60)  # 最少 60 秒

    # 注册信号处理
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"[{now()}] ========== 服务器监控客户端启动 ==========")
    print(f"[{now()}] 服务端: {SERVER_URL}")
    print(f"[{now()}] 上报间隔: {REPORT_INTERVAL}s ({REPORT_INTERVAL // 60} 分钟)")
    print(f"[{now()}] 主机名: {get_hostname()}")
    print(f"[{now()}] 按 Ctrl+C 停止\n")

    # 首次注册
    result = request_with_retry(
        lambda: register_server(args.ip),
        description="注册",
    )
    if result:
        print(f"[{now()}] 注册成功: {result['message']}")
    else:
        print(f"[{now()}] 注册失败，将在下次上报时重试")

    # 主循环：定时采集并上报
    while running:
        # 采集指标
        try:
            metrics = collect_metrics()
        except Exception as e:
            print(f"[{now()}] 采集指标失败: {e}")
            time.sleep(60)
            continue

        # 上报
        result = request_with_retry(
            lambda m=metrics: upload_metrics(m),
            description="上报数据",
        )
        if result:
            gpu_info = ""
            if metrics["gpus"]:
                gpu_info = f" | GPU: {len(metrics['gpus'])} 卡"
            print(f"[{now()}] 上报成功 | "
                  f"CPU: {metrics['cpu_pct']}% | "
                  f"内存: {metrics['mem_pct']}% | "
                  f"磁盘: {metrics['disk_pct']}%"
                  f"{gpu_info}")

        # 等待上报间隔（可被信号中断）
        for _ in range(REPORT_INTERVAL):
            if not running:
                break
            time.sleep(1)

    print(f"[{now()}] 客户端已停止")


if __name__ == "__main__":
    main()
