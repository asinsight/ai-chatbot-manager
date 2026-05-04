"""Parallel-download ComfyUI model files from S3. Runs once at container start."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3

S3_BUCKET = os.getenv("S3_BUCKET", "ella-project-comfyui-bucket")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
MODELS_DIR = os.getenv("COMFYUI_MODELS_DIR", "/app/ComfyUI/models")
MAX_WORKERS = int(os.getenv("S3_DOWNLOAD_WORKERS", "4"))


def _download_one(s3, key, size):
    """Download a single object. Skip if a same-sized local copy already exists."""
    local_path = os.path.join(MODELS_DIR, key)

    if os.path.exists(local_path) and os.path.getsize(local_path) == size:
        print(f"  skip: {key}")
        return key, False

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    size_mb = size / 1_000_000
    print(f"  downloading: {key} ({size_mb:.0f}MB)")
    s3.download_file(S3_BUCKET, key, local_path)
    print(f"  downloaded:  {key}")
    return key, True


def download_models():
    s3 = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
    )

    print(f"S3 model sync: s3://{S3_BUCKET} -> {MODELS_DIR} (workers={MAX_WORKERS})")

    # Collect the object list.
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET):
        for obj in page.get("Contents", []):
            files.append((obj["Key"], obj["Size"]))

    total_mb = sum(s for _, s in files) / 1_000_000
    print(f"  {len(files)} files, {total_mb:.0f}MB total")

    # Download in parallel (each worker thread uses its own S3 client).
    downloaded = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for key, size in files:
            thread_s3 = boto3.client(
                "s3",
                region_name=S3_REGION,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            )
            futures[executor.submit(_download_one, thread_s3, key, size)] = key

        for future in as_completed(futures):
            try:
                key, was_downloaded = future.result()
                if was_downloaded:
                    downloaded += 1
            except Exception as e:
                print(f"  error: {futures[future]} -- {e}")

    print(f"S3 model sync done (downloaded: {downloaded}, skipped: {len(files) - downloaded})")


if __name__ == "__main__":
    download_models()
