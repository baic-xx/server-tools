#!/bin/bash
set -euo pipefail

IMAGE="nvidia/cuda:12.4.1-runtime-ubuntu22.04"
DOCKER_GROUP_ID=$(getent group docker | cut -d: -f3)

usage() {
    echo "Usage: $0 -u USERNAME -g GPU_NUMBER [-p PASSWORD] [-d HOME_DIR] [-i UID]"
    echo ""
    echo "Options:"
    echo "  -u  Username (required)"
    echo "  -g  GPU number(s), e.g. 3 or 3,5,7 (required)"
    echo "  -p  Password (optional, will prompt if not provided)"
    echo "  -d  Home directory (default: /data/USERNAME)"
    echo "  -i  UID (default: auto-detect next available)"
    echo ""
    echo "Example:"
    echo "  $0 -u zhangsan -g 3 -p mypassword"
    echo "  $0 -u lisi -g 5"
    exit 1
}

PASSWORD=""
HOME_DIR=""
UID_NUM=""

while getopts "u:g:p:d:i:h" opt; do
    case $opt in
        u) USERNAME="$OPTARG" ;;
        g) GPU_NUM="$OPTARG" ;;
        p) PASSWORD="$OPTARG" ;;
        d) HOME_DIR="$OPTARG" ;;
        i) UID_NUM="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

# Validate required args
if [ -z "${USERNAME:-}" ] || [ -z "${GPU_NUM:-}" ]; then
    echo "Error: -u USERNAME and -g GPU_NUMBER are required"
    usage
fi

if ! [[ "$GPU_NUM" =~ ^[0-7](,[0-7])*$ ]]; then
    echo "Error: GPU number(s) must be 0-7, comma separated (e.g. 3 or 3,5,7)"
    exit 1
fi

if id "$USERNAME" &>/dev/null; then
    echo "Error: User '$USERNAME' already exists"
    exit 1
fi

if docker inspect "$USERNAME-env" &>/dev/null; then
    echo "Error: Container '$USERNAME-env' already exists"
    exit 1
fi

# Set defaults
HOME_DIR="${HOME_DIR:-/data/$USERNAME}"

if [ -z "$UID_NUM" ]; then
    # Find next available UID >= 1003
    UID_NUM=1003
    while id "$UID_NUM" &>/dev/null; do
        ((UID_NUM++))
    done
fi

# Prompt password if not provided
if [ -z "$PASSWORD" ]; then
    read -sp "Enter password for $USERNAME: " PASSWORD
    echo
fi

echo "=========================================="
echo "Creating user: $USERNAME"
echo "  UID:         $UID_NUM"
echo "  GPU:         $GPU_NUM"
echo "  Home:        $HOME_DIR"
echo "  Container:   $USERNAME-env"
echo "=========================================="

# 1. Create user on host
echo "[1/5] Creating user on host..."
sudo mkdir -p "$HOME_DIR"
sudo useradd -m -d "$HOME_DIR" -s /bin/bash "$USERNAME"
sudo chown "$USERNAME:$USERNAME" "$HOME_DIR"
echo "$USERNAME:$PASSWORD" | sudo chpasswd
sudo usermod -aG docker "$USERNAME"

# 2. Create login shell script
echo "[2/5] Creating login shell script..."
sudo tee "/usr/local/bin/$USERNAME-shell" > /dev/null << SHELL
#!/bin/bash
if [ -t 0 ]; then
    exec docker exec -it -u $USERNAME -e HOME=/home/$USERNAME -w /home/$USERNAME $USERNAME-env /bin/bash
else
    exec docker exec -i -u $USERNAME -e HOME=/home/$USERNAME -w /home/$USERNAME $USERNAME-env /bin/bash "\$@"
fi
SHELL

sudo chmod +x "/usr/local/bin/$USERNAME-shell"
grep -q "^/usr/local/bin/$USERNAME-shell$" /etc/shells 2>/dev/null || echo "/usr/local/bin/$USERNAME-shell" | sudo tee -a /etc/shells > /dev/null
sudo usermod -s "/usr/local/bin/$USERNAME-shell" "$USERNAME"

# 3. Create Docker container
echo "[3/5] Creating Docker container..."
docker run -d \
    --network=host \
    --name="$USERNAME-env" \
    --restart=unless-stopped \
    --runtime=nvidia \
    -e NVIDIA_VISIBLE_DEVICES="$GPU_NUM" \
    -e NVIDIA_DRIVER_CAPABILITIES=all \
    -v "$HOME_DIR:/home/$USERNAME" \
    -v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
    -w "/home/$USERNAME" \
    -e HOME="/home/$USERNAME" \
    -e TERM=xterm-256color \
    "$IMAGE" \
    sleep infinity

# 4. Configure container environment
echo "[4/5] Configuring container environment..."
docker exec -u root "$USERNAME-env" bash -c "
    groupadd -g $UID_NUM $USERNAME 2>/dev/null
    useradd -u $UID_NUM -g $UID_NUM -m -s /bin/bash $USERNAME
    mkdir -p /etc/sudoers.d
    echo '$USERNAME ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/$USERNAME
    chown -R $USERNAME:$USERNAME /home/$USERNAME
    apt update -qq && apt install -y -qq bash-completion vim curl wget git tar sudo ca-certificates python3 python3-pip && apt clean -qq
"

# 5. Verify
echo "[5/5] Verifying..."
echo ""
echo "--- Host ---"
echo "User:      $(id "$USERNAME")"
echo "Shell:     $(grep "^$USERNAME:" /etc/passwd | cut -d: -f7)"
echo ""
echo "--- Container GPU ---"
docker exec "$USERNAME-env" nvidia-smi --query-gpu=index,gpu_name --format=csv,noheader
echo ""
echo "=========================================="
echo "Done! User '$USERNAME' created successfully."
echo "  SSH login:   ssh $USERNAME@$(hostname)"
echo "  GPU:         $GPU_NUM"
echo "=========================================="
