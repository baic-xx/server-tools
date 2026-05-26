"""GPU utilization logger - records usage to JSON every 30 seconds.

Usage:
  # Default: log every 30s to gpu_log_<timestamp>.json
  python3 gpu_monitor.py

  # Custom interval and output
  python3 gpu_monitor.py --interval 10 --output my_log.json

  # Background
  nohup python3 gpu_monitor.py --interval 30 &

  # Press Ctrl+C to stop

Options:
  --interval  Logging interval in seconds (default: 30)
  --output    Output JSON file (default: gpu_log_<timestamp>.json)
"""

import subprocess
import json
import sys
import time
import datetime
import argparse
import signal
import fcntl


def query_gpu_stats():
    """Query nvidia-smi and return per-GPU stats."""
    output = subprocess.check_output([
        "nvidia-smi",
        "--query-gpu=index,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits"
    ]).decode().strip()

    gpus = []
    for line in output.split("\n"):
        parts = [x.strip() for x in line.split(",")]
        gpus.append({
            "gpu_id": int(parts[0]),
            "compute_util": int(parts[1]),
            "mem_util": int(parts[2]),
            "mem_used_mb": int(parts[3]),
            "mem_total_mb": int(parts[4]),
            "temp_c": int(parts[5]),
            "power_w": float(parts[6]),
        })

    summary = {
        "avg_compute_util": round(sum(g["compute_util"] for g in gpus) / len(gpus), 1),
        "total_mem_used_mb": sum(g["mem_used_mb"] for g in gpus),
        "total_mem_total_mb": sum(g["mem_total_mb"] for g in gpus),
        "total_mem_pct": round(sum(g["mem_used_mb"] for g in gpus) / sum(g["mem_total_mb"] for g in gpus) * 100, 1),
    }

    return summary, gpus


def append_record(filepath, record):
    """Append a record as one line to JSONL file."""
    with open(filepath, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description="GPU utilization logger")
    parser.add_argument("--interval", type=int, default=30,
                        help="Logging interval in seconds (default: 30)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file (default: gpu_log_<timestamp>.json)")
    args = parser.parse_args()

    if args.interval < 1:
        print("--interval must be >= 1")
        sys.exit(1)

    output = args.output or f"gpu_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    print(f"Logging to {output} every {args.interval}s (Ctrl+C to stop)\n")

    running = True
    def handle_sigint(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, handle_sigint)

    while running:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            summary, gpus = query_gpu_stats()
        except Exception as e:
            print(f"[{timestamp}] Error: {e}")
            time.sleep(args.interval)
            continue

        record = {
            "timestamp": timestamp,
            "summary": summary,
            "gpus": gpus,
        }
        append_record(output, record)

        # 终端输出
        print(f"[{timestamp}] "
              f"Avg Compute: {summary['avg_compute_util']}% | "
              f"Mem: {summary['total_mem_used_mb']}/{summary['total_mem_total_mb']} MB ({summary['total_mem_pct']}%)")
        for g in gpus:
            print(f"  GPU {g['gpu_id']}: compute {g['compute_util']}%, "
                  f"mem {g['mem_util']}% ({g['mem_used_mb']}/{g['mem_total_mb']} MB), "
                  f"temp {g['temp_c']}C, power {g['power_w']:.0f}W")

        time.sleep(args.interval)

    print(f"\nStopped. Log saved to {output}")


if __name__ == "__main__":
    main()
