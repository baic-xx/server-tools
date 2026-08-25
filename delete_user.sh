#!/bin/bash
set -euo pipefail

# Roll back everything create_user.sh created for a user:
#   - docker container <USERNAME>-env
#   - host user (and its home directory)
#   - login shell script /usr/local/bin/<USERNAME>-shell
#   - entry in /etc/shells

usage() {
    echo "Usage: $0 -u USERNAME [-k]"
    echo ""
    echo "Options:"
    echo "  -u  Username to remove (required)"
    echo "  -k  Keep the home directory (default: remove it)"
    echo ""
    echo "Example:"
    echo "  $0 -u zhangsan          # remove user + home dir"
    echo "  $0 -u zhangsan -k       # remove user but keep home dir"
    exit 1
}

USERNAME=""
KEEP_HOME=false

while getopts "u:kh" opt; do
    case $opt in
        u) USERNAME="$OPTARG" ;;
        k) KEEP_HOME=true ;;
        h) usage ;;
        *) usage ;;
    esac
done

if [ -z "${USERNAME:-}" ]; then
    echo "Error: -u USERNAME is required"
    usage
fi

CONTAINER="$USERNAME-env"
SHELL_SCRIPT="/usr/local/bin/$USERNAME-shell"

# Track what actually existed so the summary is accurate
HAD_USER=false
HAD_HOME=false
HAD_CONTAINER=false
HAD_SHELL=false

id "$USERNAME" &>/dev/null && HAD_USER=true || true
docker inspect "$CONTAINER" &>/dev/null && HAD_CONTAINER=true || true
[ -f "$SHELL_SCRIPT" ] && HAD_SHELL=true || true

echo "=========================================="
echo "Removing user: $USERNAME"
echo "  Keep home:   $KEEP_HOME"
echo "  Container:   $CONTAINER"
echo "=========================================="

# 1. Stop and remove the docker container first (so nothing is using the home dir)
echo "[1/4] Removing docker container..."
if $HAD_CONTAINER; then
    docker rm -f "$CONTAINER"
    echo "  Removed container $CONTAINER"
else
    echo "  Container $CONTAINER does not exist, skipping"
fi

# 2. Remove the host user
echo "[2/4] Removing host user..."
if $HAD_USER; then
    if $KEEP_HOME; then
        userdel "$USERNAME"
        echo "  Removed user $USERNAME (home directory kept)"
    else
        userdel -r "$USERNAME" 2>/dev/null || {
            # userdel -r fails if home dir is on a path it doesn't expect; fall back
            userdel "$USERNAME"
            rm -rf "/data/$USERNAME"
        }
        echo "  Removed user $USERNAME and home directory"
    fi
else
    echo "  User $USERNAME does not exist, skipping"
fi

# 3. Remove the login shell script
echo "[3/4] Removing login shell script..."
if $HAD_SHELL; then
    rm -f "$SHELL_SCRIPT"
    echo "  Removed $SHELL_SCRIPT"
else
    echo "  $SHELL_SCRIPT does not exist, skipping"
fi

# 4. Remove the entry from /etc/shells
echo "[4/4] Cleaning /etc/shells..."
if grep -q "$SHELL_SCRIPT" /etc/shells 2>/dev/null; then
    sed -i.bak "\@$SHELL_SCRIPT@d" /etc/shells
    echo "  Removed $SHELL_SCRIPT from /etc/shells (backup: /etc/shells.bak)"
else
    echo "  $SHELL_SCRIPT not in /etc/shells, skipping"
fi

# Verify
echo ""
echo "=========================================="
echo "Verification:"
echo "  User:        $([ "$HAD_USER" = true ] && { id "$USERNAME" 2>/dev/null && echo "  STILL EXISTS ✗" || echo "removed ✓"; } || echo "did not exist")"
echo "  Home:        $( { [ "$KEEP_HOME" = true ] && echo "kept (-k)"; } || { [ -d "/data/$USERNAME" ] && echo "STILL EXISTS ✗" || echo "removed ✓"; } )"
echo "  Container:   $(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER" && echo "STILL EXISTS ✗" || echo "removed ✓")"
echo "  Shell script: $( [ -f "$SHELL_SCRIPT" ] && echo "STILL EXISTS ✗" || echo "removed ✓")"
echo "  /etc/shells: $(grep -q "$SHELL_SCRIPT" /etc/shells 2>/dev/null && echo "entry STILL EXISTS ✗" || echo "clean ✓")"
echo "=========================================="
