import asyncio
import base64
import json
import logging
import os
import random
import tempfile
from copy import deepcopy
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# 프로젝트 루트 디렉토리 (src/ 상위)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 워크플로우 경로 (환경변수로 변경 가능)
DEFAULT_WORKFLOW_PATH = "comfyui_workflow/main_character_build.json"

# anchor 이미지를 사용하는 워크플로우 목록 (IPAdapter FaceID 포함)
_ANCHOR_WORKFLOWS = {"main_character_build_archived.json"}

# 이미지 생성 완료 대기 최대 시간 (초)
MAX_WAIT_SECONDS = 360

# ComfyUI 큐 최대 허용 수
COMFYUI_MAX_QUEUE = int(os.getenv("COMFYUI_MAX_QUEUE", "10"))

# 폴링 간격 (초)
POLL_INTERVAL = 1

# 마지막 사용 시드 (이미지 봇에서 참조)
last_used_seed: int = 0

# 현재 로드된 체크포인트 (이미지 봇에서 참조)
current_loaded_checkpoint: str = ""

# ── RunPod Serverless 설정 ──
runpod_enabled: bool = False
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")
RUNPOD_MAX_QUEUE = int(os.getenv("RUNPOD_MAX_QUEUE", "3"))
RUNPOD_API_BASE = "https://api.runpod.ai/v2"

# 글로벌 embedding prefix (모든 모델 공통)
EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos"
EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazynsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"

# 모델별 프롬프트 prefix
MODEL_PREFIXES = {
    "illustrious/oneObsession_v20Bold.safetensors": {
        "pos": "masterpiece, best quality, amazing quality, very awa, absurdres, newest, very aesthetic, depth of field, highres",
        "neg": "worst quality, normal quality, anatomical nonsense, bad anatomy, interlocked fingers, extra fingers, watermark, simple background, transparent, low quality, logo, text, signature",
    },
    "illustrious/JANKUTrainedChenkinNoobai_v777.safetensors": {
        # NoobAI/JANKU 권장 quality trigger (Civitai 모델 카드 + NoobAI 공식 가이드)
        "pos": "masterpiece, best quality, amazing quality, newest, absurdres, very aesthetic, highres, year 2026",
        "neg": "worst quality, low quality, lowres, bad anatomy, bad hands, mutated hands, watermark, signature, logo, text, simple background",
    },
}

RESOLUTION_MAP = {
    "portrait": (832, 1216),        # 상반신, cowboy shot — 가장 일반적
    "tall_portrait": (768, 1344),   # 전신, standing full body
    "narrow": (704, 1408),          # 좁고 긴 전신
    "landscape": (1216, 832),       # 누운 장면, 와이드
    "wide": (1536, 1024),           # 넓은 배경, 풍경
    "large_portrait": (1024, 1536), # 고해상도 세로
}


async def check_queue() -> dict:
    """ComfyUI 큐 상태 조회. Returns {"running": int, "pending": int}"""
    comfyui_url = os.getenv("COMFYUI_URL", "http://localhost:8188").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{comfyui_url}/queue")
            resp.raise_for_status()
            data = resp.json()
            running = len(data.get("queue_running", []))
            pending = len(data.get("queue_pending", []))
            return {"running": running, "pending": pending}
    except Exception as e:
        logger.error("ComfyUI 큐 조회 실패: %s", e)
        return {"running": -1, "pending": -1, "error": str(e)}


def load_workflow(path: str = DEFAULT_WORKFLOW_PATH) -> dict:
    """워크플로우 JSON 파일 로드

    Args:
        path: 프로젝트 루트 기준 상대 경로 또는 절대 경로

    Returns:
        워크플로우 dict
    """
    workflow_path = Path(path)
    if not workflow_path.is_absolute():
        workflow_path = PROJECT_ROOT / workflow_path

    with open(workflow_path, "r", encoding="utf-8") as f:
        return json.load(f)


def inject_prompts(workflow: dict, pos_prompt: str, neg_prompt: str) -> dict:
    """워크플로우에 프롬프트를 삽입

    노드 "4" (Positive CLIPTextEncode)의 %prompt% → pos_prompt
    노드 "5" (Negative CLIPTextEncode)의 %negative_prompt% → neg_prompt

    Args:
        workflow: 원본 워크플로우 dict
        pos_prompt: 긍정 프롬프트
        neg_prompt: 부정 프롬프트

    Returns:
        프롬프트가 삽입된 워크플로우 dict (deepcopy)
    """
    wf = deepcopy(workflow)
    wf["4"]["inputs"]["text"] = wf["4"]["inputs"]["text"].replace("%prompt%", pos_prompt)
    wf["5"]["inputs"]["text"] = wf["5"]["inputs"]["text"].replace("%negative_prompt%", neg_prompt)
    return wf


def apply_lora_overrides(workflow: dict, lora_overrides: dict | None) -> dict:
    """Power Lora Loader (rgthree) 노드 131의 슬롯 on/off / strength override 적용.

    Args:
        workflow: load_workflow() 결과 dict
        lora_overrides: {"lora_N": {"on": bool, "strength": float}} 형식.
                        None 또는 빈 dict이면 워크플로우 기본값 그대로 사용.

    Returns:
        modified workflow dict (in-place 수정).
    """
    if not lora_overrides:
        return workflow
    node = workflow.get("131", {}).get("inputs", {})
    if not node:
        logger.warning("apply_lora_overrides: 노드 131 없음 — 스킵")
        return workflow
    for slot_key, override in lora_overrides.items():
        if not slot_key.startswith("lora_"):
            continue
        if slot_key not in node:
            logger.warning(
                "apply_lora_overrides: %s 슬롯이 워크플로우에 없음 — 스킵 (override=%s)",
                slot_key, override,
            )
            continue
        if not isinstance(override, dict):
            continue
        if "on" in override:
            node[slot_key]["on"] = bool(override["on"])
        if "strength" in override:
            node[slot_key]["strength"] = float(override["strength"])
        logger.info(
            "LoRA override applied: %s on=%s strength=%s lora=%s",
            slot_key, node[slot_key].get("on"), node[slot_key].get("strength"),
            node[slot_key].get("lora", "?"),
        )
    return workflow


async def check_runpod_health() -> dict:
    """RunPod Serverless endpoint 헬스 체크.

    Returns:
        헬스 정보 dict. 실패 시 {"error": str}.
        성공 시 예: {"workers": {"idle": 1, "ready": 1, "running": 0, ...}, "jobs": {"inQueue": 0, "inProgress": 0, ...}}
    """
    if not RUNPOD_API_KEY or not RUNPOD_ENDPOINT_ID:
        return {"error": "RUNPOD_API_KEY or RUNPOD_ENDPOINT_ID not set"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{RUNPOD_API_BASE}/{RUNPOD_ENDPOINT_ID}/health",
                headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("RunPod 헬스 체크 실패: %s", e)
        return {"error": str(e)}


async def set_runpod_workers(workers_min: int) -> dict:
    """RunPod Serverless endpoint workersMin 설정 (REST API).

    Args:
        workers_min: 최소 워커 수 (0=스케일 다운, 1+=워커 유지)

    Returns:
        API 응답 dict. 실패 시 {"error": str}.
    """
    if not RUNPOD_API_KEY or not RUNPOD_ENDPOINT_ID:
        return {"error": "RUNPOD_API_KEY or RUNPOD_ENDPOINT_ID not set"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                f"https://rest.runpod.io/v1/endpoints/{RUNPOD_ENDPOINT_ID}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {RUNPOD_API_KEY}",
                },
                json={"workersMin": workers_min},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("RunPod workersMin 설정 실패: %s", e)
        return {"error": str(e)}


async def generate_image_runpod(
    pos_prompt: str,
    neg_prompt: str,
    orientation: str = "portrait",
    skip_face: bool = False,
    seed: int = 0,
    workflow_override: str = "",
    checkpoint_override: str = "",
    lora_overrides: dict | None = None,
    lora_trigger: str = "",
) -> str | None:
    """RunPod Serverless를 통해 이미지 생성.

    로컬 generate_image와 동일한 워크플로우 준비 로직을 사용하되,
    anchor_image/IPAdapter 로직은 제외 (RunPod에 앵커 이미지 없음).
    RunPod runsync 엔드포인트로 워크플로우를 전송하고 결과를 받는다.

    Args:
        lora_overrides: 노드 131 (Power Lora Loader) 슬롯 on/off/strength override.
                        None이면 워크플로우 기본값 사용.
        lora_trigger: LoRA activation trigger token. 비어있지 않으면 EMBEDDING_POS_PREFIX와
                      model_prefix 사이(Position b)에 prepend.

    Returns:
        생성된 이미지 파일 경로 (str) 또는 실패 시 None
    """
    try:
        # 1. 워크플로우 로드 + 프롬프트 삽입 + seed
        workflow_file = workflow_override or os.getenv("COMFYUI_WORKFLOW", DEFAULT_WORKFLOW_PATH)
        workflow = load_workflow(workflow_file)
        workflow = inject_prompts(workflow, pos_prompt, neg_prompt)
        workflow = apply_lora_overrides(workflow, lora_overrides)

        global last_used_seed
        used_seed = seed if seed else random.randint(0, 2**53)
        last_used_seed = used_seed
        workflow["119"]["inputs"]["seed"] = used_seed

        # FaceDetailer 등 다른 노드의 seed도 랜덤화 (있으면)
        for node_id in ("29", "146", "147", "148", "149"):
            if node_id in workflow and "seed" in workflow[node_id].get("inputs", {}):
                workflow[node_id]["inputs"]["seed"] = random.randint(0, 2**53)

        # 체크포인트 오버라이드
        global current_loaded_checkpoint
        if checkpoint_override:
            workflow["2"]["inputs"]["ckpt_name"] = checkpoint_override
        elif os.getenv("COMFYUI_CHECKPOINT"):
            workflow["2"]["inputs"]["ckpt_name"] = os.getenv("COMFYUI_CHECKPOINT")
        current_loaded_checkpoint = workflow["2"]["inputs"]["ckpt_name"]

        # 모델별 + 글로벌 embedding prefix 적용
        # Position b: EMBEDDING → lora_trigger → model_prefix → pos_prompt
        ckpt_name = current_loaded_checkpoint
        model_prefix = MODEL_PREFIXES.get(ckpt_name, {})
        pos_prefix_parts = [
            p for p in [
                EMBEDDING_POS_PREFIX,
                (lora_trigger or "").strip(),
                model_prefix.get("pos", ""),
            ] if p
        ]
        neg_prefix_parts = [p for p in [EMBEDDING_NEG_PREFIX, model_prefix.get("neg", "")] if p]
        if pos_prefix_parts:
            current_pos = workflow["4"]["inputs"]["text"]
            workflow["4"]["inputs"]["text"] = ", ".join(pos_prefix_parts) + ", " + current_pos
        if neg_prefix_parts:
            current_neg = workflow["5"]["inputs"]["text"]
            workflow["5"]["inputs"]["text"] = ", ".join(neg_prefix_parts) + ", " + current_neg

        # 해상도 설정
        width, height = RESOLUTION_MAP.get(orientation, (768, 1024))
        workflow["118"]["inputs"]["width"] = width
        workflow["118"]["inputs"]["height"] = height

        # 2. RunPod runsync API 호출
        logger.info("RunPod 이미지 생성 요청 (seed=%d, orientation=%s)", used_seed, orientation)
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{RUNPOD_API_BASE}/{RUNPOD_ENDPOINT_ID}/runsync",
                headers={
                    "Authorization": f"Bearer {RUNPOD_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"input": {"workflow": workflow}},
            )
            resp.raise_for_status()
            result = resp.json()

        # 3. 결과에서 이미지 추출
        status = result.get("status")
        if status != "COMPLETED":
            logger.error("RunPod 이미지 생성 실패: status=%s, result=%s", status, result)
            return None

        output = result.get("output", {})
        image_base64 = output.get("image_base64")
        if not image_base64:
            logger.error("RunPod 응답에 image_base64가 없음: %s", list(output.keys()))
            return None

        # 4. base64 디코딩 → 임시 파일 저장
        image_data = base64.b64decode(image_base64)
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".png",
            prefix="ella_runpod_",
        )
        tmp.write(image_data)
        tmp.close()

        logger.info("RunPod 이미지 저장 완료: %s", tmp.name)
        return tmp.name

    except httpx.TimeoutException:
        logger.error("RunPod 이미지 생성 타임아웃 (180초)")
        return None
    except Exception as e:
        logger.error("RunPod 이미지 생성 실패: %s", e)
        return None


async def generate_image(
    pos_prompt: str,
    neg_prompt: str,
    anchor_image: str = "",
    orientation: str = "portrait",
    skip_face: bool = False,
    seed: int = 0,
    workflow_override: str = "",
    checkpoint_override: str = "",
    lora_overrides: dict | None = None,
    lora_trigger: str = "",
) -> str | None:
    """ComfyUI API를 통해 이미지 생성

    1. 워크플로우 로드
    2. 프롬프트 삽입
    3. /prompt 엔드포인트에 POST → prompt_id 획득
    4. /history/{prompt_id}로 생성 완료 대기
    5. 이미지 다운로드 → 임시 파일 저장

    Args:
        pos_prompt: 긍정 프롬프트
        neg_prompt: 부정 프롬프트
        anchor_image: LoadImage 노드에 설정할 이미지 파일명 (빈 문자열이면 기본값 유지)
        lora_overrides: 노드 131 (Power Lora Loader) 슬롯 on/off/strength override.
                        None이면 워크플로우 기본값 사용 (현재 동작 그대로).
        lora_trigger: LoRA activation trigger token. 비어있지 않으면 EMBEDDING_POS_PREFIX와
                      model_prefix 사이(Position b)에 prepend.

    Returns:
        생성된 이미지 파일 경로 (str) 또는 실패 시 None
    """
    # ── RunPod 라우팅: 활성화 시 RunPod 우선, 실패하면 GB10 로컬 fallback ──
    if runpod_enabled and RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID:
        health = await check_runpod_health()
        workers = health.get("workers", {})
        jobs = health.get("jobs", {})
        workers_ready = workers.get("ready", 0) + workers.get("idle", 0) + workers.get("running", 0)
        jobs_in_queue = jobs.get("inQueue", 0) + jobs.get("inProgress", 0)

        if workers_ready > 0 and jobs_in_queue < RUNPOD_MAX_QUEUE:
            result = await generate_image_runpod(
                pos_prompt, neg_prompt,
                orientation=orientation, skip_face=skip_face, seed=seed,
                workflow_override=workflow_override, checkpoint_override=checkpoint_override,
                lora_overrides=lora_overrides,
                lora_trigger=lora_trigger,
            )
            if result:
                return result
            logger.warning("RunPod 실패, GB10 로컬로 fallback")
        else:
            logger.info(
                "RunPod 큐 초과 또는 워커 없음 (workers=%d, queue=%d), GB10 fallback",
                workers_ready, jobs_in_queue,
            )

    # ── GB10 로컬 ComfyUI ──
    comfyui_url = os.getenv("COMFYUI_URL", "http://localhost:8188").rstrip("/")

    # 큐 초과 체크
    queue_status = await check_queue()
    total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
    if total_queued >= COMFYUI_MAX_QUEUE:
        logger.warning("ComfyUI 큐 초과: running=%s, pending=%s (max=%d)",
                       queue_status.get("running"), queue_status.get("pending"), COMFYUI_MAX_QUEUE)
        return "QUEUE_FULL"

    try:
        # 1. 워크플로우 로드 + 프롬프트 삽입 + seed 랜덤화
        workflow_file = workflow_override or os.getenv("COMFYUI_WORKFLOW", DEFAULT_WORKFLOW_PATH)
        workflow = load_workflow(workflow_file)
        workflow = inject_prompts(workflow, pos_prompt, neg_prompt)
        workflow = apply_lora_overrides(workflow, lora_overrides)
        global last_used_seed
        used_seed = seed if seed else random.randint(0, 2**53)
        last_used_seed = used_seed
        workflow["119"]["inputs"]["seed"] = used_seed

        # FaceDetailer 등 다른 노드의 seed도 랜덤화 (있으면)
        for node_id in ("29", "146", "147", "148", "149"):
            if node_id in workflow and "seed" in workflow[node_id].get("inputs", {}):
                workflow[node_id]["inputs"]["seed"] = random.randint(0, 2**53)

        # 체크포인트 오버라이드 (환경변수 COMFYUI_CHECKPOINT)
        global current_loaded_checkpoint
        if checkpoint_override:
            workflow["2"]["inputs"]["ckpt_name"] = checkpoint_override
        elif os.getenv("COMFYUI_CHECKPOINT"):
            workflow["2"]["inputs"]["ckpt_name"] = os.getenv("COMFYUI_CHECKPOINT")
        current_loaded_checkpoint = workflow["2"]["inputs"]["ckpt_name"]

        # 모델별 + 글로벌 embedding prefix 적용
        # Position b: EMBEDDING → lora_trigger → model_prefix → pos_prompt
        ckpt_name = current_loaded_checkpoint
        model_prefix = MODEL_PREFIXES.get(ckpt_name, {})
        pos_prefix_parts = [
            p for p in [
                EMBEDDING_POS_PREFIX,
                (lora_trigger or "").strip(),
                model_prefix.get("pos", ""),
            ] if p
        ]
        neg_prefix_parts = [p for p in [EMBEDDING_NEG_PREFIX, model_prefix.get("neg", "")] if p]
        if pos_prefix_parts:
            current_pos = workflow["4"]["inputs"]["text"]
            workflow["4"]["inputs"]["text"] = ", ".join(pos_prefix_parts) + ", " + current_pos
        if neg_prefix_parts:
            current_neg = workflow["5"]["inputs"]["text"]
            workflow["5"]["inputs"]["text"] = ", ".join(neg_prefix_parts) + ", " + current_neg

        # 해상도 설정 (orientation 기반)
        width, height = RESOLUTION_MAP.get(orientation, (768, 1024))
        workflow["118"]["inputs"]["width"] = width
        workflow["118"]["inputs"]["height"] = height

        # anchor 워크플로우만 IPAdapter 관련 처리
        workflow_name = Path(workflow_file).name
        if workflow_name in _ANCHOR_WORKFLOWS:
            # anchor_image가 지정되면 LoadImage 노드 (노드 "95")의 image를 교체
            if anchor_image:
                workflow["95"]["inputs"]["image"] = anchor_image

            # skip_face: IPAdapter FaceID 비활성화 (lower body 등 얼굴 없는 구도)
            if skip_face:
                workflow["119"]["inputs"]["model"] = ["131", 0]

        async with httpx.AsyncClient(timeout=180) as client:
            # 2. /prompt에 POST → prompt_id 획득
            resp = await client.post(
                f"{comfyui_url}/prompt",
                json={"prompt": workflow},
            )
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
            logger.info("ComfyUI prompt 요청 성공: prompt_id=%s", prompt_id)

            # 3. /history/{prompt_id}로 완료 대기 (폴링)
            elapsed = 0
            history_data = None

            while elapsed < MAX_WAIT_SECONDS:
                history_resp = await client.get(f"{comfyui_url}/history/{prompt_id}")
                history_resp.raise_for_status()
                data = history_resp.json()

                if prompt_id in data:
                    history_data = data[prompt_id]
                    break

                await asyncio.sleep(POLL_INTERVAL)
                elapsed += POLL_INTERVAL

            if history_data is None:
                timeout_queue = await check_queue()
                logger.error("ComfyUI 이미지 생성 타임아웃 (%d초) — 큐 상태: running=%s, pending=%s",
                             MAX_WAIT_SECONDS, timeout_queue.get("running"), timeout_queue.get("pending"))
                return "TIMEOUT"

            # 4. output에서 이미지 정보 추출 (SaveImage 노드 "30")
            outputs = history_data.get("outputs", {})
            save_node = outputs.get("30", {})
            images = save_node.get("images", [])

            if not images:
                logger.error("ComfyUI 응답에 이미지가 없음: %s", outputs)
                return None

            image_info = images[0]
            filename = image_info["filename"]
            subfolder = image_info.get("subfolder", "")
            img_type = image_info.get("type", "output")

            # 5. 이미지 다운로드
            view_resp = await client.get(
                f"{comfyui_url}/view",
                params={
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": img_type,
                },
            )
            view_resp.raise_for_status()

            # 6. 임시 파일로 저장
            suffix = Path(filename).suffix or ".png"
            tmp = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                prefix="ella_comfyui_",
            )
            tmp.write(view_resp.content)
            tmp.close()

            logger.info("ComfyUI 이미지 저장 완료: %s", tmp.name)
            return tmp.name

    except Exception as e:
        logger.error("ComfyUI 이미지 생성 실패: %s", e)
        # VRAM 상태도 함께 로깅 (장애 원인 파악용)
        try:
            from src.watchdog import check_vram
            vram = await check_vram()
            if vram:
                torch_free_mb = vram["torch_vram_free"] / 1_000_000
                torch_total_mb = vram["torch_vram_total"] / 1_000_000
                logger.error(
                    "ComfyUI VRAM 상태: torch_free=%.0fMB / torch_total=%.0fMB, device=%s",
                    torch_free_mb, torch_total_mb, vram["name"],
                )
        except Exception as vram_err:
            logger.debug("VRAM 상태 조회 중 에러 (무시): %s", vram_err)
        return None
