# Website Publishing Guide

Complete guide to publishing the Claude the Gardener static website to AWS S3.

## Architecture Overview

The publishing system consists of three modular scripts:

1. **sync_data.sh** - Syncs data from Raspberry Pi to local machine
2. **generate.py** - Builds static HTML site from data
3. **publish.sh** - Uploads to S3 (only if changes detected)

These are orchestrated by **orchestrate.sh** which chains them together.

## Publishing Modes

### Mode 1: Local Development (Your Mac)

Run the complete pipeline from your machine:

```bash
cd static_site_generator

# Sync data from Pi → build site → publish to S3
./orchestrate.sh --s3-bucket your-bucket-name
```

This will:
1. SSH to Pi and sync latest data
2. Generate fresh HTML from data
3. Check for changes
4. Upload to S3 if changes exist

### Mode 2: Automated on Raspberry Pi

The systemd timer runs the pipeline automatically every 15 minutes:

```bash
# Install the publisher on Pi
sudo bash deploy/install-publisher.sh

# Enable timer
sudo systemctl enable --now gardener-site-publisher.timer

# Check status
systemctl status gardener-site-publisher.timer
systemctl list-timers gardener-site-publisher.timer
```

The timer runs:
```bash
orchestrate.sh --skip-sync \
    --data-dir /home/mcpserver/data \
    --photos-dir /home/mcpserver/photos \
    --s3-bucket <your-bucket>
```

Skips sync because data is already local on the Pi.

## Manual Script Usage

### Sync Data Only

```bash
cd static_site_generator
./sync_data.sh

# Dry run to see what would sync
./sync_data.sh --dry-run
```

### Build Site Only

```bash
cd static_site_generator

# Use default paths
uv run python generate.py

# Custom paths
uv run python generate.py \
    --data-dir /path/to/data \
    --photos-dir /path/to/photos \
    --output-dir /path/to/output
```

### Publish Only

```bash
cd static_site_generator

# Publish to S3
./publish.sh --output-dir ./output --s3-bucket your-bucket-name

# Dry run (shows what would upload)
./publish.sh --output-dir ./output --s3-bucket your-bucket-name --dry-run

# Custom AWS profile
./publish.sh --output-dir ./output --s3-bucket your-bucket-name --aws-profile production
```

### Full Orchestration

```bash
cd static_site_generator

# Complete pipeline
./orchestrate.sh --s3-bucket your-bucket-name

# Skip sync (when running on Pi or data already synced)
./orchestrate.sh --skip-sync --s3-bucket your-bucket-name

# Dry run
./orchestrate.sh --s3-bucket your-bucket-name --dry-run

# Verbose output
./orchestrate.sh --s3-bucket your-bucket-name --verbose
```

## Change Detection

The publish script uses **git** for change detection:

1. Initializes a git repo in `output/` directory (first run)
2. Stages all files: `git add -A`
3. Checks for changes: `git diff --cached --quiet`
4. Only uploads if changes detected
5. Commits after successful upload (audit trail)

**Benefits**:
- No unnecessary S3 writes (saves money)
- Git history shows what changed when
- Simple and reliable

**Note**: The `output/.git/` directory is gitignored - it's only for local change tracking.

## Deployment to Raspberry Pi

### Prerequisites

1. S3 bucket configured (see [S3_SETUP.md](S3_SETUP.md))
2. AWS credentials configured
3. Repository cloned on Pi

### Installation Steps

```bash
# 1. Clone/pull latest code
cd /home/admin/claude-code-the-gardener
git pull

# 2. Run installation script
sudo bash static_site_generator/deploy/install-publisher.sh
```

The script will:
- Create `/home/mcpserver/gardener-publisher/`
- Copy all necessary files
- Install Python dependencies (via uv)
- Install AWS CLI (if not present)
- Set up systemd service and timer
- Set proper permissions

### Configuration

```bash
# 1. Configure AWS credentials
sudo -u mcpserver aws configure --profile default

# 2. Edit environment file
sudo nano /home/mcpserver/gardener-publisher/.env.publish

# Set:
AWS_PROFILE=default
S3_BUCKET=your-bucket-name
```

### Testing

```bash
# Test manually (dry run)
sudo -u mcpserver /home/mcpserver/gardener-publisher/orchestrate.sh \
    --skip-sync \
    --s3-bucket your-bucket-name \
    --dry-run

# Test actual upload
sudo -u mcpserver /home/mcpserver/gardener-publisher/orchestrate.sh \
    --skip-sync \
    --s3-bucket your-bucket-name
```

### Enable Timer

```bash
# Enable and start timer
sudo systemctl enable --now gardener-site-publisher.timer

# Check status
systemctl status gardener-site-publisher.timer
systemctl list-timers gardener-site-publisher.timer

# View logs
journalctl -u gardener-site-publisher -f
```

## Monitoring

### Check Timer Status

```bash
# List all timers (shows next run time)
systemctl list-timers

# Check specific timer
systemctl status gardener-site-publisher.timer

# See when it last ran and next run
systemctl list-timers gardener-site-publisher.timer
```

### View Logs

```bash
# Follow logs in real-time
journalctl -u gardener-site-publisher -f

# Last 50 lines
journalctl -u gardener-site-publisher -n 50

# Logs since yesterday
journalctl -u gardener-site-publisher --since yesterday

# Logs for specific date
journalctl -u gardener-site-publisher --since "2024-01-15" --until "2024-01-16"
```

### Check for Errors

```bash
# Show only errors
journalctl -u gardener-site-publisher -p err

# Last failed run
systemctl status gardener-site-publisher
```

## Troubleshooting

### Timer Not Running

```bash
# Check timer is enabled
systemctl is-enabled gardener-site-publisher.timer

# Enable if not
sudo systemctl enable gardener-site-publisher.timer

# Start timer
sudo systemctl start gardener-site-publisher.timer
```

### Publish Fails

```bash
# Test AWS credentials
sudo -u mcpserver aws s3 ls s3://your-bucket-name

# Test with verbose output
sudo -u mcpserver /home/mcpserver/gardener-publisher/orchestrate.sh \
    --skip-sync \
    --s3-bucket your-bucket-name \
    --verbose

# Check environment file
sudo cat /home/mcpserver/gardener-publisher/.env.publish
```

### No Changes Detected (But Should Be)

```bash
# Check git status in output directory
cd /home/mcpserver/gardener-publisher/output
sudo -u mcpserver git status

# Force reset git tracking
sudo -u mcpserver rm -rf .git
# Next run will re-initialize and detect all files as changed
```

### Build Fails

```bash
# Test generate.py directly
cd /home/mcpserver/gardener-publisher
sudo -u mcpserver uv run python generate.py \
    --data-dir /home/mcpserver/data \
    --photos-dir /home/mcpserver/photos \
    --output-dir ./output

# Check data directory exists
ls -la /home/mcpserver/data
```

## Updating the Publisher

When you update the code:

```bash
# On your development machine, commit and push changes
cd claude-code-the-gardener
git add static_site_generator
git commit -m "Update publisher"
git push

# On Raspberry Pi, pull and reinstall
cd /home/admin/claude-code-the-gardener
git pull
sudo bash static_site_generator/deploy/install-publisher.sh
```

The install script is **idempotent** - safe to run multiple times.

## Performance

### Typical Timing

- **Sync**: ~2-5 seconds (rsync is fast)
- **Build**: ~10-30 seconds (depends on conversation count)
- **Publish**: ~5-20 seconds (depends on changes)
- **Total**: ~20-60 seconds per run

### Resource Usage

- **Memory**: ~200-400MB during build
- **CPU**: Low (mostly I/O bound)
- **Disk**: ~50MB for output directory
- **Network**: ~1-10MB upload per change

### Cost Estimate

With 15-minute publishing schedule:

- **S3 PUT requests**: ~100/day = 3,000/month
- **S3 GET requests**: Depends on visitors
- **Storage**: ~50MB = $0.001/month
- **Data transfer**: Depends on traffic

**Total**: < $0.50/month for S3 operations

## Best Practices

### Local Development

1. Use `--dry-run` to test changes
2. Run `sync_data.sh --dry-run` to preview what will sync
3. Test locally before deploying to Pi
4. Keep `.env.publish` secrets out of git

### Production (Pi)

1. Monitor logs after installation: `journalctl -u gardener-site-publisher -f`
2. Check first few runs are successful
3. Set up CloudFront for HTTPS (optional but recommended)
4. Configure Cloudflare proxy for DDoS protection
5. Backup `.env.publish` file (contains AWS credentials)

### Security

1. **Never commit** `.env.publish` or AWS credentials to git
2. Use IAM user with **minimal S3 permissions**:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:PutObject",
           "s3:GetObject",
           "s3:DeleteObject",
           "s3:ListBucket"
         ],
         "Resource": [
           "arn:aws:s3:::your-bucket-name",
           "arn:aws:s3:::your-bucket-name/*"
         ]
       }
     ]
   }
   ```
3. Rotate AWS credentials periodically
4. Use MFA on your AWS root account

## Architecture Diagram

```
┌─────────────────────┐
│  Raspberry Pi       │
│  ┌───────────────┐  │
│  │ Gardener Agent│◄─┼─── Systemd Timer (every 15 min)
│  └───────┬───────┘  │
│          │          │
│          ▼          │
│  ┌───────────────┐  │
│  │ MCP Server    │  │     ┌─────────────────┐
│  │ - JSONL data  │  │────▶│ Local Machine   │
│  │ - Photos      │  │     │ (development)   │
│  │ - Conversations│ │     └────────┬────────┘
│  └───────────────┘  │              │
└──────────┬──────────┘              │
           │                         │
           │ sync_data.sh            │ sync_data.sh
           ▼                         ▼
    ┌──────────────┐          ┌──────────────┐
    │ generate.py  │          │ generate.py  │
    │ (build site) │          │ (build site) │
    └──────┬───────┘          └──────┬───────┘
           │                         │
           ▼                         ▼
    ┌──────────────┐          ┌──────────────┐
    │ publish.sh   │          │ publish.sh   │
    │ (if changes) │          │ (if changes) │
    └──────┬───────┘          └──────┬───────┘
           │                         │
           └────────┬────────────────┘
                    ▼
             ┌─────────────┐
             │  AWS S3     │
             │  (website)  │
             └──────┬──────┘
                    │
                    ▼
             ┌─────────────┐
             │ Cloudflare  │◄──── Visitors
             │   (proxy)   │
             └─────────────┘
```

## Next Steps

1. Complete [S3 setup](S3_SETUP.md)
2. Test publishing locally
3. Deploy to Raspberry Pi
4. Monitor first automated run
5. Configure Cloudflare proxy
6. Share your site!

## Support

- Report issues: https://github.com/mnbf9rca/claude-code-the-gardener/issues
- View logs: `journalctl -u gardener-site-publisher`
- AWS CLI docs: https://aws.amazon.com/cli/
- S3 website hosting: https://docs.aws.amazon.com/AmazonS3/latest/userguide/WebsiteHosting.html
