#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")
USERS_HOME=("/root")
[[ "$REAL_HOME" != "/root" ]] && USERS_HOME+=("$REAL_HOME")

read -rp "Enter environment name [test]: " ENV_NAME
ENV_NAME="${ENV_NAME:-test}"

read -rp "Enter Python version [3.12]: " PYTHON_VER
PYTHON_VER="${PYTHON_VER:-3.12}"

# ---------- Conda Tsinghua Mirror ----------
info "Configuring conda Tsinghua mirror..."
for home in "${USERS_HOME[@]}"; do
    cat > "$home/.condarc" << 'EOF'
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
    [[ -n "${SUDO_USER:-}" && "$home" != "/root" ]] && chown "$(stat -c '%U:%G' "$home")" "$home/.condarc"
    info "Conda mirror configured for $home/.condarc"
done

# ---------- Pip Tsinghua Mirror ----------
info "Configuring pip Tsinghua mirror..."
for home in "${USERS_HOME[@]}"; do
    mkdir -p "$home/.pip"
    cat > "$home/.pip/pip.conf" << 'EOF'
[global]
index-url = https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
EOF
    [[ -n "${SUDO_USER:-}" && "$home" != "/root" ]] && chown -R "$(stat -c '%U:%G' "$home")" "$home/.pip"
    info "Pip mirror configured for $home/.pip/pip.conf"
done

# ---------- Create environment ----------
info "Creating conda environment '$ENV_NAME' with Python $PYTHON_VER ..."
conda create -n "$ENV_NAME" python="$PYTHON_VER" -y

# ---------- Install PyTorch ----------
info "Installing PyTorch (CUDA 12.4) ..."
conda run -n "$ENV_NAME" pip install torch --index-url https://download.pytorch.org/whl/cu124

echo ""
info "Done! Environment '$ENV_NAME' is ready."
info "Activate: conda activate $ENV_NAME"
