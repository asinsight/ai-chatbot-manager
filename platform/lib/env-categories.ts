export type EnvCategory = {
  id: string;
  label: string;
  /** Per-tab description shown above the form. */
  description: string;
  /** Static list of keys belonging to this category. Empty array → matches keys via `dynamicMatch`. */
  keys: string[];
  /** Optional pattern matcher for dynamic keys (e.g. *_BOT_TOKEN). */
  dynamicMatch?: (key: string) => boolean;
};

/** Variables that the bot reads but the admin must NOT change at runtime. */
export const READ_ONLY_KEYS = new Set<string>(["VIDEO_MODEL"]);

export const CATEGORIES: EnvCategory[] = [
  {
    id: "llm",
    label: "LLM backend",
    description:
      "Character-chat LLM endpoint (llama-cpp-python or Open WebUI). Used by every chat turn for response generation. The image / video / classify / search paths use Grok separately — see the Grok prompting tab.",
    keys: ["OPENWEBUI_URL", "OPENWEBUI_API_KEY", "LLM_API_PATH", "MODEL_NAME"],
  },
  {
    id: "grok",
    label: "Grok prompting",
    description:
      "Grok API used for prompt generation only — Danbooru tag generation (image), video scene analysis + motion composer, intent classification, and web search. Not the chat backend. GROK_API_KEY + GROK_BASE_URL are infrastructure; the *_MODEL overrides let you split traffic across models (e.g. cheaper for classify, larger for video composer). Empty overrides fall back to GROK_PROMPTING_MODEL.",
    keys: [
      "GROK_API_KEY",
      "GROK_PROMPTING_MODEL",
      "GROK_BASE_URL",
      "GROK_PROMPTING_IMAGE_MODEL",
      "GROK_PROMPTING_VIDEO_MODEL",
      "GROK_PROMPTING_VIDEO_ANALYZER_MODEL",
      "GROK_PROMPTING_VIDEO_COMPOSER_MODEL",
      "GROK_PROMPTING_SEARCH_MODEL",
    ],
  },
  {
    id: "comfyui",
    label: "ComfyUI",
    description:
      "ComfyUI image-generation backend (local or RunPod-hosted). Used by every character image render and the /random SFW button. The MAX_QUEUE / STUCK_TIMEOUT / VRAM_MIN_MB knobs control admin alerts and request rejection — leave them blank to use defaults.",
    keys: [
      "COMFYUI_URL",
      "COMFYUI_MAX_QUEUE",
      "COMFYUI_STUCK_TIMEOUT",
      "COMFYUI_VRAM_MIN_MB",
    ],
  },
  {
    id: "video",
    label: "Video (Atlas Cloud)",
    description:
      "Atlas Cloud i2v (image-to-video) generation. Single-backend default `alibaba/wan-2.6/image-to-video-flash` (with native audio). VIDEO_MODEL is read-only here — the dropdown / catalog UI is the M7 milestone.",
    keys: ["ATLASCLOUD_API_KEY", "VIDEO_MODEL"],
  },
  {
    id: "prompt_guard",
    label: "Prompt Guard",
    description:
      "Optional prompt-injection detection service. When PROMPT_GUARD_URL is set, every user message is sent to `POST <URL>/check`; if blocked above THRESHOLD, the bot rejects the message before it reaches the LLM. Leave URL blank to disable.",
    keys: ["PROMPT_GUARD_URL", "PROMPT_GUARD_THRESHOLD", "PROMPT_GUARD_TIMEOUT"],
  },
  {
    id: "operations",
    label: "Operations",
    description:
      "Runtime knobs that don't fit the backend categories. IMAGE_AUTONOMY controls how often the LLM proactively sends photos (0–3). FORCE_SFW_SCENE pins the /random scene for debug. ADMIN_USER_IDS / ADMIN_NOTIFY / LOG_LEVEL govern logging and admin notifications. The LLM queue + summarization knobs throttle backpressure.",
    keys: [
      "IMAGE_AUTONOMY",
      "FORCE_SFW_SCENE",
      "ADMIN_USER_IDS",
      "ADMIN_NOTIFY",
      "LOG_LEVEL",
      "SUMMARY_THRESHOLD",
      "RECENT_MESSAGES_KEEP",
      "LLM_MAX_CONCURRENT",
      "LLM_MAX_QUEUE_SIZE",
      "LLM_QUEUE_TIMEOUT",
    ],
  },
  {
    id: "tokens",
    label: "Bot tokens",
    description:
      "Telegram bot tokens. MAIN_BOT_TOKEN drives the onboarding bot; per-character + imagegen tokens use the CHAR_BOT_<charId> / CHAR_USERNAME_<charId> pattern and are added when you register a new bot in @BotFather. Bot restart required after adding or rotating a token.",
    keys: ["MAIN_BOT_TOKEN", "MAIN_BOT_USERNAME"],
    dynamicMatch: (k) =>
      /^(MAIN_BOT_TOKEN|MAIN_BOT_USERNAME|CHAR_BOT_[A-Za-z0-9]+|CHAR_USERNAME_[A-Za-z0-9]+)$/.test(
        k,
      ),
  },
  {
    id: "platform",
    label: "Admin webapp",
    description:
      "Platform-only config (this Next.js admin webapp). PYTHON_BIN is the interpreter used when the Dashboard spawns the bot subprocess — set to your venv's python so the bot's dependencies resolve. Leave blank to use `python3` from PATH.",
    keys: ["PYTHON_BIN"],
  },
];

/** Map a key → category id. Falls back to "misc". */
export function categoryFor(key: string): string {
  for (const c of CATEGORIES) {
    if (c.keys.includes(key)) return c.id;
    if (c.dynamicMatch?.(key)) return c.id;
  }
  return "misc";
}

/**
 * Per-character bot tokens (CHAR_BOT_charNN / CHAR_USERNAME_charNN, EXCLUDING
 * the imagegen route which is its own special bot, not a character) are
 * editable only from `/characters/[charId]` to keep the source-of-truth in
 * one place. They show up in /env as read-only with a redirect link.
 */
const CHAR_TOKEN_RE = /^(CHAR_BOT|CHAR_USERNAME)_char(\d{2,3})$/;

export function charIdFromKey(key: string): string | null {
  const m = key.match(CHAR_TOKEN_RE);
  return m ? `char${m[2]}` : null;
}

export function isEditable(key: string): boolean {
  if (READ_ONLY_KEYS.has(key)) return false;
  if (CHAR_TOKEN_RE.test(key)) return false;
  return true;
}

/**
 * Returns true if the key is recognized — either statically or via a dynamic
 * matcher. Used by PUT /api/env to reject unknown-key writes (typo guard).
 */
export function isRecognized(key: string): boolean {
  for (const c of CATEGORIES) {
    if (c.keys.includes(key)) return true;
    if (c.dynamicMatch?.(key)) return true;
  }
  return false;
}
