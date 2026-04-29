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

# Project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Workflow path (overridable via env var)
DEFAULT_WORKFLOW_PATH = "comfyui_workflow/main_character_build.json"

# Workflows that use an anchor image (i.e. include IPAdapter FaceID)
_ANCHOR_WORKFLOWS = {"main_character_build_archived.json"}

# Maximum wait for image generation completion (seconds)
MAX_WAIT_SECONDS = 360

# Maximum allowed ComfyUI queue depth
COMFYUI_MAX_QUEUE = int(os.getenv("COMFYUI_MAX_QUEUE", "10"))

# Poll interval (seconds)
POLL_INTERVAL = 1

# Last seed used (read by the image bot)
last_used_seed: int = 0

# Currently loaded checkpoint (read by the image bot)
current_loaded_checkpoint: str = ""

# ── RunPod Serverless config ──
runpod_enabled: bool = False
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")
RUNPOD_MAX_QUEUE = int(os.getenv("RUNPOD_MAX_QUEUE", "3"))
RUNPOD_API_BASE = "https://api.runpod.ai/v2"

# Global embedding prefixes (shared across all models)
EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos"
EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazynsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"

# Per-model prompt prefixes
MODEL_PREFIXES = {
    "illustrious/oneObsession_v20Bold.safetensors": {
        "pos": "masterpiece, best quality, amazing quality, very awa, absurdres, newest, very aesthetic, depth of field, highres",
        "neg": "worst quality, normal quality, anatomical nonsense, bad anatomy, interlocked fingers, extra fingers, watermark, low quality, logo, text, signature",
    },
    "illustrious/JANKUTrainedChenkinNoobai_v777.safetensors": {
        # NoobAI/JANKU recommended quality triggers (Civitai model card + NoobAI official guide)
        "pos": "masterpiece, best quality, amazing quality, newest, absurdres, very aesthetic, highres, year 2026",
        "neg": "worst quality, low quality, lowres, bad anatomy, bad hands, mutated hands, watermark, signature, logo, text",
    },
}

RESOLUTION_MAP = {
    "portrait": (832, 1216),        # upper body, cowboy shot — most common
    "tall_portrait": (768, 1344),   # full body, standing full body
    "narrow": (704, 1408),          # tall narrow full body
    "landscape": (1216, 832),       # lying-down scene, wide
    "wide": (1536, 1024),           # wide background, scenery
    "large_portrait": (1024, 1536), # high-res vertical
}


async def check_queue() -> dict:
    """Query ComfyUI queue status. Returns {"running": int, "pending": int}"""
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
        logger.error("ComfyUI queue query failed: %s", e)
        return {"running": -1, "pending": -1, "error": str(e)}


def load_workflow(path: str = DEFAULT_WORKFLOW_PATH) -> dict:
    """Load a workflow JSON file.

    Args:
        path: relative path from the project root, or an absolute path

    Returns:
        Workflow dict.
    """
    workflow_path = Path(path)
    if not workflow_path.is_absolute():
        workflow_path = PROJECT_ROOT / workflow_path

    with open(workflow_path, "r", encoding="utf-8") as f:
        return json.load(f)


def inject_prompts(workflow: dict, pos_prompt: str, neg_prompt: str) -> dict:
    """Inject prompts into the workflow.

    %prompt% in node "4" (Positive CLIPTextEncode) → pos_prompt
    %negative_prompt% in node "5" (Negative CLIPTextEncode) → neg_prompt

    Args:
        workflow: original workflow dict
        pos_prompt: positive prompt
        neg_prompt: negative prompt

    Returns:
        Workflow dict with prompts injected (deep-copied).
    """
    wf = deepcopy(workflow)
    wf["4"]["inputs"]["text"] = wf["4"]["inputs"]["text"].replace("%prompt%", pos_prompt)
    wf["5"]["inputs"]["text"] = wf["5"]["inputs"]["text"].replace("%negative_prompt%", neg_prompt)
    return wf


def apply_lora_overrides(workflow: dict, lora_overrides: dict | None) -> dict:
    """Apply slot on/off and strength overrides on the Power Lora Loader (rgthree) node 131.

    Args:
        workflow: dict returned by load_workflow()
        lora_overrides: {"lora_N": {"on": bool, "strength": float}}.
                        If None or empty the workflow defaults are kept.

    Returns:
        Modified workflow dict (modified in place).
    """
    if not lora_overrides:
        return workflow
    node = workflow.get("131", {}).get("inputs", {})
    if not node:
        logger.warning("apply_lora_overrides: node 131 missing — skipping")
        return workflow
    for slot_key, override in lora_overrides.items():
        if not slot_key.startswith("lora_"):
            continue
        if slot_key not in node:
            logger.warning(
                "apply_lora_overrides: slot %s not in workflow — skipping (override=%s)",
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
    """Health check the RunPod Serverless endpoint.

    Returns:
        Health info dict. {"error": str} on failure.
        Example success: {"workers": {"idle": 1, "ready": 1, "running": 0, ...}, "jobs": {"inQueue": 0, "inProgress": 0, ...}}
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
        logger.error("RunPod health check failed: %s", e)
        return {"error": str(e)}


async def set_runpod_workers(workers_min: int) -> dict:
    """Set workersMin on the RunPod Serverless endpoint (REST API).

    Args:
        workers_min: minimum worker count (0=scale down, 1+=keep workers warm)

    Returns:
        API response dict. {"error": str} on failure.
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
        logger.error("RunPod workersMin set failed: %s", e)
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
    """Generate an image via RunPod Serverless.

    Uses the same workflow-preparation logic as the local generate_image but
    skips the anchor_image / IPAdapter path (no anchor image on RunPod). Sends
    the workflow to the RunPod runsync endpoint and returns the result.

    Args:
        lora_overrides: on/off/strength override for node 131 (Power Lora Loader) slots.
                        If None the workflow defaults are kept.
        lora_trigger: LoRA activation trigger token. When non-empty, it is prepended
                      between EMBEDDING_POS_PREFIX and the model prefix (Position b).

    Returns:
        Path of the generated image file (str), or None on failure.
    """
    try:
        # 1. Load workflow, inject prompts, set seed
        workflow_file = workflow_override or os.getenv("COMFYUI_WORKFLOW", DEFAULT_WORKFLOW_PATH)
        workflow = load_workflow(workflow_file)
        workflow = inject_prompts(workflow, pos_prompt, neg_prompt)
        workflow = apply_lora_overrides(workflow, lora_overrides)

        global last_used_seed
        used_seed = seed if seed else random.randint(0, 2**53)
        last_used_seed = used_seed
        workflow["119"]["inputs"]["seed"] = used_seed

        # Randomize seed on other nodes too (FaceDetailer etc.) if present
        for node_id in ("29", "146", "147", "148", "149"):
            if node_id in workflow and "seed" in workflow[node_id].get("inputs", {}):
                workflow[node_id]["inputs"]["seed"] = random.randint(0, 2**53)

        # Checkpoint override
        global current_loaded_checkpoint
        if checkpoint_override:
            workflow["2"]["inputs"]["ckpt_name"] = checkpoint_override
        elif os.getenv("COMFYUI_CHECKPOINT"):
            workflow["2"]["inputs"]["ckpt_name"] = os.getenv("COMFYUI_CHECKPOINT")
        current_loaded_checkpoint = workflow["2"]["inputs"]["ckpt_name"]

        # Apply per-model + global embedding prefixes
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

        # Resolution
        width, height = RESOLUTION_MAP.get(orientation, (768, 1024))
        workflow["118"]["inputs"]["width"] = width
        workflow["118"]["inputs"]["height"] = height

        # 2. RunPod runsync API call
        logger.info("RunPod image generation request (seed=%d, orientation=%s)", used_seed, orientation)
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

        # 3. Extract image from result
        status = result.get("status")
        if status != "COMPLETED":
            logger.error("RunPod image generation failed: status=%s, result=%s", status, result)
            return None

        output = result.get("output", {})
        image_base64 = output.get("image_base64")
        if not image_base64:
            logger.error("RunPod response missing image_base64: %s", list(output.keys()))
            return None

        # 4. base64 decode → write to temp file
        image_data = base64.b64decode(image_base64)
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".png",
            prefix="ella_runpod_",
        )
        tmp.write(image_data)
        tmp.close()

        logger.info("RunPod image saved: %s", tmp.name)
        return tmp.name

    except httpx.TimeoutException:
        logger.error("RunPod image generation timeout (180s)")
        return None
    except Exception as e:
        logger.error("RunPod image generation failed: %s", e)
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
    """Generate an image through the ComfyUI API.

    1. Load workflow.
    2. Inject prompts.
    3. POST to /prompt → get prompt_id.
    4. Poll /history/{prompt_id} for completion.
    5. Download the image and write to a temp file.

    Args:
        pos_prompt: positive prompt
        neg_prompt: negative prompt
        anchor_image: image filename to set on the LoadImage node (kept at default when empty)
        lora_overrides: on/off/strength override for node 131 (Power Lora Loader) slots.
                        If None the workflow defaults are kept (current behaviour).
        lora_trigger: LoRA activation trigger token. When non-empty, it is prepended
                      between EMBEDDING_POS_PREFIX and the model prefix (Position b).

    Returns:
        Path of the generated image file (str), or None on failure.
    """
    # ── RunPod routing: when enabled, prefer RunPod and fall back to GB10 local on failure ──
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
            logger.warning("RunPod failed, falling back to GB10 local")
        else:
            logger.info(
                "RunPod queue exceeded or no workers (workers=%d, queue=%d), GB10 fallback",
                workers_ready, jobs_in_queue,
            )

    # ── GB10 local ComfyUI ──
    comfyui_url = os.getenv("COMFYUI_URL", "http://localhost:8188").rstrip("/")

    # Queue capacity check
    queue_status = await check_queue()
    total_queued = queue_status.get("running", 0) + queue_status.get("pending", 0)
    if total_queued >= COMFYUI_MAX_QUEUE:
        logger.warning("ComfyUI queue exceeded: running=%s, pending=%s (max=%d)",
                       queue_status.get("running"), queue_status.get("pending"), COMFYUI_MAX_QUEUE)
        return "QUEUE_FULL"

    try:
        # 1. Load workflow + inject prompts + randomize seed
        workflow_file = workflow_override or os.getenv("COMFYUI_WORKFLOW", DEFAULT_WORKFLOW_PATH)
        workflow = load_workflow(workflow_file)
        workflow = inject_prompts(workflow, pos_prompt, neg_prompt)
        workflow = apply_lora_overrides(workflow, lora_overrides)
        global last_used_seed
        used_seed = seed if seed else random.randint(0, 2**53)
        last_used_seed = used_seed
        workflow["119"]["inputs"]["seed"] = used_seed

        # Randomize seed on other nodes too (FaceDetailer etc.) if present
        for node_id in ("29", "146", "147", "148", "149"):
            if node_id in workflow and "seed" in workflow[node_id].get("inputs", {}):
                workflow[node_id]["inputs"]["seed"] = random.randint(0, 2**53)

        # Checkpoint override (COMFYUI_CHECKPOINT env var)
        global current_loaded_checkpoint
        if checkpoint_override:
            workflow["2"]["inputs"]["ckpt_name"] = checkpoint_override
        elif os.getenv("COMFYUI_CHECKPOINT"):
            workflow["2"]["inputs"]["ckpt_name"] = os.getenv("COMFYUI_CHECKPOINT")
        current_loaded_checkpoint = workflow["2"]["inputs"]["ckpt_name"]

        # Apply per-model + global embedding prefixes
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

        # Resolution (driven by orientation)
        width, height = RESOLUTION_MAP.get(orientation, (768, 1024))
        workflow["118"]["inputs"]["width"] = width
        workflow["118"]["inputs"]["height"] = height

        # IPAdapter handling — only for anchor workflows
        workflow_name = Path(workflow_file).name
        if workflow_name in _ANCHOR_WORKFLOWS:
            # If anchor_image is set, replace the image on the LoadImage node (node "95")
            if anchor_image:
                workflow["95"]["inputs"]["image"] = anchor_image

            # skip_face: disable IPAdapter FaceID (e.g. lower-body shots without a face)
            if skip_face:
                workflow["119"]["inputs"]["model"] = ["131", 0]

        async with httpx.AsyncClient(timeout=180) as client:
            # 2. POST /prompt → get prompt_id
            resp = await client.post(
                f"{comfyui_url}/prompt",
                json={"prompt": workflow},
            )
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
            logger.info("ComfyUI prompt request ok: prompt_id=%s", prompt_id)

            # 3. Poll /history/{prompt_id} for completion
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
                logger.error("ComfyUI image generation timeout (%ds) — queue state: running=%s, pending=%s",
                             MAX_WAIT_SECONDS, timeout_queue.get("running"), timeout_queue.get("pending"))
                return "TIMEOUT"

            # 4. Extract image info from output (SaveImage node "30")
            outputs = history_data.get("outputs", {})
            save_node = outputs.get("30", {})
            images = save_node.get("images", [])

            if not images:
                logger.error("ComfyUI response has no image: %s", outputs)
                return None

            image_info = images[0]
            filename = image_info["filename"]
            subfolder = image_info.get("subfolder", "")
            img_type = image_info.get("type", "output")

            # 5. Download the image
            view_resp = await client.get(
                f"{comfyui_url}/view",
                params={
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": img_type,
                },
            )
            view_resp.raise_for_status()

            # 6. Save to a temp file
            suffix = Path(filename).suffix or ".png"
            tmp = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix,
                prefix="ella_comfyui_",
            )
            tmp.write(view_resp.content)
            tmp.close()

            logger.info("ComfyUI image saved: %s", tmp.name)
            return tmp.name

    except Exception as e:
        logger.error("ComfyUI image generation failed: %s", e)
        # Log VRAM state too (helps with failure triage)
        try:
            from src.watchdog import check_vram
            vram = await check_vram()
            if vram:
                torch_free_mb = vram["torch_vram_free"] / 1_000_000
                torch_total_mb = vram["torch_vram_total"] / 1_000_000
                logger.error(
                    "ComfyUI VRAM state: torch_free=%.0fMB / torch_total=%.0fMB, device=%s",
                    torch_free_mb, torch_total_mb, vram["name"],
                )
        except Exception as vram_err:
            logger.debug("VRAM state lookup error (ignored): %s", vram_err)
        return None
