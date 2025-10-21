#!/bin/bash
set -euo pipefail

# Continuous loop agent runner for gardener user
# Executes Claude Code agent every 10 minutes with health monitoring

CLAUDE_BIN="$HOME/.local/bin/claude"
LOCK_FILE="$HOME/.gardener-agent.lock"
LOG_DIR="${LOG_DIR:-$HOME/logs}"
PROMPT_FILE="$HOME/prompt.txt"

# Ensure log directory exists and is writable
if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
    echo "[$(date -Iseconds)] ERROR: Cannot create log directory: $LOG_DIR" >&2
    echo "[$(date -Iseconds)] Falling back to /tmp/gardener-logs" >&2
    LOG_DIR="/tmp/gardener-logs"
    mkdir -p "$LOG_DIR" || {
        echo "[$(date -Iseconds)] FATAL: Cannot create fallback log directory" >&2
        exit 1
    }
fi

if ! [ -w "$LOG_DIR" ]; then
    echo "[$(date -Iseconds)] ERROR: Log directory not writable: $LOG_DIR" >&2
    exit 1
fi

# Health check helper function
healthcheck() {
    local endpoint="$1"
    if [ -n "${HEALTHCHECK_URL:-}" ]; then
        curl -m 5 --retry 2 -fsS "${HEALTHCHECK_URL}${endpoint}" || true
    fi
}

# Lock check - prevent concurrent executions
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "[$(date -Iseconds)] ERROR: Another instance is already running" >&2
    healthcheck "/fail"
    exit 1
fi

echo "[$(date -Iseconds)] Starting gardener agent loop"

# Main execution loop
while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/agent_${TIMESTAMP}.log"

    echo "[$(date -Iseconds)] Starting execution cycle" | tee -a "$LOG_FILE"

    # Check log directory size (warn if > 1GB)
    LOG_SIZE_KB=$(du -sk "$LOG_DIR" 2>/dev/null | cut -f1)
    LOG_SIZE_MB=$((LOG_SIZE_KB / 1024))
    if [ "$LOG_SIZE_MB" -gt 1024 ]; then
        echo "[$(date -Iseconds)] WARNING: Log directory exceeds 1GB (${LOG_SIZE_MB}MB)" | tee -a "$LOG_FILE"
        echo "  Consider cleaning up old logs in: $LOG_DIR" | tee -a "$LOG_FILE"
        # Send failure notification but continue executing
        healthcheck "/fail"
    fi

    # Signal execution start
    healthcheck "/start"

    # Read prompt from file
    if [ ! -f "$PROMPT_FILE" ]; then
        echo "[$(date -Iseconds)] ERROR: Prompt file not found: $PROMPT_FILE" | tee -a "$LOG_FILE"
        healthcheck "/fail"
        sleep 600
        continue
    fi

    PROMPT=$(cat "$PROMPT_FILE")

    # Execute Claude Code agent from home directory (tee to both terminal and log file)
    # Must run from home directory since gardener user may not have access to other paths
    if (cd "$HOME" && "$CLAUDE_BIN" --continue --verbose --output-format json -p "$PROMPT") 2>&1 | tee -a "$LOG_FILE"; then
        echo "[$(date -Iseconds)] Execution completed successfully" | tee -a "$LOG_FILE"
        healthcheck ""  # Success endpoint (no suffix)
    else
        EXIT_CODE=$?
        echo "[$(date -Iseconds)] ERROR: Execution failed with exit code $EXIT_CODE" | tee -a "$LOG_FILE"
        healthcheck "/fail"
    fi

    # Wait 10 minutes before next execution
    echo "[$(date -Iseconds)] Sleeping for 10 minutes..." | tee -a "$LOG_FILE"
    sleep 600
done
