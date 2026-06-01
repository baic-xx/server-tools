#!/usr/bin/env bash
# 服务器监控客户端一键安装脚本
# 使用方式: curl -sL <URL>/install.sh | bash -s -- --server http://your-server:30252

set -euo pipefail

# ─── 颜色 ───
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ─── 参数解析 ───
SERVER_URL=""
INSTALL_DIR="/opt/server-monitor"
SERVICE_NAME="server-monitor"

usage() {
    echo "用法: $0 --server <URL> [--dir <安装目录>]"
    echo ""
    echo "选项:"
    echo "  --server   监控服务端地址（必填，如 http://10.0.0.1:30252）"
    echo "  --dir      安装目录（默认 /opt/server-monitor）"
    echo "  -h         显示帮助"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) SERVER_URL="$2"; shift 2 ;;
        --dir)    INSTALL_DIR="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) error "未知参数: $1" ;;
    esac
done

[[ -z "$SERVER_URL" ]] && error "请指定 --server 参数，如: $0 --server http://10.0.0.1:30252"

# ─── 检查环境 ───
info "检查运行环境..."

[[ "$(id -u)" -ne 0 ]] && error "请以 root 用户运行此脚本"

if ! command -v python3 &>/dev/null; then
    info "安装 Python3..."
    apt-get update -qq && apt-get install -y -qq python3 python3-pip
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Python 版本: $PYTHON_VERSION"

# ─── 安装依赖 ───
info "安装 Python 依赖..."
pip3 install --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple psutil requests 2>/dev/null || \
    pip3 install --quiet psutil requests

# ─── 部署客户端 ───
info "部署客户端到 $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp "$(dirname "$0")/monitor_client.py" "$INSTALL_DIR/"

# ─── 配置 systemd ───
info "配置 systemd 服务..."

cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=服务器监控客户端
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/monitor_client.py --server ${SERVER_URL}
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}

info "安装完成！"
info ""
info "常用命令:"
info "  systemctl status ${SERVICE_NAME}   # 查看状态"
info "  journalctl -u ${SERVICE_NAME} -f   # 查看日志"
info "  systemctl stop ${SERVICE_NAME}      # 停止"
info "  systemctl restart ${SERVICE_NAME}   # 重启"
