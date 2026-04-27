"""S3에서 ComfyUI 모델 파일 병렬 다운로드. 시작 시 한번 실행."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3

S3_BUCKET = os.getenv("S3_BUCKET", "ella-project-comfyui-bucket")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
MODELS_DIR = os.getenv("COMFYUI_MODELS_DIR", "/app/ComfyUI/models")
MAX_WORKERS = int(os.getenv("S3_DOWNLOAD_WORKERS", "4"))


def _download_one(s3, key, size):
    """단일 파일 다운로드. 이미 존재하고 사이즈 같으면 스킵."""
    local_path = os.path.join(MODELS_DIR, key)

    if os.path.exists(local_path) and os.path.getsize(local_path) == size:
        print(f"  스킵: {key}")
        return key, False

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    size_mb = size / 1_000_000
    print(f"  다운로드 시작: {key} ({size_mb:.0f}MB)")
    s3.download_file(S3_BUCKET, key, local_path)
    print(f"  다운로드 완료: {key}")
    return key, True


def download_models():
    s3 = boto3.client(
        "s3",
        region_name=S3_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
    )

    print(f"S3 모델 동기화: s3://{S3_BUCKET} → {MODELS_DIR} (workers={MAX_WORKERS})")

    # 파일 목록 수집
    files = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET):
        for obj in page.get("Contents", []):
            files.append((obj["Key"], obj["Size"]))

    total_mb = sum(s for _, s in files) / 1_000_000
    print(f"  총 {len(files)}개 파일, {total_mb:.0f}MB")

    # 병렬 다운로드 (각 스레드가 별도 S3 클라이언트 사용)
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
                print(f"  에러: {futures[future]} — {e}")

    print(f"S3 모델 동기화 완료 (다운로드: {downloaded}, 스킵: {len(files) - downloaded})")


if __name__ == "__main__":
    download_models()
