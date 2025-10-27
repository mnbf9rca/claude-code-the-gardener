#!/usr/bin/env bash

# Orchestrate the complete website publishing pipeline
# Chains: sync (optional) -> build -> publish (if changes)
# Usage: ./orchestrate.sh [OPTIONS]

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Determine script directory (for finding other scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load configuration from .env.publish
if [[ ! -f "${SCRIPT_DIR}/.env.publish" ]]; then
    echo -e "${RED}Error: .env.publish not found${NC}"
    echo "Create ${SCRIPT_DIR}/.env.publish with your AWS credentials"
    echo "See .env.publish.example for template"
    exit 1
fi

# Source the environment file
set -a
source "${SCRIPT_DIR}/.env.publish"
set +a

# Default values
SKIP_SYNC=false
DATA_DIR="${PROJECT_ROOT}/app/data"
PHOTOS_DIR="${PROJECT_ROOT}/app/photos"
OUTPUT_DIR="${SCRIPT_DIR}/output"
DRY_RUN=""
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-sync)
            SKIP_SYNC=true
            shift
            ;;
        --data-dir)
            DATA_DIR="$2"
            shift 2
            ;;
        --photos-dir)
            PHOTOS_DIR="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help)
            cat << EOF
Usage: $0 [OPTIONS]

Orchestrates the complete website publishing pipeline for Claude the Gardener.

Pipeline stages:
  1. Sync data from Raspberry Pi (optional, skip with --skip-sync)
  2. Build static site from data
  3. Publish to S3 (only if changes detected)

Options:
  --skip-sync           Skip data sync step (useful when running on Pi)
  --data-dir <path>     Path to data directory (default: ../app/data)
  --photos-dir <path>   Path to photos directory (default: ../app/photos)
  --output-dir <path>   Path to output directory (default: ./output)
  --dry-run             Show what would be done without actually doing it
  --verbose, -v         Verbose output for debugging

Environment Variables (set in .env.publish):
  S3_BUCKET               S3 bucket name
  AWS_ACCESS_KEY_ID       AWS access key
  AWS_SECRET_ACCESS_KEY   AWS secret key
  AWS_DEFAULT_REGION      AWS region

Examples:
  # Run locally (syncs from Pi, builds, publishes)
  $0

  # Run on Pi (skip sync, just build and publish)
  $0 --skip-sync

  # Dry run to test without publishing
  $0 --dry-run

  # Custom paths
  $0 --data-dir /path/to/data --output-dir /path/to/output

Exit Codes:
  0 - Success (site published or no changes detected)
  1 - Error in sync stage or .env.publish not found
  2 - Error in build stage
  3 - Error in publish stage
  4 - S3_BUCKET not set in .env.publish or unknown option

EOF
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option: $1${NC}"
            echo "Run with --help for usage information"
            exit 4
            ;;
    esac
done

# Validate S3_BUCKET is set in .env.publish
if [[ -z "$S3_BUCKET" ]]; then
    echo -e "${RED}Error: S3_BUCKET not set in .env.publish${NC}"
    echo "Edit ${SCRIPT_DIR}/.env.publish and set S3_BUCKET"
    exit 4
fi

# Start orchestration
echo -e "${BLUE}🌱 Claude the Gardener - Publishing Orchestrator${NC}"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Skip sync:    $SKIP_SYNC"
echo "  Data dir:     $DATA_DIR"
echo "  Photos dir:   $PHOTOS_DIR"
echo "  Output dir:   $OUTPUT_DIR"
echo "  S3 bucket:    s3://$S3_BUCKET"
echo "  AWS region:   ${AWS_DEFAULT_REGION:-us-east-1}"
if [[ -n "$DRY_RUN" ]]; then
    echo -e "  ${YELLOW}Mode:         DRY RUN${NC}"
fi
echo ""

# Track start time
START_TIME=$(date +%s)

# Stage 1: Sync data from Raspberry Pi
if [[ "$SKIP_SYNC" == true ]]; then
    echo -e "${YELLOW}⏭️  Stage 1: Sync (SKIPPED)${NC}"
    echo "   Running on Pi or data already synced"
    echo ""
else
    echo -e "${BLUE}📥 Stage 1: Syncing data from Raspberry Pi...${NC}"
    echo ""

    if [[ ! -f "${SCRIPT_DIR}/sync_data.sh" ]]; then
        echo -e "${RED}Error: sync_data.sh not found at ${SCRIPT_DIR}/sync_data.sh${NC}"
        exit 1
    fi

    SYNC_CMD="${SCRIPT_DIR}/sync_data.sh"
    if [[ -n "$DRY_RUN" ]]; then
        SYNC_CMD="$SYNC_CMD --dry-run"
    fi

    if [[ "$VERBOSE" == true ]]; then
        $SYNC_CMD
    else
        $SYNC_CMD 2>&1 | grep -E "(✓|✗|⚠️|Error|synced|files)" || true
    fi

    SYNC_EXIT_CODE=${PIPESTATUS[0]}

    if [[ $SYNC_EXIT_CODE -ne 0 ]]; then
        echo -e "${RED}  ✗ Sync failed with exit code: $SYNC_EXIT_CODE${NC}"
        exit 1
    fi

    echo -e "${GREEN}  ✓ Sync complete${NC}"
    echo ""
fi

# Stage 2: Build static site
echo -e "${BLUE}🏗️  Stage 2: Building static site...${NC}"
echo ""

if [[ ! -f "${SCRIPT_DIR}/generate.py" ]]; then
    echo -e "${RED}Error: generate.py not found at ${SCRIPT_DIR}/generate.py${NC}"
    exit 2
fi

# Build command as array to avoid eval security issues
BUILD_CMD=(uv run python "${SCRIPT_DIR}/generate.py" --data-dir "$DATA_DIR" --photos-dir "$PHOTOS_DIR" --output-dir "$OUTPUT_DIR")

if [[ "$VERBOSE" == true ]]; then
    "${BUILD_CMD[@]}"
    BUILD_EXIT_CODE=$?
else
    "${BUILD_CMD[@]}" 2>&1 | grep -E "(Error|✓|pages|events|conversations)" || true
    BUILD_EXIT_CODE=${PIPESTATUS[0]}
fi

if [[ $BUILD_EXIT_CODE -ne 0 ]]; then
    echo -e "${RED}  ✗ Build failed with exit code: $BUILD_EXIT_CODE${NC}"
    exit 2
fi

echo -e "${GREEN}  ✓ Build complete${NC}"
echo ""

# Stage 3: Publish to S3
echo -e "${BLUE}☁️  Stage 3: Publishing to S3...${NC}"
echo ""

if [[ ! -f "${SCRIPT_DIR}/publish.sh" ]]; then
    echo -e "${RED}Error: publish.sh not found at ${SCRIPT_DIR}/publish.sh${NC}"
    exit 3
fi

# Publish command as array to avoid eval security issues
PUBLISH_CMD=("${SCRIPT_DIR}/publish.sh" --output-dir "$OUTPUT_DIR")

if [[ -n "$DRY_RUN" ]]; then
    PUBLISH_CMD+=($DRY_RUN)
fi

if [[ "$VERBOSE" == true ]]; then
    "${PUBLISH_CMD[@]}"
    PUBLISH_EXIT_CODE=$?
else
    # For publish, we always want to see key information
    "${PUBLISH_CMD[@]}" 2>&1 | grep -E "(✓|✗|⚠️|Error|changes|uploaded|complete)" || true
    PUBLISH_EXIT_CODE=${PIPESTATUS[0]}
fi

if [[ $PUBLISH_EXIT_CODE -ne 0 ]]; then
    echo -e "${RED}  ✗ Publish failed with exit code: $PUBLISH_EXIT_CODE${NC}"
    exit 3
fi

echo ""

# Calculate duration
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Success summary
echo "=========================================="
echo -e "${GREEN}✅ Pipeline complete!${NC}"
echo ""
echo "Duration: ${DURATION}s"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

if [[ -z "$DRY_RUN" ]]; then
    echo "Your site has been published to: http://$S3_BUCKET.s3-website-${AWS_DEFAULT_REGION:-us-east-1}.amazonaws.com"
    echo ""
else
    echo -e "${YELLOW}(Dry run mode - no actual changes made)${NC}"
    echo ""
fi

exit 0
