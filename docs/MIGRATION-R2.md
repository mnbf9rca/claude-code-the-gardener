# Migration Guide: Git to R2 Data Architecture

This guide walks through migrating from Git-based to R2-based data storage.

## Prerequisites

Before starting:

- ✅ R2 bucket created and accessible
- ✅ rclone installed on Pi (will be configured during Phase 1)
- ✅ GitHub secrets configured (R2_SECRET_KEY) and variables (R2_ACCESS_KEY, R2_ENDPOINT, R2_BUCKET)
- ✅ Current Git sync working (baseline for comparison)

## Phase 1: Deploy R2 Sync (Parallel Operation)

**Goal:** Run R2 sync alongside existing Git sync for validation

### Step 1: Deploy to Pi

```bash
# On Pi
cd /home/gardener-publisher/claude-code-the-gardener
git pull origin feat/r2-data-architecture

# Install rclone if not already installed
sudo apt update && sudo apt install rclone -y
rclone version  # Verify installation

# Install R2 sync
cd static_site_generator/deploy
sudo ./install-r2-sync.sh
```

### Step 2: Validate Installation

```bash
# Check timer is running
sudo systemctl status gardener-r2-sync.timer

# Trigger manual sync
sudo systemctl start gardener-r2-sync.service

# Check logs
journalctl -u gardener-r2-sync -n 50
```

### Step 3: Verify R2 Data

```bash
# Check R2 bucket contents
rclone tree r2-gardener:gardener-data --dirs-only -L 3

# Check manifest
rclone cat r2-gardener:gardener-data/manifests/current.json | jq '.files | length'

# Check first delta log
rclone ls r2-gardener:gardener-data/deltas/ | head
```

**Validation Period:** 1 week

**Success Criteria:**

- R2 sync runs every 15 minutes without errors
- File counts in R2 match local filesystem
- Delta logs capture all changes
- No SD card performance degradation

**Rollback:** If issues arise:

```bash
sudo systemctl stop gardener-r2-sync.timer
sudo systemctl disable gardener-r2-sync.timer
```

## Phase 2: Deploy Summary Generation

**Goal:** Process deltas and generate summaries incrementally

### Step 1: Add GitHub Workflow

Push changes from feat/r2-data-architecture branch.

### Step 2: Validate Summaries

Check GitHub Actions:

- process-deltas.yml runs every 15 min
- Summaries updated in R2
- No errors in workflow logs

**Validation Period:** 1 week

**Success Criteria:**

- Summaries generated correctly
- Incremental updates working
- Metrics match existing parsers

**Rollback:** Disable workflow in GitHub UI

## Phase 3: Switch Site to R2

**Goal:** Site generation uses R2 summaries instead of Git data

### Step 1: Update Site Workflow

Modify .github/workflows/generate-site.yml to fetch from R2.

### Step 2: Validate Site

- Check site builds successfully
- Verify all charts/data display correctly
- Test all pages and functionality

**Validation Period:** 1 week

**Success Criteria:**

- Site displays correctly
- Build time reduced (2-5 min vs 45-60 min)
- No broken features

**Rollback:** Revert workflow to use Git data

## Phase 4: Retire Git Sync (Optional)

**Goal:** Shut down Git-based sync completely

### Step 1: Stop Git Timer

```bash
sudo systemctl stop gardener-data-sync.timer
sudo systemctl disable gardener-data-sync.timer
```

### Step 2: Archive Git Repository

Keep as backup but don't update.

**Rollback:** Re-enable Git timer if needed

## Monitoring

**Key Metrics:**

- R2 upload success rate: Should be >99%
- Sync duration: Should be <5 minutes
- Summary generation time: <1 minute
- Site build time: <5 minutes (down from 45-60)

**Logs to Monitor:**

```bash
# Pi sync logs
journalctl -u gardener-r2-sync -f

# GitHub Actions logs
# Check in GitHub UI → Actions tab
```

## Troubleshooting

### Sync Fails with "Permission Denied"

**Cause:** rclone not configured correctly

**Fix:**

```bash
sudo -u gardener-publisher rclone config
```

### Manifest Shows Wrong File Count

**Cause:** Sync interrupted or partial upload

**Fix:**

```bash
# Manually trigger full sync
sudo systemctl start gardener-r2-sync.service

# Check logs for errors
journalctl -u gardener-r2-sync -n 100
```

### R2 Upload Rate Limit

**Cause:** Too many files uploaded too quickly

**Fix:** Implemented retry logic in sync script. If persistent, increase sync interval.

### "AccessDenied" with CreateBucket Error

**Cause:** rclone missing `no_check_bucket` flag

**Fix:** Reconfigure rclone remote:

```bash
rclone config update r2-gardener no_check_bucket true
```

## Success Metrics

After complete migration:

- ✅ Pi SD card writes: Minimal (tmpfs only)
- ✅ Site build time: 2-5 minutes (down from 45-60)
- ✅ Scalability: 110k+ files supported
- ✅ Cost: ~$6/month
- ✅ Data durability: 11 nines (R2 vs SD card)

## Support

Issues? Check:

1. Logs: `journalctl -u gardener-r2-sync -n 100`
2. R2 access: `rclone lsd r2-gardener:gardener-data`
3. Design doc: `docs/plans/2026-02-10-r2-architecture-design.md`
4. Setup doc: `docs/R2-SETUP.md`
