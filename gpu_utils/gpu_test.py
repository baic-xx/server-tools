"""GPU stress test - controlled compute & memory utilization.

Usage:
  # Stress GPU 0,1,2,3 with 80% compute, 90% memory for 120s
  python3 gpu_test.py --gpus 0,1,2,3 --compute 80 --mem 90 --duration 120

  # All GPUs, 100% compute, 100% memory, 60s (defaults)
  python3 gpu_test.py

  # Only GPU 0, 50% memory
  python3 gpu_test.py --gpus 0 --mem 50

Options:
  --gpus      Comma-separated GPU IDs, e.g. 0,1,2,3 (default: all)
  --compute   Target compute utilization %% 1-100 (default: 100)
  --mem       Target memory utilization %% 1-100 (default: 100)
  --duration  Stress test duration in seconds (default: 60)
  --cooldown  Seconds to wait after GPU becomes idle before reclaiming (default: 1800)
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
    # 0号卡多占5%显存
    actual_mem_pct = min(mem_pct + 5, 100) if gpu_id == 0 else mem_pct

    while (time.time() - state["start"]) < duration:
        # 阶段1：正常占用
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
            # 检测外部进程（读共享状态，无开销）
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

        # 释放显存
        del mem_tensors, a, b
        torch.cuda.empty_cache()

        if not foreign_found:
            break

        # 阶段2：等待外部进程离开
        print(f"GPU {gpu_id}: waiting for foreign process to leave...")
        last_foreign_logged = "waiting"
        while (time.time() - state["start"]) < duration:
            time.sleep(5)
            foreign_pids = state["foreign"].get(gpu_id, set())
            if not foreign_pids:
                break

        # 阶段3：冷却期
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
    parser = argparse.ArgumentParser(description="GPU stress test")
    parser.add_argument("--gpus", type=str, default=None,
                        help="Comma-separated GPU IDs, e.g. 0,1,2,3 (default: all)")
    parser.add_argument("--duration", type=int, default=60,
                        help="Stress test duration in seconds (default: 60)")
    parser.add_argument("--compute", type=int, default=100,
                        help="Target compute utilization %% (default: 100)")
    parser.add_argument("--mem", type=int, default=100,
                        help="Target memory utilization %% 1-100 (default: 100)")
    parser.add_argument("--cooldown", type=int, default=1800,
                        help="Seconds to wait after GPU idle before reclaiming (default: 1800)")
    args = parser.parse_args()

    if not 1 <= args.compute <= 100:
        print("--compute must be between 1 and 100")
        sys.exit(1)
    if not 1 <= args.mem <= 100:
        print("--mem must be between 1 and 100")
        sys.exit(1)

    if args.gpus:
        gpu_ids = [int(x) for x in args.gpus.split(",")]
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

    print(f"Stressing GPU(s) {gpu_ids} for {args.duration}s (compute={args.compute}%, mem={args.mem}%, cooldown={args.cooldown}s)...")
    print(f"PID: {my_pid}")
    print("Run `watch -n 1 nvidia-smi` in another terminal to monitor.\n")

    # 启动后台监控线程（只一个，每10秒查一次 nvidia-smi）
    mon = threading.Thread(target=monitor_thread, args=(my_pid, state), daemon=True)
    mon.start()

    threads = []
    for gid in gpu_ids:
        t = threading.Thread(
            target=stress_gpu,
            args=(gid, 8192, args.duration, args.compute, args.mem, args.cooldown, state),
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
