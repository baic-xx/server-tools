#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
    echo "用法: $0 <任务>"
    echo ""
    echo "任务:"
    echo "  deploy    首次部署（服务器配置 + conda 环境 + 启动定时任务）"
    echo "  update    仅更新（停掉旧 run.sh 并重启）"
    echo ""
    echo "示例:"
    echo "  $0 deploy    # 第一次部署，跑全部流程"
    echo "  $0 update    # 只重启定时任务"
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

TASK="$1"

case "$TASK" in
    deploy|update) ;;
    *)
        echo "错误: 未知任务 '$TASK'"
        usage
        exit 1
        ;;
esac

echo "=========================================="
echo "  任务: $TASK"
echo "=========================================="
echo ""

# ── 停掉旧的 run.sh（cleanup handler 会自动停掉 gpu_test.py） ──
stop_old_run() {
    # 1) 找 run.sh 进程（排除 deploy 自身）
    local run_pids
    run_pids=$(ps -eo pid,args | grep "[b]ash.*run\.sh" | grep -v deploy | awk '{print $1}') || true

    if [[ -n "$run_pids" ]]; then
        echo "[INFO] 发现旧的 run.sh 进程: $run_pids"
        # 先 SIGTERM，让 cleanup handler 停 gpu_test
        for pid in $run_pids; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 3
        # 还没死就 SIGKILL
        for pid in $run_pids; do
            if kill -0 "$pid" 2>/dev/null; then
                echo "[WARN] PID $pid 未退出，强制终止"
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
        echo "[INFO] 旧 run.sh 已停止"
    else
        echo "[INFO] 未发现旧的 run.sh 进程"
    fi

    # 2) 安全网：清理残留的 gpu_test.py（SIGKILL run.sh 时 cleanup 来不及跑）
    local gpu_pids
    gpu_pids=$(ps -eo pid,args | grep "[p]ython.*Depth-Anything-3" | awk '{print $1}') || true
    if [[ -n "$gpu_pids" ]]; then
        echo "[INFO] 清理残留 gpu_test 进程: $gpu_pids"
        for pid in $gpu_pids; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 1
        for pid in $gpu_pids; do
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
    fi
}

if [[ "$TASK" == "deploy" ]]; then
    # 1. 服务器配置
    echo "[1/3] Running setup_server.sh ..."
    sudo bash "$SCRIPT_DIR/setup_server.sh"
    echo ""

    # 2. 创建 conda 环境
    echo "[2/3] Running create_conda_env.sh ..."
    bash "$SCRIPT_DIR/create_conda_env.sh"
    echo ""
fi

# ── 启动定时任务（deploy 和 update 都会执行） ──
stop_old_run

echo "[INFO] 启动 run.sh ..."
nohup bash "$SCRIPT_DIR/run.sh" > /dev/null 2>&1 &
echo "run.sh started (PID: $!)"
