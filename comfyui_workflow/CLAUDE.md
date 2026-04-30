# `comfyui_workflow/` — ComfyUI workflow JSONs (SFW fork)

ComfyUI workflow exports consumed by `src/comfyui.py` (image gen). Each file is a node-graph snapshot suitable for ComfyUI's `Load Workflow` action and for programmatic invocation through the RunPod handler in `deploy/runpod/`.

## Files

- **`main_character_build.json`** — Primary character image-gen workflow. Illustrious-family checkpoint with the standard text-encode → KSampler → VAE-decode chain. Used for `/random` SFW rolls, character-card renders, and direct prompt-to-image flows from chat.
- **`main_character_build_archived.json`** — Previous-revision snapshot of the main workflow. Kept for rollback; not loaded at runtime.
- **`main_character_build_highqual.json`** — Higher-quality variant for `/highqual` requests. Adds a chain of `FaceDetailer` passes for face / eye / hand refinement plus a `DetailerForEach` foot/toe pass on top of the base render. Same Illustrious checkpoint family as the main workflow. **NSFW-free as of M5 cleanup**: the original NSFW Detailer chain (`FaceDetailer (vagina)`, `FaceDetailer (breast)`, plus the matching `bbox/pussy.pt` and `segm/breasts_seg.pt` UltralyticsDetectorProvider nodes, and their explicit anatomical wildcard prompts) was deleted; the chain now ends `hand → foot SEGM → DetailerForEach (Foot) → SaveImage`.
- **`audiogen-workflow.json`** — DROP. `alibaba/wan-2.6/image-to-video-flash` (Atlas Cloud) provides native audio in the video output, so no post-hoc MMAudio synthesis step is needed. The original NSFW-fine-tuned MMAudio workflow (`mmaudio_large_44k_nsfw_gold_8.5k_final_fp16.safetensors`) and its loader code path were removed at fork time.

## Embedding prefixes (defined in `src/comfyui.py:47-48`)

Every render injects these embeddings into the prompts before the model-specific text:

```
EMBEDDING_POS_PREFIX = "embedding:illustrious/lazypos"
EMBEDDING_NEG_PREFIX = "embedding:illustrious/lazynsfw, embedding:illustrious/lazyneg, embedding:illustrious/lazyhand"
```

`lazynsfw` was moved from positive to negative at fork time so it actively suppresses NSFW visual elements in every render rather than amplifying them. `lazypos` (positive) stays as a quality embed; `lazyneg` and `lazyhand` cover general bad-quality and hand-anatomy issues.

These embeddings must be present on the model server (S3 download in `deploy/runpod/s3_download.py`).

## SFW-fork drop

- **`DaSiWa-WAN2.2-i2v-FastFidelity-C-AiO-69.json`** — Was the DaSiWa WAN 2.2 i2v fallback workflow in the original repo. NOT carried into the fork. Atlas Cloud `wan-2.6/image-to-video-flash` handles all video generation now (see `src/video.py`), so this workflow plus the matching `deploy/runpod-video/` worker were both dropped.
- **`audiogen-workflow.json`** — Was the ComfyUI MMAudio post-hoc audio synthesis workflow in the original repo. Deleted from the fork (Phase 2D). `wan-2.6/image-to-video-flash` emits video with native audio, and the bypass branch that used to call this workflow was already removed from `src/video.py` (Phase 2A).

## Checkpoint placeholders

Some bundled workflows ship with `"ckpt_name": "PLACEHOLDER_CHECKPOINT.safetensors"` instead of a real model filename. This is intentional — the open-source build does not pin a specific checkpoint, so each operator picks one that exists on their ComfyUI server before the first render. Use `/workflows → Form → Checkpoint` (a dropdown auto-populated from the live ComfyUI `/object_info/CheckpointLoaderSimple` response) to swap the placeholder for a real checkpoint and Save. Bot restart required afterwards.

## Editing notes

- ComfyUI workflows are large JSON graphs — prefer editing through the ComfyUI UI (`Save (API Format)`) rather than hand-editing.
- The platform admin's `/workflows` page is the recommended editing surface (M5):
  - **Stage assignments** card maps Standard / HQ stages to a workflow filename via the `COMFYUI_WORKFLOW` / `COMFYUI_WORKFLOW_HQ` env vars. Archived workflows are excluded from the picker.
  - **Form** tab edits a small whitelist (checkpoint, KSampler seed/cfg/steps/sampler/scheduler, SaveImage filename_prefix) without touching graph topology.
  - **Replace** tab accepts a fresh ComfyUI export — but rejects any paste whose Positive node `text` does not contain `%prompt%` or whose Negative node `text` does not contain `%negative_prompt%` (422 `PLACEHOLDER_MISSING`). `src/comfyui.py:121-122` does `str.replace("%prompt%", ...)` at runtime; without those tokens, render output is silently broken.
- Description text shown on `/workflows` lives in `config/workflow_descriptions.json` (platform-admin-only metadata; the bot does not read it).
- After any change, redeploy the RunPod image (`deploy/runpod/build_remote.sh`) so the worker picks up the new graph.
- Do not add LoRA loader nodes that reference NSFW-tagged LoRAs — the fork has no character LoRA pipeline and the SFW negative block in `config/grok_prompts.json` assumes no NSFW visual amplification at the model level.
