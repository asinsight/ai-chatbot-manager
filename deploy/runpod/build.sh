#!/bin/bash
# Local build helper for the RunPod serverless image.
# Usage:
#   cd /path/to/ComfyUI && bash /path/to/this/repo/deploy/runpod/build.sh
# The script expects to be invoked from a host that has both Docker and a
# local ComfyUI checkout (the build context needs the ComfyUI models/ tree).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
IMAGE_NAME="ella-comfyui-serverless"
IMAGE_TAG="latest"

echo "=== Building ella-chat-publish ComfyUI RunPod serverless image ==="
echo "ComfyUI directory: $COMFYUI_DIR"
echo "Dockerfile:        $SCRIPT_DIR/Dockerfile"

# Copy handler.py into the ComfyUI directory so it lives inside the build context.
cp "$SCRIPT_DIR/handler.py" "$COMFYUI_DIR/handler.py"

# Build from the ComfyUI directory (so the Dockerfile's COPY can reach models/).
cd "$COMFYUI_DIR"

docker build \
    -f "$SCRIPT_DIR/Dockerfile" \
    -t "$IMAGE_NAME:$IMAGE_TAG" \
    .

# Clean up the temporary copy.
rm -f "$COMFYUI_DIR/handler.py"

echo ""
echo "=== Build complete ==="
echo "Image: $IMAGE_NAME:$IMAGE_TAG"
echo "Size:  $(docker images $IMAGE_NAME:$IMAGE_TAG --format '{{.Size}}')"
echo ""
echo "To push to a registry:"
echo "  docker tag $IMAGE_NAME:$IMAGE_TAG <your-registry>/$IMAGE_NAME:$IMAGE_TAG"
echo "  docker push <your-registry>/$IMAGE_NAME:$IMAGE_TAG"
