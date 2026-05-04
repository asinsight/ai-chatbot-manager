// Client-safe constants for the config editor — no node:fs / node:path imports.
// The server-side counterparts (paths, read/write/backup) live in `config-files.ts`.

export type ConfigFileKey =
  | "sfw_scenes"
  | "pose_motion_presets"
  | "sfw_denylist"
  | "profile_keys";

export const CONFIG_FILE_KEYS: ConfigFileKey[] = [
  "sfw_scenes",
  "pose_motion_presets",
  "sfw_denylist",
  "profile_keys",
];

export const CONFIG_FILE_BASENAMES: Record<ConfigFileKey, string> = {
  sfw_scenes: "sfw_scenes.json",
  pose_motion_presets: "pose_motion_presets.json",
  sfw_denylist: "sfw_denylist.json",
  profile_keys: "profile_keys.json",
};

// Repo-relative display paths — what the user sees in the tab header.
export const CONFIG_FILE_DISPLAY_PATHS: Record<ConfigFileKey, string> = {
  sfw_scenes: "config/sfw_scenes.json",
  pose_motion_presets: "config/pose_motion_presets.json",
  sfw_denylist: "config/sfw_denylist.json",
  profile_keys: "config/profile_keys.json",
};

export const CONFIG_FILE_META: Record<
  ConfigFileKey,
  { title: string; summary: string; usedBy: string }
> = {
  sfw_scenes: {
    title: "SFW scenes",
    summary:
      "Scene catalog seeded into Grok before image-prompt generation. Each entry pre-fixes the scene type so Grok does not bias pose selection.",
    usedBy: "src/trait_pools.py · roll_sfw_scene() · /random SFW button",
  },
  pose_motion_presets: {
    title: "Pose motion presets",
    summary:
      "Text-only motion presets for the WAN 2.2 i2v Composer fallback. One preset per pose key; 'generic' is a required catch-all.",
    usedBy: "src/pose_motion_presets.py · video composer fallback path",
  },
  sfw_denylist: {
    title: "SFW outfit denylist",
    summary:
      "Keywords silently dropped from [OUTFIT: ...] LLM emissions. Case-insensitive, whole-word match.",
    usedBy: "src/handlers_char.py outfit parser",
  },
  profile_keys: {
    title: "Profile keys",
    summary:
      "Canonical user-profile keys + alias mappings. Unknown keys emitted by the LLM are dropped when applying partial profile edits.",
    usedBy: "src/profile_keys.py",
  },
};
