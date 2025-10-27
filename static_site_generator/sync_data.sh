#!/usr/bin/env bash

# Sync data from the Raspberry Pi to local machine for static site generation
# Usage: ./sync_data.sh [--dry-run]

# Note: We don't use -e (exit on error) because rsync may return non-zero for partial transfers
# (e.g., permission denied on some files). We check exit codes explicitly instead.
set -uo pipefail

# Determine project root (parent of the script's directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration - edit these to match your setup
DEFAULT_SOURCE_HOST="rob@192.168.17.145"
SOURCE_DATA_PATH="/home/mcpserver/data/"
SOURCE_CLAUDE_PATH="/home/gardener/.claude/projects/-home-gardener-workspace/"
SOURCE_PHOTOS_PATH="/home/mcpserver/photos/"
LOCAL_DATA_DIR="${PROJECT_ROOT}/app/data/"
LOCAL_PHOTOS_DIR="${PROJECT_ROOT}/app/photos/"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be synced${NC}"
fi

# Check if source host is reachable
echo -e "${BLUE}🔌 Checking connection to ${DEFAULT_SOURCE_HOST}...${NC}"
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "${DEFAULT_SOURCE_HOST}" "echo 'Connected'" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Cannot connect to ${DEFAULT_SOURCE_HOST}${NC}"
    echo "Make sure:"
    echo "  1. The Pi is powered on and connected to the network"
    echo "  2. SSH is enabled on the Pi"
    echo "  3. Your SSH keys are set up (or you'll be prompted for password)"
    exit 1
fi
echo -e "${GREEN}✓ Connection successful${NC}"

# Helper function to report rsync status
report_rsync_status() {
    local exit_code=$1
    local description=$2

    if [[ ${exit_code} -eq 0 ]]; then
        echo -e "${GREEN}  ✓ ${description} synced successfully${NC}"
    elif [[ ${exit_code} -eq 23 ]]; then
        echo -e "${YELLOW}  ⚠️  ${description} partially synced (some files skipped due to permissions)${NC}"
    else
        echo -e "${YELLOW}  ⚠️  ${description} rsync exited with code ${exit_code}${NC}"
    fi
}

# Create local directories if they don't exist
mkdir -p "${LOCAL_DATA_DIR}"
mkdir -p "${LOCAL_DATA_DIR}/claude"
mkdir -p "${LOCAL_PHOTOS_DIR}"

# Sync MCP server data
echo -e "${BLUE}📊 Syncing MCP server data...${NC}"
# Exclude light_state.json which has permission issues and isn't needed for static site
rsync -av --no-perms --update ${DRY_RUN} \
    --exclude='light_state.json' \
    "${DEFAULT_SOURCE_HOST}:${SOURCE_DATA_PATH}" \
    "${LOCAL_DATA_DIR}"
report_rsync_status $? "MCP data"

# Sync Claude conversation history
echo -e "${BLUE}💬 Syncing Claude conversation history...${NC}"
rsync -av --no-perms --update ${DRY_RUN} \
    "${DEFAULT_SOURCE_HOST}:${SOURCE_CLAUDE_PATH}" \
    "${LOCAL_DATA_DIR}/claude/"
report_rsync_status $? "Claude conversations"

# Sync photos
echo -e "${BLUE}📸 Syncing plant photos...${NC}"
rsync -av --no-perms --update ${DRY_RUN} \
    "${DEFAULT_SOURCE_HOST}:${SOURCE_PHOTOS_PATH}" \
    "${LOCAL_PHOTOS_DIR}"
report_rsync_status $? "Photos"

echo ""
echo -e "${GREEN}✅ Sync complete!${NC}"
echo ""
echo "Data synced to:"
echo "  📊 MCP data: ${LOCAL_DATA_DIR}"
echo "  💬 Claude conversations: ${LOCAL_DATA_DIR}/claude/"
echo "  📸 Plant photos: ${LOCAL_PHOTOS_DIR}"
echo ""

# Show some stats
if [[ -z "${DRY_RUN}" ]]; then
    CONVERSATION_COUNT=$(find "${LOCAL_DATA_DIR}/claude" -name "*.jsonl" -type f | wc -l | tr -d ' ')
    DATA_FILES=$(find "${LOCAL_DATA_DIR}" -maxdepth 1 -name "*.jsonl" -type f | wc -l | tr -d ' ')

    echo "📈 Quick stats:"
    echo "  📄 ${CONVERSATION_COUNT} conversation files"
    echo "  📄 ${DATA_FILES} data JSONL files"

    if [[ -d "${LOCAL_PHOTOS_DIR}" ]]; then
        PHOTO_COUNT=$(find "${LOCAL_PHOTOS_DIR}" -name "plant_*.jpg" -type f 2>/dev/null | wc -l | tr -d ' ')
        echo "  📸 ${PHOTO_COUNT} photos"
    fi
fi

echo ""
echo "Next steps:"
echo "  1. Generate the static site:"
echo "       cd static_site_generator"
echo "       uv run python generate.py"
echo "  2. View locally:"
echo "       open output/index.html"
echo "       or: uv run python -m http.server -d output 8080"
