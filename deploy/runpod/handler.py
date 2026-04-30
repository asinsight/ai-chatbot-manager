"""RunPod Serverless handler — ComfyUI image generation.

Runs as the entry-point of a RunPod Serverless endpoint. Spawns ComfyUI as a
subprocess and drives it via its HTTP API to generate one image per request.
"""

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
    """Spawn the ComfyUI server in the background (idempotent)."""
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

    # Wait for ComfyUI to come up.
    for _ in range(120):
        try:
            resp = requests.get(f"{COMFYUI_URL}/queue", timeout=2)
            if resp.status_code == 200:
                print("ComfyUI ready")
                return
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("ComfyUI failed to start within 120s")


def handler(event):
    """RunPod handler — run a workflow and return the rendered image.

    Input:
        event["input"]["workflow"]: ComfyUI workflow JSON (prompts already substituted)

    Output:
        {"image_base64": "...", "seed": 12345}
    """
    start_comfyui()

    workflow = event["input"].get("workflow")
    if not workflow:
        return {"error": "workflow is required"}

    if isinstance(workflow, str):
        workflow = json.loads(workflow)

    try:
        # 1. POST the workflow to /prompt.
        resp = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]

        # 2. Poll /history for completion (up to 360s).
        for _ in range(360):
            hist_resp = requests.get(
                f"{COMFYUI_URL}/history/{prompt_id}",
                timeout=10,
            )
            hist_resp.raise_for_status()
            data = hist_resp.json()

            if prompt_id in data:
                # Workflow finished.
                outputs = data[prompt_id].get("outputs", {})
                save_node = outputs.get("30", {})
                images = save_node.get("images", [])

                if not images:
                    return {"error": "no images in output"}

                image_info = images[0]
                filename = image_info["filename"]
                subfolder = image_info.get("subfolder", "")
                img_type = image_info.get("type", "output")

                # Fetch the image bytes.
                view_resp = requests.get(
                    f"{COMFYUI_URL}/view",
                    params={"filename": filename, "subfolder": subfolder, "type": img_type},
                    timeout=30,
                )
                view_resp.raise_for_status()

                # Base64-encode + return.
                image_b64 = base64.b64encode(view_resp.content).decode("utf-8")
                return {"image_base64": image_b64}

            time.sleep(1)

        return {"error": "timeout (360s)"}

    except Exception as e:
        return {"error": str(e)}


runpod.serverless.start({"handler": handler})
