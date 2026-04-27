# `deploy/` — Deployment artifacts (SFW fork)

Systemd units, install/backup scripts, and the RunPod serverless image-gen endpoint for `ella-chat-publish`.

## Systemd units

- **`ella-chat-publish.service`** — Main bot unit. Runs `src/bot.py` under the project venv. Renamed from the original `ella-telegram.service` to match the fork name; install/uninstall scripts and `journalctl -u ella-chat-publish` follow the new name.
- **`comfyui.service`** — Local ComfyUI server for development image generation. Production routes through `runpod/` instead, but this unit is kept for local-host fallback and dev workflow.
- **`llama-server.service`** — Optional `llama.cpp` server unit for running a local LLM as a fallback when the hosted LLM endpoint is unavailable. Disabled by default; enable via `systemctl enable --now llama-server` if you provide a model file.
- **`prompt-guard.service`** — Optional safety classifier service that the bot can call for additional filtering on top of `src/input_filter.py`. Independent of the bot lifecycle.

## Scripts

- **`backup_db.sh`** — SQLite snapshot helper. Copies the bot DB (`data/bot.sqlite`) to a timestamped path, intended to be run from cron. Adjust `DB_PATH` / `BACKUP_DIR` at the top of the script for your install.
- **`install.sh`** — Bootstrap script. Creates the venv, installs `requirements.txt`, copies the four `.service` files into `/etc/systemd/system/`, runs `systemctl daemon-reload`, and enables the main bot unit. Re-runnable.

## RunPod serverless

- **`runpod/`** — Image-generation serverless endpoint. Files:
  - `Dockerfile` — Pulls the ComfyUI base image, installs custom nodes, and pre-warms the Illustrious checkpoint.
  - `handler.py` — RunPod handler entry; receives a workflow JSON + prompt parameters from `src/comfyui.py`, runs ComfyUI, and returns the image bytes.
  - `s3_download.py` — Downloads the model checkpoints + embeddings (`lazypos`, `lazynsfw`, `lazyneg`, `lazyhand`) from S3 at container start so the image is small and the model layer is hot-swappable.
  - `start.sh` — Container entrypoint; calls `s3_download.py` then `handler.py`.
  - `build.sh` / `build_remote.sh` — Local and remote (RunPod GPU) image-build helpers.

## SFW-fork drops (not present in this directory)

- **`runpod-video/`** — DaSiWa WAN 2.2 i2v fallback worker. DROPPED: the SFW fork uses Atlas Cloud `alibaba/wan-2.6/image-to-video-flash` for all video gen, so the self-hosted DaSiWa LoRA path and its RunPod worker are no longer needed.

## Environment variables

The bot reads its config from `.env` at runtime (see `.env.example` at the repo root). Keys that affect deployment specifically:

- `RUNPOD_ENDPOINT_ID` — Image-gen RunPod endpoint ID.
- `ATLASCLOUD_API_KEY` — Atlas Cloud credential for video generation.
- `VIDEO_MODEL` — defaults to `alibaba/wan-2.6/image-to-video-flash`; do not change unless replacing the video backend wholesale.
- `TELEGRAM_BOT_TOKEN`, `LLM_API_KEY`, `GROK_API_KEY` — required at runtime.

`.env` itself is intentionally not committed; copy `.env.example` and fill in production secrets at install time.
