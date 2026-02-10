# R2 Setup Guide

## Prerequisites Checklist

Complete these steps before deploying the R2 sync script to the Pi.

---

## Step 1: Create R2 Bucket

1. Log into [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Navigate to **R2 Object Storage** → **Create bucket**
3. Configuration:
   - **Bucket name:** `gardener-data`
   - **Location:** Automatic (let Cloudflare choose optimal location)
   - **Storage class:** Standard
4. Click **Create bucket**

**Expected result:** Bucket `gardener-data` created successfully

---

## Step 2: Generate R2 API Tokens

1. In Cloudflare Dashboard, go to **R2** → **Manage R2 API Tokens**
2. Click **Create API Token**
3. Configuration:
   - **Token name:** `gardener-pi-sync`
   - **Permissions:** Object Read & Write
   - **TTL:** No expiry (or set expiry if preferred)
   - **Bucket scope:** Apply to specific buckets only
   - **Select buckets:** `gardener-data`
4. Click **Create API Token**
5. **IMPORTANT:** Save these credentials immediately (shown only once):
   ```
   Access Key ID: <COPY_THIS>
   Secret Access Key: <COPY_THIS>
   Endpoint: https://<account_id>.r2.cloudflarestorage.com
   ```

**Expected result:** API credentials saved securely

---

## Step 3: Configure GitHub Repository Secrets

1. Go to GitHub repository → **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets and Variables (click **New repository secret** for each):

   | Secret Name | Value |
   |-------------|-------|
   | `R2_SECRET_KEY` | Secret Access Key from Step 2 |

   | Variable Name | Value |
   |-------------|-------|
   | `R2_ACCESS_KEY` | Access Key ID from Step 2 |
   | `R2_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |
   | `R2_BUCKET` | `gardener-data` |

**Expected result:** All 4 secrets configured in GitHub

---

## Step 4: Install and Test R2 Access with rclone

### Install rclone

On your **development machine** (and later on Pi):

```bash
# Debian/Ubuntu/Raspberry Pi OS
sudo apt update && sudo apt install rclone -y

# macOS
brew install rclone

# Verify installation
rclone version
```

### Configure and Test

```bash
# Configure rclone remote
# Note: no_check_bucket is required for R2 bucket-scoped tokens
rclone config create r2-gardener s3 \
  provider Cloudflare \
  access_key_id <R2_ACCESS_KEY> \
  secret_access_key <R2_SECRET_KEY> \
  endpoint https://<account_id>.r2.cloudflarestorage.com \
  no_check_bucket true

# Test bucket access
rclone lsd r2-gardener:gardener-data

# Test write (creates test file)
echo "test" | rclone rcat r2-gardener:gardener-data/test.txt

# Test read
rclone cat r2-gardener:gardener-data/test.txt

# Clean up test file
rclone delete r2-gardener:gardener-data/test.txt
```

**Expected output:**

- `lsd`: Shows empty bucket (no directories yet)
- `rcat`: No output (success)
- `cat`: Prints "test"
- `delete`: No output (success)

---

## Bucket Information

Once configured:

- **Bucket name:** gardener-data
- **Region:** Automatic (Cloudflare-optimized)
- **Endpoint:** `https://<account_id>.r2.cloudflarestorage.com`

## Access Credentials Storage

Credentials will be stored in:

- **Pi:** `/home/gardener-publisher/.config/rclone/rclone.conf`
- **GitHub:** Repository Secrets (for GitHub Actions)

## Bucket Structure

See detailed structure in: `docs/plans/2026-02-10-r2-architecture-design.md`

Key directories:

- `raw/` - Raw data files (photos, transcripts, logs, data)
- `manifests/` - State tracking (current.json, daily snapshots)
- `deltas/` - Change events for audit trail
- `summaries/` - Derived data (metrics, indexes)

---

## Verification

After completing all steps, verify:

- ✅ R2 bucket `gardener-data` exists in Cloudflare dashboard
- ✅ API token `gardener-pi-sync` created with Read & Write permissions
- ✅ All 4 GitHub secrets configured
- ✅ rclone can list, read, and write to bucket

---

## Next Steps

Once R2 is configured:

1. Run `scripts/init-r2-bucket.sh` to create folder structure
2. Deploy sync script to Pi using `static_site_generator/deploy/install-r2-sync.sh`

## Troubleshooting

### "Access Denied" errors

**Cause:** API token doesn't have correct permissions

**Fix:**

1. Go to Cloudflare R2 → Manage R2 API Tokens
2. Verify token has "Object Read & Write" permissions
3. Verify token scope includes `gardener-data` bucket
4. If needed, create new token with correct permissions

### "Bucket not found" errors

**Cause:** Endpoint URL incorrect or bucket doesn't exist

**Fix:**
1. Verify bucket name is exactly `gardener-data` (case-sensitive)
2. Verify endpoint URL includes your account ID
3. Check bucket exists in Cloudflare dashboard

### rclone connection timeout

**Cause:** Network connectivity or firewall issues

**Fix:**
1. Check internet connection
2. Verify firewall allows HTTPS (port 443) outbound
3. Try from different network to isolate issue

---

## Cost Monitoring

Once operational, monitor costs in Cloudflare Dashboard → R2 → Usage

**Expected costs** (at 100GB, 110k files/year):

- Storage: ~$1.50/month
- Class A operations (writes): ~$4.32/month
- Class B operations (reads): ~$0.05/month
- **Total: ~$6/month**

See detailed cost analysis in: `docs/plans/2026-02-10-r2-architecture-design.md`
