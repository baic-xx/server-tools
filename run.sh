#!/usr/bin/env bash
#
# 定时执行脚本 - 启动后台任务，等待完成后间隔一段时间再启动
#
# 用法:
#   ./schedule_run.sh                    # 使用默认命令和间隔
#   ./schedule_run.sh -i 600             # 自定义间隔
#   ./schedule_run.sh -c "python ..." -i 1800 -n 5
#
# 参数:
#   -c, --command    要执行的命令（默认为下方的训练命令）
#   -i, --interval   上一轮结束后到下一轮启动的间隔秒数（默认 1800，即 30 分钟）
#   -n, --max-runs   最大执行次数（默认 0，即无限循环）
#       --dry-run    只打印将要执行的命令，不实际运行
#   -h, --help       显示帮助信息

set -euo pipefail

# ── 默认值 ──
COMMAND="nohup python /data/xx/workspace/Depth-Anything-3/src/depth_anything_3/train.py -D nyu_v2 -e 50 -b 16 -l 3e-4 -g 0,1,2,3,6,7 -c 80 -m 40 -d 36000 -t 600 > /dev/null 2>&1 &"
INTERVAL=1800
MAX_RUNS=0
DRY_RUN=false

# ── 参数解析 ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--command)  COMMAND="$2";  shift 2 ;;
        -i|--interval) INTERVAL="$2"; shift 2 ;;
        -n|--max-runs) MAX_RUNS="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=true;  shift ;;
        -h|--help)
            sed -n '3,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

if [[ "$INTERVAL" -lt 1 ]]; then
    echo "错误: 间隔必须为正整数（秒）"
    exit 1
fi

format_duration() {
    local secs=$1
    if (( secs >= 3600 )); then
        printf "%dh%dm" $((secs/3600)) $((secs%3600/60))
    elif (( secs >= 60 )); then
        printf "%dm%ds" $((secs/60)) $((secs%60))
    else
        printf "%ds" "$secs"
    fi
}

INTERVAL_DISPLAY=$(format_duration "$INTERVAL")

echo "=========================================="
echo " 定时执行脚本已启动"
echo " 命令: $COMMAND"
echo " 间隔: $INTERVAL_DISPLAY"
[[ $MAX_RUNS -gt 0 ]] && echo " 次数: $MAX_RUNS"
echo "=========================================="

# ── 优雅退出 ──
RUN_COUNT=0
STOP=false
CURRENT_PID=""

cleanup() {
    echo ""
    echo "[INFO] 收到终止信号，正在停止..."
    STOP=true
    if [[ -n "$CURRENT_PID" ]] && kill -0 "$CURRENT_PID" 2>/dev/null; then
        echo "[INFO] 终止任务 (PID: $CURRENT_PID)..."
        kill "$CURRENT_PID" 2>/dev/null || true
        # 等子进程退出
        wait "$CURRENT_PID" 2>/dev/null || true
    fi
    echo "[INFO] 已执行 $RUN_COUNT 次，退出。"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── 主循环 ──
while true; do
    RUN_COUNT=$((RUN_COUNT + 1))
    START_TIME=$(date +%s)

    echo ""
    echo "[INFO] ═══ 第 ${RUN_COUNT} 次执行 ═══ $(date '+%Y-%m-%d %H:%M:%S')"

    if $DRY_RUN; then
        echo "[DRY-RUN] $COMMAND"
    else
        eval "$COMMAND"
        CURRENT_PID=$!
        echo "[INFO] 已启动 (PID: $CURRENT_PID)"

        # 等待后台任务完成
        while kill -0 "$CURRENT_PID" 2>/dev/null; do
            if $STOP; then exit 0; fi
            ELAPSED_NOW=$(($(date +%s) - START_TIME))
            sleep 10
        done
        echo ""

        wait "$CURRENT_PID"
        EXIT_CODE=$?
        CURRENT_PID=""

        END_TIME=$(date +%s)
        ELAPSED=$((END_TIME - START_TIME))

        if [[ $EXIT_CODE -eq 0 ]]; then
            echo "[INFO] 完成 (耗时 $(format_duration "$ELAPSED"))"
        else
            echo "[WARN] 退出码: $EXIT_CODE (耗时 $(format_duration "$ELAPSED"))"
        fi
    fi

    # 检查执行次数上限
    if [[ $MAX_RUNS -gt 0 && $RUN_COUNT -ge $MAX_RUNS ]]; then
        echo "[INFO] 已达到最大执行次数 ($MAX_RUNS)，退出。"
        break
    fi

    # 等待下一轮
    echo "[INFO] 等待 ${INTERVAL_DISPLAY} 后启动下一次..."
    for ((i=0; i<INTERVAL; i++)); do
        if $STOP; then break 2; fi
        sleep 1
    done
done
