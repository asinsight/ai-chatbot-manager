# `comfyui_workflow/` — ComfyUI workflow JSONs (SFW fork)

ComfyUI workflow exports consumed by `src/comfyui.py` (image gen) and the audio-gen pipeline. Each file is a node-graph snapshot suitable for ComfyUI's `Load Workflow` action and for programmatic invocation through the RunPod handler in `deploy/runpod/`.

## Files

- **`main_character_build.json`** — Primary character image-gen workflow. Illustrious-family checkpoint with the standard text-encode → KSampler → VAE-decode chain. Used for `/random` SFW rolls, character-card renders, and direct prompt-to-image flows from chat.
- **`main_character_build_archived.json`** — Previous-revision snapshot of the main workflow. Kept for rollback; not loaded at runtime.
- **`main_character_build_highqual.json`** — Higher-quality variant (more sampler steps / refiner pass) for explicit `/highqual` requests. Same Illustrious checkpoint family as the main workflow.
- **`audiogen-workflow.json`** — Audio generation workflow (TTS / sound effect synthesis). Independent from the image pipeline.

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

## Editing notes

- ComfyUI workflows are large JSON graphs — prefer editing through the ComfyUI UI (`Save (API Format)`) rather than hand-editing.
- After any change, redeploy the RunPod image (`deploy/runpod/build_remote.sh`) so the worker picks up the new graph.
- Do not add LoRA loader nodes that reference NSFW-tagged LoRAs — the fork has no character LoRA pipeline and the SFW negative block in `config/grok_prompts.json` assumes no NSFW visual amplification at the model level.
