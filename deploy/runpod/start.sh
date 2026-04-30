#!/bin/bash
# Download model checkpoints from S3, then launch the worker entry-point.
echo "=== S3 model download ==="
python /s3_download.py

echo "=== Starting ComfyUI worker ==="
python /handler.py
