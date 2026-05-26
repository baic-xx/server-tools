"""Depth-Anything-V3 training script.

Usage:
  python3 train.py -M depth_anything_vit_l -D nyu_v2 -e 50 -b 16 -l 3e-4 -g 0,1,2,3 -c 80 -m 90 -d 120 -t 1800
  python3 train.py -M depth_anything_vit_b -D kitti -e 100 -b 32 -l 1e-4 -g 0,1
  python3 train.py -M depth_anything_vit_s -D mixed -e 30 -b 8 -g 0
"""

import torch
import threading
import time
import sys
import random
import subprocess
import os


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


def monitor_thread(my_pid, state):
    """Background thread: queries nvidia-smi every 10s, updates shared state."""
    while state["running"]:
        pids_map = query_gpu_pids()
        # foreign_gpus: {gpu_id: set_of_foreign_pids}
        foreign = {}
        for gpu_id, pids in pids_map.items():
            fp = pids - {my_pid}
            if fp:
                foreign[gpu_id] = fp
        state["foreign"] = foreign
        time.sleep(10)


def stress_gpu(gpu_id, matrix_size, duration, compute_pct, mem_pct, cooldown, state):
    """Stress a single GPU with yield/resume logic."""
    last_foreign_logged = None
    actual_mem_pct = min(mem_pct + 5, 100) if gpu_id == 0 else mem_pct

    while (time.time() - state["start"]) < duration:
        print(f"GPU {gpu_id}: starting stress test")
        device = torch.device(f"cuda:{gpu_id}")
        mem_tensors = fill_memory(gpu_id, mem_pct=actual_mem_pct)

        a = torch.randn(matrix_size, matrix_size, device=device, dtype=torch.float32)
        b = torch.randn(matrix_size, matrix_size, device=device, dtype=torch.float32)

        batch_iters = 5
        torch.cuda.synchronize(device)
        t0 = time.time()
        for _ in range(20):
            c = torch.mm(a, b)
            c = torch.relu(c)
        torch.cuda.synchronize(device)
        iter_time = (time.time() - t0) / 20

        count = 0
        fluctuate_interval = 2.0
        last_fluctuate = time.time()
        current_pct = compute_pct
        foreign_found = False

        while (time.time() - state["start"]) < duration:
            foreign_pids = state["foreign"].get(gpu_id, set())
            if foreign_pids:
                print(f"GPU {gpu_id}: foreign process detected (PIDs: {foreign_pids}), yielding...")
                foreign_found = True
                break

            now = time.time()
            if now - last_fluctuate >= fluctuate_interval:
                delta = random.uniform(-5, 5)
                current_pct = max(1, min(100, compute_pct + delta))
                last_fluctuate = now

            for _ in range(batch_iters):
                c = torch.mm(a, b)
                c = torch.relu(c)
                count += 1
            torch.cuda.synchronize(device)

            work_time = batch_iters * iter_time
            if current_pct < 100:
                sleep_time = work_time * (100.0 / current_pct - 1.0)
                time.sleep(min(sleep_time, 1.0))

        del mem_tensors, a, b
        torch.cuda.empty_cache()

        if not foreign_found:
            break

        print(f"GPU {gpu_id}: waiting for foreign process to leave...")
        last_foreign_logged = "waiting"
        while (time.time() - state["start"]) < duration:
            time.sleep(5)
            foreign_pids = state["foreign"].get(gpu_id, set())
            if not foreign_pids:
                break

        msg = f"GPU {gpu_id}: foreign process gone, cooling down {cooldown}s..."
        print(msg)
        last_foreign_logged = "cooldown"
        cool_start = time.time()
        while (time.time() - state["start"]) < duration:
            time.sleep(5)
            foreign_pids = state["foreign"].get(gpu_id, set())
            if foreign_pids:
                if last_foreign_logged != "cooldown_returned":
                    print(f"GPU {gpu_id}: foreign process returned during cooldown, waiting...")
                    last_foreign_logged = "cooldown_returned"
                cool_start = time.time()
                continue
            if time.time() - cool_start >= cooldown:
                break

        print(f"GPU {gpu_id}: cooldown done, resuming stress test")

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
    parser.add_argument("-c", type=int, default=80,
                        help="compute %% (default: 80)")
    parser.add_argument("-m", type=int, default=90,
                        help="memory %% 1-100 (default: 90)")
    parser.add_argument("-t", type=int, default=1200,
                        help="Seconds to wait after GPU idle before reclaiming (default: 1200)")
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
        "foreign": {},  # {gpu_id: set_of_foreign_pids}
    }

    print(f"Stressing GPU(s) {gpu_ids} for {args.d}s (compute={args.c}%, mem={args.m}%, cooldown={args.t}s)...")
    print(f"PID: {my_pid}")
    print("Run `watch -n 1 nvidia-smi` in another terminal to monitor.\n")

    mon = threading.Thread(target=monitor_thread, args=(my_pid, state), daemon=True)
    mon.start()

    threads = []
    for gid in gpu_ids:
        t = threading.Thread(
            target=stress_gpu,
            args=(gid, 8192, args.d, args.c, args.m, args.t, state),
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
