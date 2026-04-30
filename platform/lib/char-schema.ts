// Field metadata for the schema-driven character editor form.
// Tied to character_card_schema.json — keep in sync if the root schema is edited.

export type FieldWidget =
  | "text"
  | "textarea"
  | "monaco"
  | "chips"
  | "kv"
  | "trigger-list"
  | "stat-limits";

export type FieldDef = {
  key: string;
  label: string;
  description?: string;
  required?: boolean;
  widget: FieldWidget;
  /** Hint for textareas / Monaco — taller widget. */
  multiline?: boolean;
  placeholder?: string;
};

/** persona/charNN.json — see character_card_schema.json (root). */
export const PERSONA_FIELDS: FieldDef[] = [
  { key: "name", label: "Name", required: true, widget: "text", description: "Character display name (replaces {{char}} in prompts)." },
  { key: "profile_summary_ko", label: "Profile summary", widget: "text", description: "One-line profile shown in the admin list." },
  { key: "description", label: "Description", required: true, widget: "textarea", multiline: true, description: "Free-form description (appearance, background, personality)." },
  { key: "personality", label: "Personality", widget: "textarea", description: "Short personality summary." },
  { key: "scenario", label: "Scenario", widget: "textarea", description: "Current RP scenario / setting." },
  { key: "first_mes", label: "First message", required: true, widget: "textarea", multiline: true, description: "Opening line the character sends. Supports {{user}} / {{char}}." },
  { key: "mes_example", label: "Example messages", widget: "monaco", description: "Few-shot dialogue. Use <START> blocks." },
  { key: "system_prompt", label: "System prompt", required: true, widget: "monaco", description: "Speech-style / Response Rules / Tone Guide / Emoji Rules." },
  { key: "post_history_instructions", label: "Post-history instructions", widget: "textarea", description: "Reminder injected after the chat history." },
  { key: "creator_notes", label: "Creator notes", widget: "textarea", description: "Memo for the card creator (not injected into prompts)." },
  // anchor_image: hidden from the form per PM request — still preserved in
  // schema + bot code (handlers_char.py reads it for ComfyUI IPAdapter FaceID
  // when present). Edit via Raw JSON if you need to set it.
  { key: "image_prompt_prefix", label: "Image prompt prefix", widget: "textarea", description: "Positive Danbooru tag prefix appended to every image generation." },
  { key: "image_negative_prefix", label: "Image negative prefix", widget: "textarea", description: "Negative Danbooru tag prefix." },
  { key: "stat_personality", label: "Stat personality", widget: "textarea", description: "Per-character meaning of fixation (rise/fall conditions). Injected into the prompt." },
  { key: "stat_moods", label: "Allowed moods", widget: "chips", description: "Mood values the [STAT:] signal may emit." },
  { key: "proactive_behaviors", label: "Proactive behaviors", widget: "textarea", description: "Self-driven behaviors the character takes without explicit user input." },
  { key: "interests", label: "Interests", widget: "chips", description: "Topics the character actively explores." },
  { key: "discovery_hint_template", label: "Discovery hint template", widget: "text", description: "Template for unfamiliar topics. {topic} is substituted; blank uses default." },
  { key: "mood_behaviors", label: "Mood-specific behaviors", widget: "kv", description: "Per-mood behavior guide. Only the active mood is injected." },
  { key: "mood_triggers", label: "Mood triggers", widget: "trigger-list", description: "Free-text trigger description → mood transition." },
  { key: "stat_limits", label: "Stat limits", widget: "stat-limits", description: "Per-character cap on fixation up/down deltas." },
  { key: "jobs", label: "Jobs", widget: "chips", description: "Job keys (matches jobs/<key>.json — currently empty in this fork)." },
];

/** images/charNN.json fields. Simple flat schema — Danbooru-tag strings + body shape / breast objects. */
export const IMAGES_FIELDS: FieldDef[] = [
  { key: "appearance_tags", label: "Appearance tags", widget: "textarea", description: "Always-applied face/hair/skin Danbooru tags." },
  { key: "clothing", label: "Default clothing", widget: "textarea", description: "Outfit set (top / bottom / shoes / accessories)." },
  { key: "alt_outfit", label: "Alt outfit", widget: "textarea", description: "Alternate outfit (work-mode / off-day / etc.)." },
  { key: "underwear", label: "Underwear", widget: "textarea", description: "Underwear set (only used as a layer when outfit allows visibility)." },
];

/** behaviors/charNN.json — proactive_behavior is a fixation-tier table. */
export const BEHAVIORS_FIELDS: FieldDef[] = [
  // proactive_behavior is rendered as a custom 4-tier widget — see behaviors-form.tsx.
  // The form widget owns parsing + serialization back into the canonical
  // [{condition: {fixation: [low, high]}, prompt: '...'}, …] shape.
];

export const BLANK_PERSONA: Record<string, unknown> = {
  name: "",
  profile_summary_ko: "",
  jobs: [],
  description: "",
  personality: "",
  scenario: "",
  first_mes: "",
  mes_example: "",
  system_prompt: "",
  post_history_instructions: "",
  creator_notes: "",
  anchor_image: "",
  image_prompt_prefix: "",
  image_negative_prefix: "",
  stat_personality: "",
  stat_moods: [],
  proactive_behaviors: "",
  interests: [],
  discovery_hint_template: "",
  mood_behaviors: {},
  mood_triggers: [],
  stat_limits: {},
};

export const BLANK_IMAGES = (charId: string): Record<string, unknown> => ({
  char_id: charId,
  appearance_tags: "",
  clothing: "",
  alt_outfit: "",
  underwear: "",
  body_shape: { size: "", build: "", curve: "", accent: "", ass: "" },
  breast: { size: "", feature: "" },
});

export const BLANK_BEHAVIORS: Record<string, unknown> = {
  proactive_behavior: [
    { condition: { fixation: [0, 20] }, prompt: "VERY LOW: …" },
    { condition: { fixation: [20, 50] }, prompt: "LOW: …" },
    { condition: { fixation: [50, 80] }, prompt: "MEDIUM: …" },
    { condition: { fixation: [80, 101] }, prompt: "HIGH: …" },
  ],
};
