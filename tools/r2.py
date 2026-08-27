"""Cloudflare R2 client for the hosted deployment's evidence files. R2 is
S3-compatible, so this is just the standard boto3 S3 client pointed at
R2's endpoint. Only used when R2_ACCOUNT_ID (and friends) are set --
local pipeline runs and the local static dashboard build keep reading
data/real_docs/ straight off disk, see render_evidence.render_evidence.

Object keys mirror the same relative-from-repo-root path already stored
in each transaction's evidence_file column (e.g.
"data/real_docs/SandBox-FI/checks/receipt_042.pdf"), so no database
changes are needed when moving evidence storage from local disk to R2 --
see scripts/upload_evidence_to_r2.py.
"""
import os


def is_configured():
    return bool(os.environ.get("R2_ACCOUNT_ID"))


def _client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


class NotFound(Exception):
    """Raised by fetch_object when the key doesn't exist in the bucket."""


def fetch_object(key):
    """Returns the raw bytes stored at `key` in the configured bucket.
    Raises NotFound if the key doesn't exist."""
    from botocore.exceptions import ClientError
    try:
        obj = _client().get_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise NotFound(key) from e
        raise
    return obj["Body"].read()


def upload_object(key, data):
    _client().put_object(Bucket=os.environ["R2_BUCKET_NAME"], Key=key, Body=data)
