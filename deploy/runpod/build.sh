#!/bin/bash
# GB10에서 실행: Docker 이미지 빌드
# 사용법: cd /home/swiri021/ComfyUI && bash /home/swiri021/ella-telegram/deploy/runpod/build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMFYUI_DIR="/home/swiri021/ComfyUI"
IMAGE_NAME="ella-comfyui-serverless"
IMAGE_TAG="latest"

echo "=== Ella ComfyUI RunPod Serverless 빌드 ==="
echo "ComfyUI 디렉토리: $COMFYUI_DIR"
echo "Dockerfile: $SCRIPT_DIR/Dockerfile"

# handler.py를 ComfyUI 디렉토리에 복사 (빌드 컨텍스트 내에 있어야 함)
cp "$SCRIPT_DIR/handler.py" "$COMFYUI_DIR/handler.py"

# ComfyUI 디렉토리에서 빌드 (COPY가 models/ 참조)
cd "$COMFYUI_DIR"

docker build \
    -f "$SCRIPT_DIR/Dockerfile" \
    -t "$IMAGE_NAME:$IMAGE_TAG" \
    .

# 임시 복사 정리
rm -f "$COMFYUI_DIR/handler.py"

echo ""
echo "=== 빌드 완료 ==="
echo "이미지: $IMAGE_NAME:$IMAGE_TAG"
echo "크기: $(docker images $IMAGE_NAME:$IMAGE_TAG --format '{{.Size}}')"
echo ""
echo "RunPod에 푸시하려면:"
echo "  docker tag $IMAGE_NAME:$IMAGE_TAG <your-registry>/$IMAGE_NAME:$IMAGE_TAG"
echo "  docker push <your-registry>/$IMAGE_NAME:$IMAGE_TAG"
