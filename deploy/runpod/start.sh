#!/bin/bash
# S3 모델 다운로드 후 공식 워커 시작
echo "=== S3 모델 다운로드 ==="
python /s3_download.py

echo "=== ComfyUI 워커 시작 ==="
# 공식 워커의 기본 엔트리포인트 실행
python /handler.py
