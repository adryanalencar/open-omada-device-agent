#!/usr/bin/env bash
set -euo pipefail

OPENWRT_HOST="${OPENWRT_HOST:-root@172.17.0.4}"
REMOTE_DIR="${REMOTE_DIR:-/mnt/shared/open-omada-device-agent}"
REMOTE_PYTHON="${REMOTE_PYTHON:-/usr/bin/python3}"
REMOTE_AGENT="${REMOTE_AGENT:-/usr/bin/open-omada-agent}"
AGENT_ARGS="${AGENT_ARGS:---debug}"
LOG_FILE="${LOG_FILE:-/tmp/open-omada-agent.log}"
SSH_OPTS="${SSH_OPTS:--o StrictHostKeyChecking=no -o UserKnownHostsFile=/tmp/openomada_known_hosts}"
RESTART=1

usage() {
    cat <<'EOF'
Usage: scripts/deploy-openwrt.sh [options]

Options:
  --host USER@HOST      SSH target. Default: root@172.17.0.4
  --remote-dir PATH     Remote repository path. Default: /mnt/shared/open-omada-device-agent
  --agent-args ARGS     Arguments passed to open-omada-agent. Default: --debug
  --log-file PATH       Remote log file. Default: /tmp/open-omada-agent.log
  --no-restart          Copy files but do not restart the agent
  -h, --help            Show this help

Environment overrides:
  OPENWRT_HOST, REMOTE_DIR, REMOTE_PYTHON, REMOTE_AGENT, AGENT_ARGS, LOG_FILE, SSH_OPTS
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --host)
            OPENWRT_HOST="${2:?missing value for --host}"
            shift 2
            ;;
        --remote-dir)
            REMOTE_DIR="${2:?missing value for --remote-dir}"
            shift 2
            ;;
        --agent-args)
            AGENT_ARGS="${2:?missing value for --agent-args}"
            shift 2
            ;;
        --log-file)
            LOG_FILE="${2:?missing value for --log-file}"
            shift 2
            ;;
        --no-restart)
            RESTART=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -d "$PROJECT_ROOT/src/open_omada_device_agent" ]; then
    echo "Could not find src/open_omada_device_agent under $PROJECT_ROOT" >&2
    exit 1
fi

echo "Deploying Open Omada agent source to $OPENWRT_HOST:$REMOTE_DIR"

# shellcheck disable=SC2086
COPYFILE_DISABLE=1 tar -C "$PROJECT_ROOT" -cf - src/open_omada_device_agent agent.py pyproject.toml README.md docs \
    | ssh $SSH_OPTS "$OPENWRT_HOST" "mkdir -p '$REMOTE_DIR' && tar -C '$REMOTE_DIR' -xf -"

if [ "$RESTART" -eq 0 ]; then
    echo "Copied source. Restart skipped by --no-restart."
    exit 0
fi

# shellcheck disable=SC2086
ssh $SSH_OPTS "$OPENWRT_HOST" \
    "REMOTE_DIR='$REMOTE_DIR' REMOTE_PYTHON='$REMOTE_PYTHON' REMOTE_AGENT='$REMOTE_AGENT' AGENT_ARGS='$AGENT_ARGS' LOG_FILE='$LOG_FILE' /bin/ash -s" <<'REMOTE'
set -eu

if [ ! -x "$REMOTE_PYTHON" ]; then
    echo "Missing Python interpreter: $REMOTE_PYTHON" >&2
    exit 1
fi

if [ ! -x "$REMOTE_AGENT" ]; then
    echo "Missing agent entrypoint: $REMOTE_AGENT" >&2
    exit 1
fi

if ! command -v ubus >/dev/null 2>&1; then
    echo "Warning: ubus not found; OpenWrt telemetry and WLAN control will be limited" >&2
fi

if ! command -v uci >/dev/null 2>&1; then
    echo "Warning: uci not found; OpenWrt configuration control will be limited" >&2
fi

if ! command -v ndsctl >/dev/null 2>&1; then
    echo "Warning: ndsctl not found; openNDS portal telemetry/control will be limited" >&2
fi

agent_pids() {
    ps w | awk -v agent="$REMOTE_AGENT" '
        $1 ~ /^[0-9]+$/ && index($0, agent) && !index($0, " awk ") && !index($0, " grep ") {print $1}
    '
}

pids="$(agent_pids)"
if [ -n "$pids" ]; then
    echo "Stopping existing open-omada-agent process(es): $pids"
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 2
    remaining_pids="$(agent_pids)"
    if [ -n "$remaining_pids" ]; then
        echo "Force-stopping existing open-omada-agent process(es): $remaining_pids"
        for pid in $remaining_pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
        sleep 1
    fi
fi

stamp="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo now)"
if [ -f "$LOG_FILE" ]; then
    mv "$LOG_FILE" "$LOG_FILE.before-deploy-$stamp"
fi

cmd="cd '$REMOTE_DIR' && exec '$REMOTE_AGENT' $AGENT_ARGS >'$LOG_FILE' 2>&1 </dev/null"
if command -v setsid >/dev/null 2>&1; then
    setsid /bin/ash -c "$cmd" &
elif [ -x /sbin/start-stop-daemon ]; then
    /sbin/start-stop-daemon -S -b -x /bin/ash -- -c "$cmd"
else
    /bin/ash -c "$cmd" &
fi

sleep 5
new_pids="$(agent_pids)"
if [ -z "$new_pids" ]; then
    echo "open-omada-agent did not stay running. Last log lines:" >&2
    tail -80 "$LOG_FILE" 2>/dev/null || true
    exit 1
fi

echo "open-omada-agent running with PID(s): $new_pids"
echo "Last log lines from $LOG_FILE:"
tail -80 "$LOG_FILE" 2>/dev/null || true
REMOTE
