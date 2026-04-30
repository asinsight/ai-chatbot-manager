"""Prompt-injection detection API server.

ProtectAI deberta-v3-base-prompt-injection-v2 model (CPU-only, ~50-200ms/request).

POST /check {"text": "..."} → {"label": "SAFE"|"INJECTION", "score": 0.0-1.0, "blocked": bool}
GET  /health → {"status": "ok", "model": "..."}

Run:
    pip install -r requirements.txt
    python prompt_guard_server.py        # listens on 0.0.0.0:8081

Or via systemd: see prompt-guard.service in this directory.

The bot reaches this server through PROMPT_GUARD_URL (set in the bot's .env).
When PROMPT_GUARD_URL is empty, the bot skips the remote call and falls back
to regex-based filtering only.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from transformers import pipeline

logger = logging.getLogger(__name__)

MODEL_ID = "protectai/deberta-v3-base-prompt-injection-v2"
THRESHOLD = 0.8

classifier = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global classifier
    logger.info("loading injection-detection model: %s", MODEL_ID)
    classifier = pipeline(
        "text-classification",
        model=MODEL_ID,
        tokenizer=MODEL_ID,
        device=-1,  # CPU
        truncation=True,
        max_length=512,
    )
    logger.info("injection-detection model loaded")
    yield


app = FastAPI(title="Prompt Injection Guard API", lifespan=lifespan)


class CheckRequest(BaseModel):
    text: str
    threshold: float = THRESHOLD


class CheckResponse(BaseModel):
    label: str
    score: float
    blocked: bool


@app.post("/check", response_model=CheckResponse)
async def check(req: CheckRequest):
    result = classifier(req.text)[0]
    # ProtectAI label vocabulary: "SAFE" or "INJECTION".
    injection_score = result["score"] if result["label"] == "INJECTION" else 1.0 - result["score"]
    label = "INJECTION" if injection_score >= req.threshold else "SAFE"
    return CheckResponse(
        label=label,
        score=round(injection_score, 4),
        blocked=injection_score >= req.threshold,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_ID}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
