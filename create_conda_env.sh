#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")

# Locate conda from user's bashrc
CONDA_SH=$(grep -oP '(?<=source ")[^"]*conda\.sh(?=")' "$REAL_HOME/.bashrc" 2>/dev/null || true)
if [[ -z "$CONDA_SH" ]]; then
    CONDA_SH=$(find "$REAL_HOME" -maxdepth 3 -name "conda.sh" -path "*/etc/profile.d/*" 2>/dev/null | head -1 || true)
fi
if [[ -n "$CONDA_SH" && -f "$CONDA_SH" ]]; then
    source "$CONDA_SH"
else
    echo "[ERROR] Cannot find conda installation. Run setup_server.sh first."
    exit 1
fi

read -rp "Enter environment name [test]: " ENV_NAME
ENV_NAME="${ENV_NAME:-test}"

read -rp "Enter Python version [3.12]: " PYTHON_VER
PYTHON_VER="${PYTHON_VER:-3.12}"

# ---------- Conda Tsinghua Mirror ----------
info "Configuring conda Tsinghua mirror for $REAL_USER..."
cat > "$REAL_HOME/.condarc" << 'EOF'
channels:
  - defaults
show_channel_urls: true
default_channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  pytorch: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
EOF
[[ -n "${SUDO_USER:-}" ]] && chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.condarc"
info "Conda mirror configured."

# ---------- Pip Tsinghua Mirror ----------
info "Configuring pip Tsinghua mirror for $REAL_USER..."
mkdir -p "$REAL_HOME/.pip"
cat > "$REAL_HOME/.pip/pip.conf" << 'EOF'
[global]
index-url = https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
EOF
[[ -n "${SUDO_USER:-}" ]] && chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.pip"
info "Pip mirror configured."

# ---------- Create environment ----------
if conda env list | grep -q "^$ENV_NAME "; then
    warn "Environment '$ENV_NAME' already exists, skipping creation."
else
    info "Creating conda environment '$ENV_NAME' with Python $PYTHON_VER ..."
    conda create -n "$ENV_NAME" python="$PYTHON_VER" -y
fi

# ---------- Activate & Install PyTorch ----------
info "Activating environment '$ENV_NAME'..."

conda activate "$ENV_NAME"

info "Installing PyTorch ..."
pip install torch

echo ""
info "Done! Environment '$ENV_NAME' is ready."
