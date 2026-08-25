#!/bin/bash
set -euo pipefail

usage() {
	echo "Usage: sudo $0 -u USERNAME"
	echo ""
	echo "Recreates USERNAME-env with Docker socket access so the container user can build images."
	echo "A timestamped backup image is created before the container is stopped."
	echo ""
	echo "Example:"
	echo "  sudo $0 -u wangrh"
	exit 1
}

USERNAME=""

while getopts "u:h" opt; do
	case $opt in
		u) USERNAME="$OPTARG" ;;
		h) usage ;;
		*) usage ;;
	esac
done

if [ -z "$USERNAME" ]; then
	echo "Error: -u USERNAME is required"
	usage
fi

if ! command -v docker &>/dev/null; then
	echo "Error: docker is not installed or is not in PATH"
	exit 1
fi

if [ ! -S /var/run/docker.sock ]; then
	echo "Error: /var/run/docker.sock does not exist"
	exit 1
fi

CONTAINER="$USERNAME-env"

if ! docker inspect "$CONTAINER" &>/dev/null; then
	echo "Error: container '$CONTAINER' does not exist"
	exit 1
fi

if ! docker inspect --format '{{.State.Running}}' "$CONTAINER" | grep -qx true; then
	echo "Error: container '$CONTAINER' is not running"
	exit 1
fi

if ! docker exec "$CONTAINER" id "$USERNAME" &>/dev/null; then
	echo "Error: user '$USERNAME' does not exist in container '$CONTAINER'"
	exit 1
fi

HOME_DIR="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination (printf "/home/%s" "'"$USERNAME"'")}}{{.Source}}{{end}}{{end}}' "$CONTAINER")"
GPU_NUM="$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER" | sed -n 's/^NVIDIA_VISIBLE_DEVICES=//p')"
GPU_CAPABILITIES="$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER" | sed -n 's/^NVIDIA_DRIVER_CAPABILITIES=//p')"
RUNTIME="$(docker inspect --format '{{.HostConfig.Runtime}}' "$CONTAINER")"
RESTART_POLICY="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$CONTAINER")"
NETWORK_MODE="$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$CONTAINER")"
DOCKER_GROUP_ID="$(stat -c '%g' /var/run/docker.sock)"

if [ -z "$HOME_DIR" ] || [ -z "$GPU_NUM" ] || [ -z "$RUNTIME" ] || [ -z "$RESTART_POLICY" ]; then
	echo "Error: '$CONTAINER' does not match the expected create_user.sh configuration"
	exit 1
fi

echo "=========================================="
echo "Enabling Docker builds for: $USERNAME"
echo "  Container:   $CONTAINER"
echo "  Home:        $HOME_DIR"
echo "  GPU:         $GPU_NUM"
echo "  Docker GID:  $DOCKER_GROUP_ID"
echo ""
echo "Warning: Docker socket access grants the container user root-equivalent control of this host."
echo "=========================================="

BACKUP_IMAGE="$CONTAINER:before-docker-$(date +%Y%m%d-%H%M%S)"

echo "[1/5] Creating backup image..."
docker commit "$CONTAINER" "$BACKUP_IMAGE"
echo "  Backup image: $BACKUP_IMAGE"

echo "[2/5] Recreating container with Docker socket..."
docker stop "$CONTAINER"
docker rm "$CONTAINER"
docker run -d \
	--network="$NETWORK_MODE" \
	--name="$CONTAINER" \
	--restart="$RESTART_POLICY" \
	--runtime="$RUNTIME" \
	-e NVIDIA_VISIBLE_DEVICES="$GPU_NUM" \
	-e NVIDIA_DRIVER_CAPABILITIES="$GPU_CAPABILITIES" \
	-v "$HOME_DIR:/home/$USERNAME" \
	-v /data3:/data3 \
	-v /usr/bin/nvidia-smi:/usr/bin/nvidia-smi:ro \
	-v /var/run/docker.sock:/var/run/docker.sock \
	-w "/home/$USERNAME" \
	-e HOME="/home/$USERNAME" \
	-e TERM=xterm-256color \
	"$BACKUP_IMAGE" \
	sleep infinity

echo "[3/5] Installing Docker CLI when needed..."
docker exec -u root "$CONTAINER" bash -lc '
if ! command -v docker >/dev/null; then
	apt update -qq
	DEBIAN_FRONTEND=noninteractive apt install -y -qq docker.io
	apt clean -qq
fi
'

echo "[4/5] Granting Docker socket access to $USERNAME..."
docker exec -u root -i "$CONTAINER" bash <<EOF
set -e
SOCKET_GROUP="\$(getent group $DOCKER_GROUP_ID | cut -d: -f1)"
if [ -z "\$SOCKET_GROUP" ]; then
	SOCKET_GROUP=docker-host
	if getent group "\$SOCKET_GROUP" >/dev/null; then
		SOCKET_GROUP="docker-host-$DOCKER_GROUP_ID"
	fi
	groupadd -g $DOCKER_GROUP_ID "\$SOCKET_GROUP"
fi
usermod -aG "\$SOCKET_GROUP" $USERNAME
EOF

echo "[5/5] Verifying Docker access..."
docker exec -u "$USERNAME" "$CONTAINER" docker version --format 'Client={{.Client.Version}} Server={{.Server.Version}}'

echo "=========================================="
echo "Done. '$USERNAME' can now run docker build in '$CONTAINER'."
echo "Backup image retained: $BACKUP_IMAGE"
echo "=========================================="
