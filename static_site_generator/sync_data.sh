#!/usr/bin/env bash

# Sync data from the Raspberry Pi to local machine for static site generation
# Usage: ./sync_data.sh [--dry-run]

set -euo pipefail

# Configuration - edit these to match your setup
DEFAULT_SOURCE_HOST="rob@192.168.17.145"
SOURCE_DATA_PATH="/home/mcpserver/data/"
SOURCE_CLAUDE_PATH="/home/gardener/.claude/projects/-home-gardener-workspace/"
LOCAL_DATA_DIR="./app/data/"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo -e "${YELLOW}= DRY RUN MODE - No files will be synced${NC}"
fi

# Check if source host is reachable
echo -e "${BLUE}=á Checking connection to ${DEFAULT_SOURCE_HOST}...${NC}"
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "${DEFAULT_SOURCE_HOST}" "echo 'Connected'" > /dev/null 2>&1; then
    echo -e "${YELLOW}   Cannot connect to ${DEFAULT_SOURCE_HOST}${NC}"
    echo "Make sure:"
    echo "  1. The Pi is powered on and connected to the network"
    echo "  2. SSH is enabled on the Pi"
    echo "  3. Your SSH keys are set up (or you'll be prompted for password)"
    exit 1
fi
echo -e "${GREEN} Connection successful${NC}"

# Create local data directory if it doesn't exist
mkdir -p "${LOCAL_DATA_DIR}"
mkdir -p "${LOCAL_DATA_DIR}/claude"

# Sync MCP server data
echo -e "${BLUE}=å Syncing MCP server data...${NC}"
rsync -av --no-perms --update ${DRY_RUN} \
    "${DEFAULT_SOURCE_HOST}:${SOURCE_DATA_PATH}" \
    "${LOCAL_DATA_DIR}"

# Sync Claude conversation history
echo -e "${BLUE}=å Syncing Claude conversation history...${NC}"
rsync -av --no-perms --update ${DRY_RUN} \
    "${DEFAULT_SOURCE_HOST}:${SOURCE_CLAUDE_PATH}" \
    "${LOCAL_DATA_DIR}/claude/"

echo ""
echo -e "${GREEN} Sync complete!${NC}"
echo ""
echo "Data synced to:"
echo "  " MCP data: ${LOCAL_DATA_DIR}"
echo "  " Claude conversations: ${LOCAL_DATA_DIR}/claude/"
echo ""

# Show some stats
if [[ -z "${DRY_RUN}" ]]; then
    CONVERSATION_COUNT=$(find "${LOCAL_DATA_DIR}/claude" -name "*.jsonl" -type f | wc -l | tr -d ' ')
    DATA_FILES=$(find "${LOCAL_DATA_DIR}" -maxdepth 1 -name "*.jsonl" -type f | wc -l | tr -d ' ')

    echo "=Ê Quick stats:"
    echo "  " ${CONVERSATION_COUNT} conversation files"
    echo "  " ${DATA_FILES} data JSONL files"

    if [[ -d "${LOCAL_DATA_DIR}/../photos" ]]; then
        PHOTO_COUNT=$(find "${LOCAL_DATA_DIR}/../photos" -name "plant_*.jpg" -type f 2>/dev/null | wc -l | tr -d ' ')
        echo "  " ${PHOTO_COUNT} photos"
    fi
fi

echo ""
echo "Next steps:"
echo "  1. Generate the static site: python static_site_generator/generate.py"
echo "  2. View locally: open static_site_generator/output/index.html"
echo "     or: python -m http.server -d static_site_generator/output"
