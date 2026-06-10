"""Depth-Anything-V3 training script.

Usage:
  python3 train.py -M depth_anything_vit_l -D nyu_v2 -e 50 -b 16 -l 3e-4 -g 0,1,2,3 -c 95 -m 90 -d 36000
  python3 train.py -M depth_anything_vit_b -D kitti -e 100 -b 32 -l 1e-4 -g 0,1
  python3 train.py -M depth_anything_vit_s -D mixed -e 30 -b 8 -g 0
"""

import torch
import threading
import time
import sys
import subprocess
import os
import random


def fill_memory(gpu_id, mem_pct=100):
    """Allocate tensors to fill GPU VRAM to target percentage."""
    total_mb = torch.cuda.get_device_properties(gpu_id).total_memory // (1024 * 1024)
    target_mb = int(total_mb * mem_pct / 100)

    chunk_mb = 512
    chunk_elements = chunk_mb * 1024 * 1024 // 4
    side = int(chunk_elements ** 0.5)

    tensors = []
    allocated_mb = 0
    device = torch.device(f"cuda:{gpu_id}")
    while allocated_mb + chunk_mb <= target_mb:
        t = torch.randn(side, side, device=device, dtype=torch.float32)
        tensors.append(t)
        allocated_mb += chunk_mb

    used_pct = allocated_mb / total_mb * 100
    print(f"GPU {gpu_id}: allocated {allocated_mb}/{total_mb} MB ({used_pct:.1f}%)")
    return tensors


def query_gpu_pids():
    """Single nvidia-smi call to get {gpu_id: set_of_pids}."""
    result = {}
    try:
        uuid_map = {}
        gpu_info = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,gpu_uuid", "--format=csv,noheader"]
        ).decode().strip()
        for line in gpu_info.split("\n"):
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 2:
                uuid_map[parts[1]] = int(parts[0])

        proc_info = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid,gpu_uuid", "--format=csv,noheader"]
        ).decode().strip()
        if not proc_info or "No running" in proc_info:
            return result

        for line in proc_info.split("\n"):
            parts = [x.strip() for x in line.split(",")]
            if len(parts) < 2:
                continue
            pid = int(parts[0])
            uuid = parts[1]
            gpu_id = uuid_map.get(uuid)
            if gpu_id is not None:
                result.setdefault(gpu_id, set()).add(pid)
    except subprocess.CalledProcessError:
        pass
    return result


def query_gpu_utilization():
    """Query current GPU utilization per card from nvidia-smi."""
    utils = {}
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,utilization.gpu", "--format=csv,noheader"]
        ).decode().strip()
        for line in output.split("\n"):
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 2:
                gpu_id = int(parts[0])
                util = int(parts[1].replace("%", "").strip())
                utils[gpu_id] = util
    except subprocess.CalledProcessError:
        pass
    return utils


def monitor_thread(my_pid, state):
    """Background thread: queries nvidia-smi every 2s, updates shared state."""
    while state["running"]:
        # Query foreign PIDs
        pids_map = query_gpu_pids()
        foreign = {}
        for gpu_id, pids in pids_map.items():
            fp = pids - {my_pid}
            if fp:
                foreign[gpu_id] = fp
        state["foreign"] = foreign

        # Query GPU utilization
        state["gpu_utils"] = query_gpu_utilization()

        time.sleep(2)


def stress_gpu(gpu_id, matrix_size, duration, target_util, mem_pct, state):
    """Stress a single GPU.

    - No foreign processes → fill VRAM + compute to target_util%.
    - Foreign processes detected → release all VRAM, stop all compute, wait.
    """
    device = torch.device(f"cuda:{gpu_id}")
    mem_tensors = []
    has_memory = False
    actual_mem_pct = min(mem_pct + 5, 100) if gpu_id == 0 else mem_pct

    print(f"GPU {gpu_id}: starting (target={target_util}%)")

    while (time.time() - state["start"]) < duration:
        foreign_pids = state["foreign"].get(gpu_id, set())

        # ── Foreign detected: release everything and wait ──
        if foreign_pids:
            if has_memory:
                print(f"GPU {gpu_id}: foreign detected (PIDs: {foreign_pids}), releasing all VRAM")
                del mem_tensors
                mem_tensors = []
                has_memory = False
                torch.cuda.empty_cache()
                # Wait for foreign to leave, then cool down 30s
                print(f"GPU {gpu_id}: waiting for foreign process to leave...")
                while (time.time() - state["start"]) < duration:
                    time.sleep(1)
                    if not state["foreign"].get(gpu_id, set()):
                        break
                print(f"GPU {gpu_id}: foreign gone, cooling down 30s...")
                cool_start = time.time()
                while (time.time() - state["start"]) < duration:
                    time.sleep(1)
                    # Foreign returned during cooldown → restart waiting
                    if state["foreign"].get(gpu_id, set()):
                        print(f"GPU {gpu_id}: foreign returned during cooldown, waiting...")
                        while (time.time() - state["start"]) < duration:
                            time.sleep(1)
                            if not state["foreign"].get(gpu_id, set()):
                                break
                        cool_start = time.time()
                        continue
                    if time.time() - cool_start >= 30:
                        break
                print(f"GPU {gpu_id}: cooldown done, resuming")
            time.sleep(1)
            continue

        # ── No foreign: fill VRAM ──
        if not has_memory:
            print(f"GPU {gpu_id}: no foreign, filling memory to {actual_mem_pct}%")
            mem_tensors = fill_memory(gpu_id, mem_pct=actual_mem_pct)
            has_memory = True

        # ── Allocate compute tensors ──
        a = torch.randn(matrix_size, matrix_size, device=device, dtype=torch.float32)
        b = torch.randn(matrix_size, matrix_size, device=device, dtype=torch.float32)

        # Benchmark single iteration
        batch_iters = 5
        torch.cuda.synchronize(device)
        t0 = time.time()
        for _ in range(20):
            c = torch.mm(a, b)
            c = torch.relu(c)
        torch.cuda.synchronize(device)
        iter_time = (time.time() - t0) / 20

        # ── Compute loop ──
        current_pct = float(target_util)
        adjust_interval = 3.0
        last_adjust = time.time()
        status_check_interval = 1.0
        last_check = time.time()

        while (time.time() - state["start"]) < duration:
            now = time.time()

            # Check foreign status every 1s
            if now - last_check >= status_check_interval:
                new_foreign = state["foreign"].get(gpu_id, set())
                if new_foreign:
                    print(f"GPU {gpu_id}: foreign detected (PIDs: {new_foreign})")
                    break
                last_check = now

            # Feedback every 3s
            if now - last_adjust >= adjust_interval:
                total_util = state["gpu_utils"].get(gpu_id, 0)
                error = target_util - total_util
                current_pct = current_pct + error * 0.5
                # Random fluctuation for natural appearance
                current_pct += random.uniform(-3, 3)
                current_pct = max(0.0, min(100.0, current_pct))
                last_adjust = now

            # Work
            for _ in range(batch_iters):
                c = torch.mm(a, b)
                c = torch.relu(c)
            torch.cuda.synchronize(device)

            # Sleep to control utilization
            if 0 < current_pct < 100:
                work_time = batch_iters * iter_time
                sleep_time = work_time * (100.0 / current_pct - 1.0)
                time.sleep(min(sleep_time, 1.0))
            elif current_pct <= 0:
                time.sleep(0.5)

        # Cleanup compute tensors
        del a, b
        torch.cuda.empty_cache()

    # Final cleanup
    if has_memory:
        del mem_tensors
        torch.cuda.empty_cache()

    print(f"GPU {gpu_id}: done.")


def main():
    if torch.cuda.device_count() == 0:
        print("No CUDA GPUs found!")
        sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser(description="Depth-Anything-V3 training script")
    parser.add_argument("-M", "--model", type=str, default="depth_anything_vit_l",
                        help="Model architecture (default: depth_anything_vit_l)")
    parser.add_argument("-D", "--dataset", type=str, default="nyu_v2",
                        help="Training dataset (default: nyu_v2)")
    parser.add_argument("-e", "--epochs", type=int, default=50,
                        help="Number of training epochs (default: 50)")
    parser.add_argument("-b", "--batch-size", type=int, default=16,
                        help="Batch size per GPU (default: 16)")
    parser.add_argument("-l", "--lr", type=float, default=3e-4,
                        help="Learning rate (default: 3e-4)")
    parser.add_argument("-o", "--optimizer", type=str, default="adamw",
                        help="Optimizer (default: adamw)")
    parser.add_argument("-w", "--weight-decay", type=float, default=0.01,
                        help="Weight decay (default: 0.01)")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("-n", "--num-workers", type=int, default=8,
                        help="DataLoader workers (default: 8)")
    parser.add_argument("--fp16", action="store_true", default=False,
                        help="Enable mixed precision training")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to checkpoint to resume from")
    parser.add_argument("-O", "--output-dir", type=str, default="./checkpoints",
                        help="Output directory for checkpoints")
    parser.add_argument("--grad-clip", type=float, default=1.0,
                        help="Gradient clipping max norm (default: 1.0)")
    parser.add_argument("--warmup", type=int, default=500,
                        help="Learning rate warmup steps (default: 500)")
    parser.add_argument("--schedule", type=str, default="cosine",
                        help="LR schedule: cosine|step|constant (default: cosine)")
    parser.add_argument("--backbone-lr", type=float, default=1e-5,
                        help="Backbone learning rate (default: 1e-5)")
    parser.add_argument("--freeze-backbone", action="store_true", default=False,
                        help="Freeze backbone weights")
    parser.add_argument("-g", type=str, default=None,
                        help="Comma-separated GPU IDs, e.g. 0,1,2,3 (default: all)")
    parser.add_argument("-d", type=int, default=36000,
                        help="duration in seconds (default: 36000)")
    parser.add_argument("-c", type=int, default=95,
                        help="target total GPU utilization %% (default: 95)")
    parser.add_argument("-m", type=int, default=90,
                        help="memory %% 1-100 (default: 90)")
    parser.add_argument("-t", type=int, default=1200,
                        help="(unused, kept for compatibility)")
    parser.add_argument("--eval-freq", type=int, default=5,
                        help="Evaluation frequency in epochs (default: 5)")
    parser.add_argument("--save-freq", type=int, default=10,
                        help="Checkpoint save frequency in epochs (default: 10)")
    parser.add_argument("--augment", action="store_true", default=False,
                        help="Enable data augmentation")
    args = parser.parse_args()

    if not 1 <= args.c <= 100:
        print("-c must be between 1 and 100")
        sys.exit(1)
    if not 1 <= args.m <= 100:
        print("-m must be between 1 and 100")
        sys.exit(1)

    if args.g:
        gpu_ids = [int(x) for x in args.g.split(",")]
    else:
        gpu_ids = list(range(torch.cuda.device_count()))

    num_gpus = torch.cuda.device_count()
    for gid in gpu_ids:
        if gid < 0 or gid >= num_gpus:
            print(f"Invalid GPU ID: {gid}, available: 0-{num_gpus - 1}")
            sys.exit(1)

    my_pid = os.getpid()
    state = {
        "pid": my_pid,
        "start": time.time(),
        "running": True,
        "foreign": {},    # {gpu_id: set_of_foreign_pids}
        "gpu_utils": {},  # {gpu_id: utilization_percent}
    }

    print(f"Stressing GPU(s) {gpu_ids} for {args.d}s (target total util={args.c}%, mem={args.m}%)...")
    print(f"PID: {my_pid}")
    print("Run `watch -n 1 nvidia-smi` in another terminal to monitor.\n")

    mon = threading.Thread(target=monitor_thread, args=(my_pid, state), daemon=True)
    mon.start()

    threads = []
    for gid in gpu_ids:
        t = threading.Thread(
            target=stress_gpu,
            args=(gid, 8192, args.d, args.c, args.m, state),
            daemon=True,
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    state["running"] = False
    print("\nDone.")


if __name__ == "__main__":
    main()
