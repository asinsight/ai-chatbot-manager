// Client-safe types. Server module `lorebook.ts` uses node:fs / node:path.

export type EntryPosition = "background" | "active";

export type LorebookEntry = {
  keywords: string[];
  content: string;
  position: EntryPosition;
};

export type LorebookFile = {
  // Underscore-prefixed keys (`_doc`, ...) are passthrough metadata.
  // The bot loader skips them; the UI hides them.
  entries: LorebookEntry[];
  [docKey: `_${string}`]: unknown;
};

export type WorldSummary = {
  name: string;            // basename without .json
  entry_count: number;
  mapped_chars: string[];  // characters whose mapping points to this world
  mtime_ms: number;
  size_bytes: number;
};

export type MappingPayload = {
  mapping: Record<string, string>;  // char_id -> world_id
  characters: string[];             // all known character ids (for the UI dropdown)
  worlds: string[];                 // all available world ids (for the dropdown options)
};

// World filename validation: lowercase ascii + digits + underscore, must
// start with a letter, no `mapping` (reserved), no underscore prefix.
const WORLD_NAME_RE = /^[a-z][a-z0-9_]*$/;

export function isValidWorldName(name: string): boolean {
  if (!WORLD_NAME_RE.test(name)) return false;
  if (name === "mapping") return false;
  return true;
}

// ── client-safe preview ─────────────────────────────────────────────────────
// Mirrors src/prompt.py _match_world_info() so the platform's TestPane shows
// exactly what the bot will inject at runtime.

export type EntryMatch = {
  keyword: string;
  position: EntryPosition;
  content: string;
};

export function previewMatches(text: string, content: LorebookFile): EntryMatch[] {
  const lower = text.toLowerCase();
  const out: EntryMatch[] = [];
  for (const entry of content.entries ?? []) {
    for (const keyword of entry.keywords ?? []) {
      if (lower.includes(keyword.toLowerCase())) {
        out.push({
          keyword,
          position: entry.position === "background" ? "background" : "active",
          content: entry.content,
        });
        break;
      }
    }
  }
  return out;
}
