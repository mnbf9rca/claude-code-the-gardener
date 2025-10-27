#!/usr/bin/env bash

# Publish static site to S3 with change detection
# Only uploads if changes are detected (avoids unnecessary write fees)
# Usage: ./publish.sh --output-dir <path> [--dry-run]

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Load configuration from .env.publish
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
OUTPUT_DIR=""
DRY_RUN=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dryrun"
            shift
            ;;
        --help)
            echo "Usage: $0 --output-dir <path> [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --output-dir       Path to directory containing generated static site (required)"
            echo "  --dry-run          Show what would be uploaded without actually uploading"
            echo ""
            echo "Environment (set in .env.publish):"
            echo "  S3_BUCKET               S3 bucket name"
            echo "  AWS_ACCESS_KEY_ID       AWS access key"
            echo "  AWS_SECRET_ACCESS_KEY   AWS secret key"
            echo "  AWS_REGION              AWS region (e.g., us-east-1)"
            echo ""
            echo "Example:"
            echo "  $0 --output-dir ./output"
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option: $1${NC}"
            echo "Run with --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$OUTPUT_DIR" ]]; then
    echo -e "${RED}Error: --output-dir is required${NC}"
    echo "Run with --help for usage information"
    exit 1
fi

if [[ -z "$S3_BUCKET" ]]; then
    echo -e "${RED}Error: S3_BUCKET not set in .env.publish${NC}"
    echo "Edit ${SCRIPT_DIR}/.env.publish and set S3_BUCKET"
    exit 1
fi

# Validate output directory exists
if [[ ! -d "$OUTPUT_DIR" ]]; then
    echo -e "${RED}Error: Output directory not found: $OUTPUT_DIR${NC}"
    echo "Run generate.py first to create the static site"
    exit 1
fi

# Check for AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI not found${NC}"
    echo "Install AWS CLI v2:"
    echo "  macOS:  brew install awscli"
    echo "  Linux:  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

# Dry run mode notification
if [[ -n "$DRY_RUN" ]]; then
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be uploaded${NC}"
    echo ""
fi

echo -e "${BLUE}📦 Claude the Gardener - Site Publisher${NC}"
echo "=========================================="
echo ""

# Validate AWS_REGION is set
if [[ -z "$AWS_REGION" ]]; then
    echo -e "${RED}Error: AWS_REGION not set${NC}"
    echo "Set AWS_REGION in .env.publish (e.g., us-east-1, eu-west-2)"
    exit 1
fi

echo "Configuration:"
echo "  Output directory: $OUTPUT_DIR"
echo "  S3 bucket:        s3://$S3_BUCKET"
echo "  AWS region:       $AWS_REGION"
echo ""

# Initialize git repo in output directory if not exists
# This is used for change detection
cd "$OUTPUT_DIR"

if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo -e "${BLUE}🔧 Initializing git repository for change tracking...${NC}"
    git init
    git config user.name "Claude the Gardener Publisher"
    git config user.email "publisher@gardener.local"
    echo -e "${GREEN}  ✓ Git repository initialized${NC}"
fi

# Check for changes
echo -e "${BLUE}🔍 Checking for changes...${NC}"

# Stage all files
git add -A

# Check if there are changes
if git diff --cached --quiet; then
    echo -e "${YELLOW}  ℹ️  No changes detected - site is already up to date${NC}"
    echo ""
    echo "Nothing to publish. Exiting."
    exit 0
fi

# Show what changed
CHANGED_FILES=$(git diff --cached --stat | tail -n 1)
echo -e "${GREEN}  ✓ Changes detected:${NC}"
git diff --cached --stat | head -n 20
if [[ $(git diff --cached --numstat | wc -l) -gt 20 ]]; then
    echo "  ... (showing first 20 files)"
fi
echo ""
echo -e "${GREEN}  Summary: $CHANGED_FILES${NC}"
echo ""

# Upload to S3
echo -e "${BLUE}☁️  Uploading to S3...${NC}"

# Sync to S3 with proper content types and cache headers
# AWS CLI automatically uses AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION from environment
aws s3 sync . "s3://$S3_BUCKET" \
    --delete \
    --exclude ".git/*" \
    --exclude ".DS_Store" \
    --cache-control "public, max-age=3600" \
    --metadata-directive REPLACE \
    $DRY_RUN

SYNC_EXIT_CODE=$?

if [[ $SYNC_EXIT_CODE -ne 0 ]]; then
    echo -e "${RED}  ✗ S3 sync failed with exit code: $SYNC_EXIT_CODE${NC}"
    echo ""
    echo "Common issues:"
    echo "  - Check AWS credentials are configured correctly"
    echo "  - Verify S3 bucket exists and you have write permissions"
    echo "  - Ensure AWS CLI profile '$AWS_PROFILE' is valid"
    exit $SYNC_EXIT_CODE
fi

echo -e "${GREEN}  ✓ Upload complete${NC}"
echo ""

# Commit changes (audit trail)
if [[ -z "$DRY_RUN" ]]; then
    echo -e "${BLUE}📝 Recording publication in git history...${NC}"
    git commit -m "Published at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo -e "${GREEN}  ✓ Changes committed${NC}"
    echo ""
fi

# Success summary
echo "=========================================="
echo -e "${GREEN}✅ Publication complete!${NC}"
echo ""
echo "Site URL: http://$S3_BUCKET.s3-website.${AWS_REGION}.amazonaws.com"
echo ""
echo "Next steps:"
echo "  - Verify the site at the URL above"
echo "  - Configure Cloudflare proxy to point to S3 endpoint"
echo "  - Set up CloudFront distribution for HTTPS (optional)"
echo ""
