"""RunPod Serverless Handler — ComfyUI 이미지 생성.

RunPod Serverless endpoint에서 실행되며,
ComfyUI를 서브프로세스로 실행하고 API를 통해 이미지를 생성한다.
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
    """ComfyUI 서버를 백그라운드로 시작한다."""
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

    # ComfyUI 시작 대기
    for _ in range(120):
        try:
            resp = requests.get(f"{COMFYUI_URL}/queue", timeout=2)
            if resp.status_code == 200:
                print("ComfyUI 시작 완료")
                return
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("ComfyUI 시작 실패 (120초 타임아웃)")


def handler(event):
    """RunPod handler — 워크플로우 실행 + 이미지 반환.

    Input:
        event["input"]["workflow"]: ComfyUI 워크플로우 JSON (프롬프트 삽입 완료)

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
        # 1. /prompt에 POST
        resp = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]

        # 2. /history로 완료 대기 (최대 360초)
        for _ in range(360):
            hist_resp = requests.get(
                f"{COMFYUI_URL}/history/{prompt_id}",
                timeout=10,
            )
            hist_resp.raise_for_status()
            data = hist_resp.json()

            if prompt_id in data:
                # 완료
                outputs = data[prompt_id].get("outputs", {})
                save_node = outputs.get("30", {})
                images = save_node.get("images", [])

                if not images:
                    return {"error": "no images in output"}

                image_info = images[0]
                filename = image_info["filename"]
                subfolder = image_info.get("subfolder", "")
                img_type = image_info.get("type", "output")

                # 이미지 다운로드
                view_resp = requests.get(
                    f"{COMFYUI_URL}/view",
                    params={"filename": filename, "subfolder": subfolder, "type": img_type},
                    timeout=30,
                )
                view_resp.raise_for_status()

                # base64 인코딩하여 반환
                image_b64 = base64.b64encode(view_resp.content).decode("utf-8")
                return {"image_base64": image_b64}

            time.sleep(1)

        return {"error": "timeout (360s)"}

    except Exception as e:
        return {"error": str(e)}


runpod.serverless.start({"handler": handler})
