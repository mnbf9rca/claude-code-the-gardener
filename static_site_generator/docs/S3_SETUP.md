# AWS S3 Static Website Hosting Setup

This guide walks you through setting up an S3 bucket to host the Claude the Gardener static website.

## Prerequisites

- AWS account
- AWS CLI installed and configured
- Basic knowledge of AWS S3

## Step 1: Create S3 Bucket

Choose a globally unique bucket name (e.g., `claude-the-gardener` or `my-gardener-site`).

```bash
# Set your bucket name
export BUCKET_NAME="claude-the-gardener"
export AWS_REGION="us-east-1"  # Change to your preferred region

# Create bucket
aws s3 mb s3://$BUCKET_NAME --region $AWS_REGION
```

## Step 2: Configure Static Website Hosting

Enable static website hosting on the bucket:

```bash
# Configure website hosting
aws s3 website s3://$BUCKET_NAME --index-document index.html --error-document index.html
```

This sets:
- **Index document**: `index.html` (homepage)
- **Error document**: `index.html` (fallback for 404s, works with client-side routing)

## Step 3: Set Bucket Policy for Public Read Access

The website needs to be publicly readable. Create a bucket policy:

```bash
# Create policy file
cat > /tmp/bucket-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
    }
  ]
}
EOF

# Apply policy
aws s3api put-bucket-policy --bucket $BUCKET_NAME --policy file:///tmp/bucket-policy.json
```

## Step 4: Disable Block Public Access

By default, S3 blocks public access. You need to disable this for website hosting:

```bash
aws s3api put-public-access-block \
    --bucket $BUCKET_NAME \
    --public-access-block-configuration \
    "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
```

## Step 5: Get Website Endpoint

Your website will be available at the S3 website endpoint:

```bash
# Website endpoint format (depends on region)
echo "http://${BUCKET_NAME}.s3-website-${AWS_REGION}.amazonaws.com"
```

For `us-east-1`, it's:
```
http://claude-the-gardener.s3-website-us-east-1.amazonaws.com
```

## Step 6: Configure AWS CLI Profile (on Raspberry Pi)

On the Raspberry Pi, configure AWS credentials:

```bash
# As mcpserver user
sudo -u mcpserver aws configure --profile default

# Enter when prompted:
# AWS Access Key ID: <your-access-key>
# AWS Secret Access Key: <your-secret-key>
# Default region name: us-east-1 (or your chosen region)
# Default output format: json
```

## Step 7: Update .env.publish

Edit the environment file:

```bash
sudo nano /home/mcpserver/gardener-publisher/.env.publish
```

Set:
```bash
AWS_PROFILE=default
S3_BUCKET=claude-the-gardener  # Your bucket name
```

## Step 8: Test Upload

Test the publishing pipeline:

```bash
# Dry run to verify configuration
sudo -u mcpserver /home/mcpserver/gardener-publisher/orchestrate.sh \
    --skip-sync \
    --s3-bucket claude-the-gardener \
    --dry-run

# Actual upload
sudo -u mcpserver /home/mcpserver/gardener-publisher/orchestrate.sh \
    --skip-sync \
    --s3-bucket claude-the-gardener
```

## Optional: CloudFront Distribution (HTTPS + CDN)

If you want HTTPS and better performance, set up a CloudFront distribution:

### Create CloudFront Distribution

1. Go to AWS Console → CloudFront → Create Distribution
2. **Origin domain**: Select your S3 bucket (use the website endpoint, not the bucket itself)
3. **Origin path**: Leave empty
4. **Viewer protocol policy**: Redirect HTTP to HTTPS
5. **Allowed HTTP methods**: GET, HEAD, OPTIONS
6. **Cache policy**: CachingOptimized
7. **Price class**: Use only North America and Europe (or your preference)
8. Click **Create Distribution**

### Configure Custom Domain (Optional)

If you have a domain (e.g., `gardener.example.com`):

1. Request SSL certificate in AWS Certificate Manager (ACM) for your domain
2. Add the domain to CloudFront distribution settings
3. Create CNAME record in your DNS pointing to CloudFront domain

### Cloudflare Proxy

If you're proxying through Cloudflare:

1. In Cloudflare DNS, create a CNAME record:
   ```
   Type: CNAME
   Name: gardener (or @)
   Target: your-cloudfront-distribution.cloudfront.net (or S3 endpoint)
   Proxy status: Proxied (orange cloud)
   ```

2. In Cloudflare → SSL/TLS → Overview:
   - Set mode to **Full** (not Full Strict, since S3 uses AWS certs)

## Troubleshooting

### 403 Forbidden

- Check bucket policy is correct and applied
- Verify Block Public Access settings are disabled
- Ensure files have correct permissions in S3

### 404 Not Found

- Verify `index.html` exists in bucket root
- Check S3 website hosting is enabled
- Confirm you're using the website endpoint (not bucket endpoint)

### Upload Fails

- Check AWS credentials are correct: `aws s3 ls`
- Verify IAM user/role has S3 write permissions
- Check bucket name in `.env.publish` is correct

### Slow Updates

- CloudFront caching can delay updates (default 24h)
- Invalidate CloudFront cache: `aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"`
- Or set shorter cache TTL in CloudFront distribution settings

## Cost Estimate

For a hobby project with moderate traffic:

- **S3 Storage**: $0.023/GB per month (~$0.05 for 2GB of HTML/CSS/images)
- **S3 Requests**: $0.0004 per 1,000 GET requests (~$0.20 for 500k views/month)
- **S3 Data Transfer**: First 1GB free, then $0.09/GB (~$0.90 for 10GB/month)
- **CloudFront** (optional): First 1TB free, then $0.085/GB

**Total monthly cost**: ~$1-5 depending on traffic (without CloudFront)

## Security Note

This setup makes your website **publicly accessible** (read-only). This is normal for a static website. Your plant care data is public.

If you want to restrict access:
- Use CloudFront with signed URLs
- Add Lambda@Edge for authentication
- Use S3 bucket policies with IP restrictions

For a hobby project documenting plant care, public access is typically fine.

## Next Steps

Once S3 is configured:
1. Enable the systemd timer: `sudo systemctl enable --now gardener-site-publisher.timer`
2. Monitor first run: `journalctl -u gardener-site-publisher -f`
3. Verify site updates automatically every 15 minutes

See [PUBLISHING.md](PUBLISHING.md) for complete publishing workflow documentation.
