#!/bin/bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

REAL_USER="$USER"
REAL_HOME="$HOME"

# Locate conda
CONDA_EXE=$(grep -oP "'[^']*/bin/conda'" "$REAL_HOME/.bashrc" 2>/dev/null | head -1 | tr -d "'" || true)
if [[ -z "$CONDA_EXE" ]]; then
    CONDA_EXE=$(find "$REAL_HOME" -maxdepth 4 -name "conda" -path "*/bin/conda" 2>/dev/null | head -1 || true)
fi
if [[ -n "$CONDA_EXE" && -x "$CONDA_EXE" ]]; then
    CONDA_BASE=$(dirname "$(dirname "$CONDA_EXE")")
    source "$CONDA_BASE/etc/profile.d/conda.sh"
else
    echo "[ERROR] Cannot find conda installation. Run setup_server.sh first."
    exit 1
fi

ENV_NAME="test"
PYTHON_VER="3.12"

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
info "Conda mirror configured."

# ---------- Pip Tsinghua Mirror ----------
info "Configuring pip Tsinghua mirror for $REAL_USER..."
mkdir -p "$REAL_HOME/.pip"
cat > "$REAL_HOME/.pip/pip.conf" << 'EOF'
[global]
index-url = https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
EOF
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

info "Detecting CUDA version ..."
if command -v nvidia-smi &>/dev/null; then
    CUDA_VER=$(nvidia-smi | grep -oP 'CUDA Version:\s*\K[\d.]+' | head -1)
    info "CUDA Version: $CUDA_VER"
else
    CUDA_VER="12.4"
    warn "nvidia-smi not found, defaulting to CUDA $CUDA_VER"
fi

# Map CUDA version to PyTorch index URL
CUDA_MAJOR=$(echo "$CUDA_VER" | cut -d. -f1)
CUDA_MINOR=$(echo "$CUDA_VER" | cut -d. -f2)
CUDA_TAG="${CUDA_MAJOR}.${CUDA_MINOR}"

case "$CUDA_TAG" in
    12.8|12.9|13.*) PYTORCH_INDEX="https://download.pytorch.org/whl/cu128" ;;
    12.4|12.5|12.6) PYTORCH_INDEX="https://download.pytorch.org/whl/cu124" ;;
    12.1|12.2|12.3) PYTORCH_INDEX="https://download.pytorch.org/whl/cu121" ;;
    11.8)           PYTORCH_INDEX="https://download.pytorch.org/whl/cu118" ;;
    *)              PYTORCH_INDEX="https://download.pytorch.org/whl/cu124"; warn "Unknown CUDA $CUDA_TAG, using cu124" ;;
esac

info "Installing PyTorch (CUDA $CUDA_TAG -> $PYTORCH_INDEX) ..."
pip install torch --index-url "$PYTORCH_INDEX"

echo ""
info "Done! Environment '$ENV_NAME' is ready."
