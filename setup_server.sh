#!/bin/bash
set -euo pipefail

CUDA_IMAGE="nvidia/cuda:12.4.1-runtime-ubuntu22.04"
SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIN3Yrj48KDj6b/6wiAmn5BDTmgv+AyNdhJRbW7CIIvDY xx-baic@xx-baic"
MONITOR_SERVER_URL="http://120.209.217.11:30252"

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

# Both root and the login user get configured
USERS_HOME=("/root")
[[ "$REAL_HOME" != "/root" ]] && USERS_HOME+=("$REAL_HOME")

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---------- Password ----------
change_password() {
    read -rp "Change password? [y/N] " choice
    if [[ "${choice,,}" == "y" ]]; then
        read -rp "Which user? [$REAL_USER] " target
        target="${target:-$REAL_USER}"
        passwd "$target"
        info "Password changed for $target."
    else
        info "Skipped password change."
    fi
}

# ---------- SSH Key ----------
setup_ssh_key() {
    for home in "${USERS_HOME[@]}"; do
        local ssh_dir="$home/.ssh"
        local auth_file="$ssh_dir/authorized_keys"

        mkdir -p "$ssh_dir"
        chmod 700 "$ssh_dir"

        if [[ -f "$auth_file" ]] && grep -qF "$SSH_KEY" "$auth_file"; then
            info "SSH key already exists in $auth_file"
            continue
        fi

        echo "$SSH_KEY" >> "$auth_file"
        chmod 600 "$auth_file"
        [[ -n "${SUDO_USER:-}" ]] && chown -R "$(stat -c '%U:%G' "$home")" "$ssh_dir"
        info "SSH key added to $auth_file"
    done
}

# ---------- Miniconda ----------
install_miniconda() {
    info "Updating system packages..."
    sudo apt update -qq && sudo apt install -y -qq git ca-certificates
    if command -v conda &>/dev/null; then
        warn "conda is already installed: $(conda --version)"
        read -rp "Reinstall? [y/N] " choice
        [[ "${choice,,}" != "y" ]] && return
    fi

    CONDA_DIR="$REAL_HOME/miniconda3"

    if [[ -d "$CONDA_DIR" && -x "$CONDA_DIR/bin/conda" ]]; then
        warn "Found existing installation at $CONDA_DIR"
        read -rp "Use this installation and initialize only? [Y/n] " choice
        if [[ "${choice,,}" != "n" ]]; then
            source "$CONDA_DIR/bin/activate"
            sudo -u "$REAL_USER" bash -c "source '$CONDA_DIR/bin/activate' && conda init --all"
            info "conda initialized for $REAL_USER. Run 'source ~/.bashrc' to activate."
            return
            info "conda initialized. Run 'source ~/.bashrc' to activate."
            return
        fi
    fi

    info "Downloading Miniconda installer..."
    INSTALLER="/tmp/Miniconda3-latest-Linux-x86_64.sh"
    wget -q -O "$INSTALLER" https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

    info "Installing Miniconda to $CONDA_DIR ..."
    bash "$INSTALLER" -b -p "$CONDA_DIR"
    rm -f "$INSTALLER"

    eval "$("$CONDA_DIR/bin/conda" shell.bash hook)"
    source "$CONDA_DIR/bin/activate"
    sudo -u "$REAL_USER" bash -c "source '$CONDA_DIR/bin/activate' && conda init --all"
    info "Miniconda installed and conda initialized. Run 'source ~/.bashrc' to activate."
}

# ---------- Docker & CUDA image ----------
pull_cuda_image() {
    if ! command -v docker &>/dev/null; then
        warn "docker is not installed. Skipping image pull."
        warn "Install Docker first: https://docs.docker.com/engine/install/"
        return
    fi

    info "Docker found: $(docker --version)"
    info "Pulling image $CUDA_IMAGE ..."
    docker pull "$CUDA_IMAGE"
    info "Image $CUDA_IMAGE is ready."
}

# ---------- Monitor Client ----------
setup_monitor_client() {
    info "Setting up monitor client..."

    # 安装依赖（用 conda 的 Python）
    local CONDA_PYTHON="$REAL_HOME/miniconda3/bin/python"
    if [[ ! -f "$CONDA_PYTHON" ]]; then
        warn "conda python not found at $CONDA_PYTHON, skipping monitor client."
        return
    fi
    sudo -u "$REAL_USER" "$CONDA_PYTHON" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple psutil requests

    # 部署客户端脚本
    local MONITOR_DIR="/opt/server-monitor"
    local SCRIPT_SOURCE
    SCRIPT_SOURCE="$(cd "$(dirname "$0")" && pwd)/monitor/client/monitor_client.py"

    if [[ ! -f "$SCRIPT_SOURCE" ]]; then
        warn "monitor_client.py not found at $SCRIPT_SOURCE, skipping."
        return
    fi

    mkdir -p "$MONITOR_DIR"
    cp "$SCRIPT_SOURCE" "$MONITOR_DIR/"
    info "Client script copied to $MONITOR_DIR/"

    # 配置 systemd 服务
    cat > /etc/systemd/system/server-monitor.service << EOF
[Unit]
Description=服务器监控客户端
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
ExecStart=$CONDA_PYTHON ${MONITOR_DIR}/monitor_client.py --server ${MONITOR_SERVER_URL}
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable server-monitor
    systemctl restart server-monitor

    info "Monitor client started (reporting to ${MONITOR_SERVER_URL})"
    info "  systemctl status server-monitor  # 查看状态"
    info "  journalctl -u server-monitor -f  # 查看日志"
}

# ---------- Main ----------
echo "=========================================="
echo "       Server One-Click Setup"
echo "=========================================="
echo ""

change_password
echo ""
setup_ssh_key
echo ""
install_miniconda
echo ""
setup_monitor_client
echo ""
# pull_cuda_image

echo ""
echo "=========================================="
echo "  All done!"
echo "  Run 'source ~/.bashrc' to activate conda."
echo "=========================================="
