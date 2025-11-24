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
    git init --initial-branch=main
    git config user.name "Claude the Gardener Publisher"
    git config user.email "publisher@gardener.local"
    echo -e "${GREEN}  ✓ Git repository initialized${NC}"
fi

# Always ensure .gitignore exists and is up-to-date
# (not just on first init, in case it was missing or needs updating)
cat > .gitignore << 'EOF'
# Exclude photos directory - large binary files that rarely change
# and would cause the git repo to grow uncontrollably
photos/*.jpg
photos/*.jpeg
photos/*.png

# But track the index file so we know when photos change
!photos/index.txt

# Exclude system files
.DS_Store
EOF

echo -e "${GREEN}  ✓ .gitignore configured (excluding photo files, tracking index)${NC}"

# Generate photo index for change detection
# This allows git to detect when photos are added/removed without tracking the large binaries
if [[ -d "photos" ]]; then
    ls photos/ 2>/dev/null | sort > photos/index.txt || echo "" > photos/index.txt
    echo -e "${GREEN}  ✓ Photo index generated${NC}"
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
git diff --cached --stat | head -n 20 || true
if [[ $(git diff --cached --numstat | wc -l) -gt 20 ]]; then
    echo "  ... (showing first 20 files)"
fi
echo ""
echo -e "${GREEN}  Summary: $CHANGED_FILES${NC}"
echo ""

# Upload to S3
echo -e "${BLUE}☁️  Uploading to S3...${NC}"
echo ""

# Step 1: Sync photos WITHOUT --delete to preserve them forever in S3
# Photos are valuable historical records and should never be deleted
if [[ -d "photos" ]] && [[ -n "$(ls -A photos 2>/dev/null)" ]]; then
    echo "  📸 Syncing photos (never deleted)..."
    aws s3 sync photos/ "s3://$S3_BUCKET/photos/" \
        --cache-control "public, max-age=31536000" \
        --metadata-directive REPLACE \
        $DRY_RUN

    PHOTOS_EXIT_CODE=$?
    if [[ $PHOTOS_EXIT_CODE -ne 0 ]]; then
        echo -e "${RED}  ✗ Photos sync failed with exit code: $PHOTOS_EXIT_CODE${NC}"
        exit $PHOTOS_EXIT_CODE
    fi
    echo -e "${GREEN}  ✓ Photos synced${NC}"
    echo ""
fi

# Step 2: Sync everything else WITH --delete (excluding photos)
# This ensures HTML/CSS/JS files are properly updated and old files are removed
echo "  🌐 Syncing site content (HTML, CSS, JS)..."
aws s3 sync . "s3://$S3_BUCKET" \
    --delete \
    --exclude ".git/*" \
    --exclude ".DS_Store" \
    --exclude ".gitignore" \
    --exclude "photos/*" \
    --exclude "photos" \
    --cache-control "public, max-age=3600" \
    --metadata-directive REPLACE \
    $DRY_RUN

SYNC_EXIT_CODE=$?

if [[ $SYNC_EXIT_CODE -ne 0 ]]; then
    echo -e "${RED}  ✗ Site content sync failed with exit code: $SYNC_EXIT_CODE${NC}"
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
