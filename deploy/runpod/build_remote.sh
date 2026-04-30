#!/bin/bash
# Docker build script meant to run from inside an x86_64 RunPod pod's web
# terminal — copy-paste the file in and run it. Generates a self-contained
# Dockerfile + handler.py + builds + pushes the image to Docker Hub.

set -e

echo "=== ella-chat-publish ComfyUI Docker build (x86_64) ==="

# 1. Working directory
cd /workspace
mkdir -p ella-build && cd ella-build

# 2. Write the Dockerfile
cat > Dockerfile << 'DOCKERFILE'
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    git wget libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && ln -s /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI
WORKDIR /app/ComfyUI

RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app/ComfyUI/custom_nodes
RUN git clone https://github.com/rgthree/rgthree-comfy.git && \
    cd rgthree-comfy && pip install --no-cache-dir -r requirements.txt 2>/dev/null || true

WORKDIR /app/ComfyUI
RUN pip install --no-cache-dir runpod

RUN mkdir -p /app/ComfyUI/models/checkpoints/illustrious

RUN wget -q --show-progress -O /app/ComfyUI/models/checkpoints/illustrious/oneObsession_v20Bold.safetensors \
    "https://civitai.com/api/download/models/2657925"

RUN wget -q --show-progress -O /app/ComfyUI/models/checkpoints/illustrious/pornmasterAnime_ilV5.safetensors \
    "https://civitai.com/api/download/models/2518034"

RUN wget -q --show-progress -O /app/ComfyUI/models/checkpoints/illustrious/novaAnimeXL_ilV170.safetensors \
    "https://huggingface.co/SiE69/Illoustrious_Checkpoint_Collection/resolve/main/novaAnimeXL_ilV170.safetensors"

RUN wget -q --show-progress -O /app/ComfyUI/models/checkpoints/illustrious/celestrealAnimeSemi_v30.safetensors \
    "https://civitai.com/api/download/models/2550245"

WORKDIR /app
COPY handler.py /app/handler.py

CMD ["python", "/app/handler.py"]
DOCKERFILE

# 3. Write handler.py
cat > handler.py << 'HANDLER'
import json
import os
import subprocess
import time
import base64

import runpod
import requests

COMFYUI_PORT = 8188
COMFYUI_URL = f"http://127.0.0.1:{COMFYUI_PORT}"

comfyui_process = None


def start_comfyui():
    global comfyui_process
    if comfyui_process is not None:
        return

    comfyui_process = subprocess.Popen(
        [
            "python", "main.py",
            "--listen", "127.0.0.1",
            "--port", str(COMFYUI_PORT),
            "--reserve-vram", "0",
            "--gpu-only",
        ],
        cwd="/app/ComfyUI",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for _ in range(120):
        try:
            resp = requests.get(f"{COMFYUI_URL}/queue", timeout=2)
            if resp.status_code == 200:
                print("ComfyUI started successfully")
                return
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("ComfyUI failed to start (120s timeout)")


def handler(event):
    start_comfyui()

    workflow = event["input"].get("workflow")
    if not workflow:
        return {"error": "workflow is required"}

    if isinstance(workflow, str):
        workflow = json.loads(workflow)

    try:
        resp = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]

        for _ in range(360):
            hist_resp = requests.get(
                f"{COMFYUI_URL}/history/{prompt_id}",
                timeout=10,
            )
            hist_resp.raise_for_status()
            data = hist_resp.json()

            if prompt_id in data:
                outputs = data[prompt_id].get("outputs", {})
                save_node = outputs.get("30", {})
                images = save_node.get("images", [])

                if not images:
                    return {"error": "no images in output"}

                image_info = images[0]
                filename = image_info["filename"]
                subfolder = image_info.get("subfolder", "")
                img_type = image_info.get("type", "output")

                view_resp = requests.get(
                    f"{COMFYUI_URL}/view",
                    params={"filename": filename, "subfolder": subfolder, "type": img_type},
                    timeout=30,
                )
                view_resp.raise_for_status()

                image_b64 = base64.b64encode(view_resp.content).decode("utf-8")
                return {"image_base64": image_b64}

            time.sleep(1)

        return {"error": "timeout (360s)"}

    except Exception as e:
        return {"error": str(e)}


runpod.serverless.start({"handler": handler})
HANDLER

echo "=== Files staged ==="
echo "Dockerfile + handler.py written"

# 4. Install Docker if it isn't already on the pod.
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
fi

# 5. Build the image
echo "=== Starting Docker build ==="
docker build -t ellaadmin/ella-comfyui-serverless:latest .

echo ""
echo "=== Build complete ==="
docker images ellaadmin/ella-comfyui-serverless:latest

# 6. Push instructions (login + push are interactive; do them manually).
echo "=== Docker Hub login ==="
echo "Run these commands to log in and push:"
echo "  docker login -u ellaadmin"
echo "  docker push ellaadmin/ella-comfyui-serverless:latest"
