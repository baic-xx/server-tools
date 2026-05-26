"""GPU log analyzer - summarize utilization from JSONL log files.

Usage:
  # Summarize entire log
  python3 gpu_summary.py gpu_log_20260525_132307.json

  # Summarize a time range
  python3 gpu_summary.py gpu_log_20260525_132307.json --from "2026-05-25 13:23:00" --to "2026-05-25 13:30:00"

  # Only show specific GPUs
  python3 gpu_summary.py gpu_log_20260525_132307.json --gpus 0,1,2,3

Options:
  --from    Start time (default: first record)
  --to      End time (default: last record)
  --gpus    Comma-separated GPU IDs to filter (default: all)
"""

import json
import sys
import argparse
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description="GPU log analyzer")
    parser.add_argument("logfile", help="JSONL log file path")
    parser.add_argument("--from", dest="start_time", default=None, help="Start time YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--to", dest="end_time", default=None, help="End time YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--gpus", type=str, default=None, help="Comma-separated GPU IDs (default: all)")
    return parser.parse_args()


def load_records(path, start_time, end_time):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            ts = datetime.strptime(rec["timestamp"], "%Y-%m-%d %H:%M:%S")
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue
            records.append(rec)
    return records


def summarize(records, gpu_filter):
    if not records:
        print("No records found.")
        return

    first_ts = records[0]["timestamp"]
    last_ts = records[-1]["timestamp"]
    duration = (datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S") -
                datetime.strptime(first_ts, "%Y-%m-%d %H:%M:%S"))

    print(f"=== GPU Utilization Summary ===")
    print(f"Time range: {first_ts} ~ {last_ts} ({duration}")
    print(f"Total records: {len(records)}")
    print()

    # 整体汇总
    avg_compute_all = [r["summary"]["avg_compute_util"] for r in records]
    avg_mem_all = [r["summary"]["total_mem_pct"] for r in records]
    print(f"--- Overall (avg across all GPUs) ---")
    print(f"  Compute: avg={sum(avg_compute_all)/len(avg_compute_all):.1f}%  "
          f"min={min(avg_compute_all):.1f}%  max={max(avg_compute_all):.1f}%")
    print(f"  Memory:  avg={sum(avg_mem_all)/len(avg_mem_all):.1f}%  "
          f"min={min(avg_mem_all):.1f}%  max={max(avg_mem_all):.1f}%")
    print()

    # 逐卡汇总
    # 收集所有 GPU ID
    all_gpu_ids = sorted(set(g["gpu_id"] for r in records for g in r["gpus"]))
    if gpu_filter:
        all_gpu_ids = [gid for gid in all_gpu_ids if gid in gpu_filter]

    print(f"--- Per GPU ---")
    print(f"  {'GPU':>4} | {'Compute':>28} | {'MemUtil':>28} | {'Mem(MB)':>21} | {'Temp':>14} | {'Power':>14}")
    print(f"  {'':>4} | {'avg':>7} {'min':>7} {'max':>7} | {'avg':>7} {'min':>7} {'max':>7} | {'avg':>7} {'min':>7} {'max':>7} | {'avg':>5} {'max':>5} | {'avg':>7} {'max':>7}")
    print(f"  {'':->4}-+-{'':->28}-+-{'':->28}-+-{'':->21}-+-{'':->14}-+-{'':->14}")

    for gid in all_gpu_ids:
        compute_list = []
        mem_util_list = []
        mem_used_list = []
        temp_list = []
        power_list = []
        for r in records:
            for g in r["gpus"]:
                if g["gpu_id"] == gid:
                    compute_list.append(g["compute_util"])
                    mem_util_list.append(g["mem_util"])
                    mem_used_list.append(g["mem_used_mb"])
                    temp_list.append(g["temp_c"])
                    power_list.append(g["power_w"])

        n = len(compute_list)
        if n == 0:
            continue

        print(f"  {gid:>4} | "
              f"{sum(compute_list)/n:>6.1f}% {min(compute_list):>6}% {max(compute_list):>6}% | "
              f"{sum(mem_util_list)/n:>6.1f}% {min(mem_util_list):>6}% {max(mem_util_list):>6}% | "
              f"{sum(mem_used_list)/n:>7.0f} {min(mem_used_list):>7} {max(mem_used_list):>7} | "
              f"{sum(temp_list)/n:>5.0f} {max(temp_list):>5} | "
              f"{sum(power_list)/n:>6.1f} {max(power_list):>6.1f}")

    print()

    # 利用率分布（每卡 compute 在各区间占比）
    print(f"--- Compute Distribution ---")
    brackets = [(0, 0), (1, 25), (26, 50), (51, 75), (76, 100)]
    for gid in all_gpu_ids:
        vals = []
        for r in records:
            for g in r["gpus"]:
                if g["gpu_id"] == gid:
                    vals.append(g["compute_util"])
        if not vals:
            continue
        dist = []
        for lo, hi in brackets:
            pct = sum(1 for v in vals if lo <= v <= hi) / len(vals) * 100
            dist.append(f"{lo:>3}-{hi:>3}%: {pct:>5.1f}%")
        print(f"  GPU {gid}: {' | '.join(dist)}")


def main():
    args = parse_args()

    start_time = None
    end_time = None
    if args.start_time:
        start_time = datetime.strptime(args.start_time, "%Y-%m-%d %H:%M:%S")
    if args.end_time:
        end_time = datetime.strptime(args.end_time, "%Y-%m-%d %H:%M:%S")

    gpu_filter = None
    if args.gpus:
        gpu_filter = set(int(x) for x in args.gpus.split(","))

    records = load_records(args.logfile, start_time, end_time)
    summarize(records, gpu_filter)


if __name__ == "__main__":
    main()
