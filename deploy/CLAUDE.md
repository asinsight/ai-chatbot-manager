# `deploy/` — Deployment helpers

Self-contained components that run alongside the bot but are not part
of the bot process itself.

## Standalone services

- **`prompt-guard/`** — Self-contained FastAPI server for prompt-injection
  detection. Bundled here because it is meant to run on the same host as
  the bot (or any host the bot can reach over HTTP). Contents:
  - `prompt_guard_server.py` — FastAPI app exposing `POST /check` + `GET /health`. Loads ProtectAI `deberta-v3-base-prompt-injection-v2` once at startup (CPU-only).
  - `requirements.txt` — `fastapi` / `uvicorn` / `transformers` / `torch` (CPU build) / `sentencepiece` / `protobuf`.
  - `README.md` — manual run + smoke-test reference.

## RunPod serverless

- **`runpod/`** — Image-generation serverless endpoint. Files:
  - `Dockerfile` — Pulls the ComfyUI base image, installs custom nodes.
  - `handler.py` — RunPod handler entry; receives a workflow JSON + prompt parameters from `src/comfyui.py`, runs ComfyUI, returns the image bytes.
  - `s3_download.py` — Downloads model checkpoints + embeddings from S3 at container start so the image stays small and the model layer is hot-swappable.
  - `start.sh` — Container entry-point; calls `s3_download.py` then `handler.py`.
  - `build.sh` / `build_remote.sh` — Local and remote (RunPod GPU) image-build helpers.

## What's intentionally not here

- Systemd unit files / `install.sh` / `backup_db.sh` — host-specific
  setup belongs in the operator's own ops repo, not in the open-source
  distribution. The bot can be supervised by anything (systemd,
  supervisord, tmux, Docker, the platform admin's `Start` button…).

## Environment variables

The bot reads its config from `.env` at the repo root. Keys that
specifically affect deployment:

- `COMFYUI_URL` — local ComfyUI endpoint, or RunPod proxy URL.
- `RUNPOD_API_KEY` + `RUNPOD_ENDPOINT_ID` + `RUNPOD_MAX_QUEUE` — image-gen RunPod credentials, used when `runpod_enabled` is set.
- `ATLASCLOUD_API_KEY` — Atlas Cloud credential for video generation.
- `VIDEO_MODEL` — defaults to `alibaba/wan-2.6/image-to-video-flash`.
- `MAIN_BOT_TOKEN` + `MAIN_BOT_USERNAME` — main bot Telegram credentials (required to start).
- `GROK_API_KEY` + `GROK_BASE_URL` — LLM credentials (or any OpenAI-compatible alternative).

`.env` is in `.gitignore`. Copy `.env.example` and fill in real secrets
at install time.
