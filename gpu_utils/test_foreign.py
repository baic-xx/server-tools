"""Quick test: occupy GPU 4 for 60s to verify gpu_test.py foreign process detection."""
import torch
import time

device = torch.device("cuda:6")
a = torch.randn(4096, 4096, device=device)
print(f"GPU 6 occupied (PID: {__import__('os').getpid()}), holding for 20s...")
start = time.time()
while time.time() - start < 20:
    a = a @ a
    time.sleep(1)
print("Done.")
