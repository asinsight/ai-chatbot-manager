export type EnvCategory = {
  id: string;
  label: string;
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
    label: "LLM 백엔드",
    keys: ["OPENWEBUI_URL", "OPENWEBUI_API_KEY", "LLM_API_PATH", "MODEL_NAME"],
  },
  {
    id: "grok",
    label: "Grok",
    keys: [
      "GROK_API_KEY",
      "GROK_MODEL_NAME",
      "GROK_BASE_URL",
      "GROK_IMAGE_MODEL",
      "VIDEO_GROK_MODEL",
      "VIDEO_ANALYZER_MODEL",
      "GROK_SEARCH_MODEL",
    ],
  },
  {
    id: "comfyui",
    label: "ComfyUI",
    keys: [
      "COMFYUI_URL",
      "COMFYUI_MAX_QUEUE",
      "COMFYUI_STUCK_TIMEOUT",
      "COMFYUI_VRAM_MIN_MB",
    ],
  },
  {
    id: "video",
    label: "비디오 (Atlas Cloud)",
    keys: ["ATLASCLOUD_API_KEY", "VIDEO_MODEL"],
  },
  {
    id: "prompt_guard",
    label: "Prompt Guard",
    keys: ["PROMPT_GUARD_URL", "PROMPT_GUARD_THRESHOLD", "PROMPT_GUARD_TIMEOUT"],
  },
  {
    id: "operations",
    label: "운영",
    keys: [
      "IMAGE_AUTONOMY",
      "FORCE_SFW_SCENE",
      "ENV",
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
    label: "봇 토큰 (Test/Prod)",
    keys: [],
    dynamicMatch: (k) =>
      /^(TEST|PROD)_(MAIN_BOT_TOKEN|MAIN_BOT_USERNAME|CHAR_BOT_[A-Za-z0-9]+|CHAR_USERNAME_[A-Za-z0-9]+)$/.test(
        k,
      ),
  },
  {
    id: "platform",
    label: "Admin webapp",
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

export function isEditable(key: string): boolean {
  return !READ_ONLY_KEYS.has(key);
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
