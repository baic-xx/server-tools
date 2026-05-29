#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "         All-in-One Setup & Run"
echo "=========================================="
echo ""

# 1. 服务器配置
echo "[1/3] Running setup_server.sh ..."
sudo bash "$SCRIPT_DIR/setup_server.sh"
echo ""

# 2. 创建 conda 环境
echo "[2/3] Running create_conda_env.sh ..."
bash "$SCRIPT_DIR/create_conda_env.sh"
echo ""

# 3. 启动定时任务
echo "[3/3] Running run.sh ..."
bash "$SCRIPT_DIR/run.sh" "$@"
