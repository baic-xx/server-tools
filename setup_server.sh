#!/bin/bash
set -euo pipefail

CUDA_IMAGE="nvidia/cuda:12.4.1-runtime-ubuntu22.04"
SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIN3Yrj48KDj6b/6wiAmn5BDTmgv+AyNdhJRbW7CIIvDY xx-baic@xx-baic"

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

    read -rp "Enter Miniconda install path [$REAL_HOME/miniconda3]: " CONDA_DIR
    CONDA_DIR="${CONDA_DIR:-$REAL_HOME/miniconda3}"

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
# pull_cuda_image

echo ""
echo "=========================================="
echo "  All done!"
echo "  Run 'source ~/.bashrc' to activate conda."
echo "=========================================="
