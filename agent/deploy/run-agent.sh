#!/bin/bash
set -euo pipefail

# Single-run agent executor for gardener user
# Executes Claude Code agent once per invocation (triggered by systemd timer)
# Timer schedules runs 20 minutes after previous run completes

# Load environment variables from .env.agent
ENV_FILE="$HOME/.env.agent"
if [ -f "$ENV_FILE" ]; then
    set -a  # Export all variables
    source "$ENV_FILE"
    set +a
fi

CLAUDE_BIN="$HOME/.local/bin/claude"
WORKSPACE_DIR="$HOME/workspace"
LOCK_FILE="$HOME/.gardener-agent.lock"
LOG_DIR="${LOG_DIR:-$HOME/logs}"
PROMPT_FILE="$HOME/prompt.txt"
SYSTEM_PROMPT_FILE="$HOME/system-prompt.txt"
MCP_CONFIG_FILE="$HOME/.mcp.json"

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

# Validate MCP configuration file exists and is readable
if [ ! -f "$MCP_CONFIG_FILE" ]; then
    echo "[$(date -Iseconds)] ERROR: MCP configuration file not found: $MCP_CONFIG_FILE" >&2
    exit 1
fi

if [ ! -r "$MCP_CONFIG_FILE" ]; then
    echo "[$(date -Iseconds)] ERROR: MCP configuration file not readable: $MCP_CONFIG_FILE" >&2
    exit 1
fi

# Health check helper function
# Usage: healthcheck "/endpoint" [data_to_post]
healthcheck() {
    local endpoint="$1"
    local data="${2:-}"
    if [ -n "${HEALTHCHECK_URL:-}" ]; then
        if [ -n "$data" ]; then
            # POST with data (already truncated by caller)
            echo "$data" | curl -m 10 --retry 2 -fsS --data-binary @- "${HEALTHCHECK_URL}${endpoint}" || true
        else
            # Simple ping (GET)
            curl -m 5 --retry 2 -fsS "${HEALTHCHECK_URL}${endpoint}" || true
        fi
    fi
}

# Lock check - prevent concurrent executions
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "[$(date -Iseconds)] ERROR: Another instance is already running" >&2
    healthcheck "/fail"
    exit 1
fi

echo "[$(date -Iseconds)] Starting gardener agent run"

# Setup log file for this run
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/agent_${TIMESTAMP}.log"

echo "[$(date -Iseconds)] Starting execution" | tee -a "$LOG_FILE"

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
    exit 1
fi

PROMPT=$(cat "$PROMPT_FILE")

# Build command arguments array to properly handle spaces and special characters
CLAUDE_ARGS=(
    --output-format json
    --mcp-config "$MCP_CONFIG_FILE"
    -p "$PROMPT"
)

# Conditionally add system prompt argument if file exists
if [ -f "$SYSTEM_PROMPT_FILE" ]; then
    SYSTEM_PROMPT_EXTENSION=$(cat "$SYSTEM_PROMPT_FILE")
    CLAUDE_ARGS+=(--append-system-prompt "$SYSTEM_PROMPT_EXTENSION")
    echo "[$(date -Iseconds)] Using system prompt extension from $SYSTEM_PROMPT_FILE" | tee -a "$LOG_FILE"
fi

# Execute Claude Code agent from workspace directory (tee to both terminal and log file)
# Runs in isolated workspace so Claude cannot access config files in $HOME
if (cd "$WORKSPACE_DIR" && "$CLAUDE_BIN" "${CLAUDE_ARGS[@]}") 2>&1 | tee -a "$LOG_FILE"; then
    EXEC_EXIT_CODE=0
    echo "[$(date -Iseconds)] Execution completed successfully" | tee -a "$LOG_FILE"
else
    EXEC_EXIT_CODE=$?
    echo "[$(date -Iseconds)] ERROR: Execution failed with exit code $EXEC_EXIT_CODE" | tee -a "$LOG_FILE"
fi

# Check for /login in output (indicates authentication failure)
if grep -q "/login" "$LOG_FILE"; then
    echo "[$(date -Iseconds)] ERROR: Detected /login in output - authentication failure" | tee -a "$LOG_FILE"
    EXEC_EXIT_CODE=1
fi

# Send appropriate healthcheck with log content (last 100KB)
if [ "$EXEC_EXIT_CODE" -eq 0 ]; then
    healthcheck "" "$(tail -c 102400 "$LOG_FILE")"  # Success endpoint with logs
else
    healthcheck "/fail" "$(tail -c 102400 "$LOG_FILE")"  # Failure endpoint with logs
fi

# Backup Claude conversations to git repository
BACKUP_DIR="$HOME/claude-backup"
PROJECTS_DIR="$HOME/.claude/projects/-home-gardener-workspace"

echo "[$(date -Iseconds)] Backing up conversations to git" | tee -a "$LOG_FILE"

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_DIR" ]; then
    echo "[$(date -Iseconds)]   Creating backup directory: $BACKUP_DIR" | tee -a "$LOG_FILE"
    mkdir -p "$BACKUP_DIR"
fi

# Initialize git repo if not already initialized (defensive)
if [ ! -d "$BACKUP_DIR/.git" ]; then
    echo "[$(date -Iseconds)]   Initializing git repository" | tee -a "$LOG_FILE"
    (cd "$BACKUP_DIR" && git init --initial-branch=main)
    (cd "$BACKUP_DIR" && git config user.name "Gardener Backup")
    (cd "$BACKUP_DIR" && git config user.email "backup@gardener.local")

    # Create .gitignore
    cat > "$BACKUP_DIR/.gitignore" << 'EOF'
# Exclude temporary files
*.tmp
*.swp
*.log
EOF
fi

# Sync conversations to backup directory (only if source exists)
if [ -d "$PROJECTS_DIR" ]; then
    echo "[$(date -Iseconds)]   Syncing conversations from $PROJECTS_DIR" | tee -a "$LOG_FILE"
    rsync -a --delete --filter='protect .git' "$PROJECTS_DIR/" "$BACKUP_DIR/" 2>&1 | tee -a "$LOG_FILE" || {
        echo "[$(date -Iseconds)]   WARNING: rsync failed, continuing anyway" | tee -a "$LOG_FILE"
    }

    # Commit changes (if any)
    (
        cd "$BACKUP_DIR"
        git add -A
        if ! git diff --cached --quiet; then
            TIMESTAMP=$(date -Iseconds)
            if git commit -m "Conversation backup: $TIMESTAMP"; then
                echo "[$(date -Iseconds)]   ✓ Conversations backed up successfully" | tee -a "$LOG_FILE"
            else
                echo "[$(date -Iseconds)]   WARNING: Git commit failed" | tee -a "$LOG_FILE"
            fi
        else
            echo "[$(date -Iseconds)]   No changes to backup" | tee -a "$LOG_FILE"
        fi
    ) 2>&1 | tee -a "$LOG_FILE" || {
        echo "[$(date -Iseconds)]   WARNING: Backup git operations failed" | tee -a "$LOG_FILE"
    }
else
    echo "[$(date -Iseconds)]   WARNING: Projects directory not found: $PROJECTS_DIR" | tee -a "$LOG_FILE"
fi

echo "[$(date -Iseconds)] Agent run complete" | tee -a "$LOG_FILE"
exit $EXEC_EXIT_CODE
