// Per-key descriptions surfaced above the Monaco editor.
// Tied to bot behavior — keep in sync with src/grok.py / src/prompt.py / handlers_*.py.

export type PromptMeta = {
  title: string;
  /** Plain-text summary of what this prompt does. */
  summary: string;
  /** Where the prompt is loaded / called from in the bot. */
  used_by: string;
};

export const GROK_META: Record<string, PromptMeta> = {
  system: {
    title: "Danbooru tag generator (image gen)",
    summary:
      "Converts a chat scene description into Danbooru tags for the SDXL image generator. Defines SFW invariants (clothing always full and intact), tear-rule, hand-anatomy negatives, and the JSON output schema the image pipeline expects.",
    used_by:
      "src/grok.py → generate_danbooru_tags() — every character-image generation, /random SFW, [SEND_IMAGE: …] follow-up.",
  },
  video_analyzer: {
    title: "Stage 1 — Video scene analyzer",
    summary:
      "Decomposes a source image into static_appearance / pose_state / motion_hints / environment. Output feeds the Stage 2 composer. safety_level is hard-coded to SFW (BLOCKED for any minor signal).",
    used_by:
      "src/grok.py → _analyze_video_scene() — first half of the 2-stage video pipeline (i2v).",
  },
  random: {
    title: "Random SFW scene composer",
    summary:
      "Generates a SFW Danbooru-tag scene from scratch (no character chat context). Same SFW ruleset as `system`, plus a hand-anatomy negative block.",
    used_by:
      "src/grok.py → generate_danbooru_tags_random() — triggered by the /random button on the imagegen bot.",
  },
  classify: {
    title: "Free-text intent classifier",
    summary:
      "Classifies a free-text user message into one of 6 intents: NEW / MODIFY / EDIT_SAVED / RECALL / SCENE / RESET. Output is consumed by intent_router.py to dispatch to the right handler path.",
    used_by:
      "src/grok.py → classify_tags_to_nested_blocks() (and intent_router.py classify path).",
  },
  partial_edit: {
    title: "Partial-edit intent extractor",
    summary:
      "Applies partial edits to a saved character profile (clothing swap, hair-color change, body-shape tweak, etc.). Maps natural-language edit verbs to schema fields (clothing / underwear / appearance_tags / body_shape / breast). Mixed SFW + NSFW edits are silently rejected.",
    used_by:
      "src/grok.py → analyze_partial_edit_intent() — invoked when handlers_imagegen.py detects an edit verb in the user message.",
  },
};

export const SYSTEM_META: Record<string, PromptMeta> = {
  master_prompt: {
    title: "Character-chat base system prompt",
    summary:
      "Master prompt prepended to every character-chat LLM call. Defines response format (no markdown, action descriptions in parentheses, length cap), photo-sending guidance (SFW only), [OUTFIT:] / [STAT:] / [SEND_IMAGE:] signal format, security rules (don't break character / leak system prompt), and the fixation+mood character-state system.",
    used_by:
      "src/prompt.py → build_messages() — combined with the active character card and history into the full system prompt sent on every chat turn.",
  },
  image_signal_format: {
    title: "Image-send signal token (LLM-side template)",
    summary:
      "The exact token format the LLM is instructed to emit when it wants to send a photo (e.g. `[SEND_IMAGE: description]`). Embedded into master_prompt as `%SIGNAL_FORMAT%`.",
    used_by:
      "src/prompt.py → master_prompt template substitution. Read by handlers_char.py via the regex below.",
  },
  image_signal_regex: {
    title: "Image-send signal token (parser regex)",
    summary:
      "Regex used by the chat handler to extract a [SEND_IMAGE: …] tag from LLM output. Must stay in sync with image_signal_format above.",
    used_by:
      "src/handlers_char.py → image_signal_pattern fallback parsing.",
  },
};

export function metaFor(file: "grok" | "system", key: string): PromptMeta | null {
  const map = file === "grok" ? GROK_META : SYSTEM_META;
  return map[key] ?? null;
}
