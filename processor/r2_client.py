"""S3-compatible Cloudflare R2 client utilities."""
import json
import os

import boto3
from botocore.exceptions import ClientError


def get_s3_client():
    """Create boto3 S3 client configured for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def get_json(s3, bucket: str, key: str, default=None):
    """Download and parse JSON from R2. Returns default if key not found."""
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return default
        raise


def put_json(s3, bucket: str, key: str, data) -> None:
    """Serialise data to JSON and upload to R2."""
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2, default=str).encode(),
        ContentType="application/json",
    )


def list_objects(s3, bucket: str, prefix: str) -> list[dict]:
    """List all objects under prefix, handling pagination."""
    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return objects


def get_jsonl_lines(s3, bucket: str, key: str) -> list[dict]:
    """Download a JSONL file and parse each line. Skips blank/malformed lines."""
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        lines = []
        for raw in obj["Body"].read().decode().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                print(f"WARNING: skipping malformed JSONL line in {bucket}/{key}: {raw[:120]!r}", flush=True)
        return lines
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return []
        raise
