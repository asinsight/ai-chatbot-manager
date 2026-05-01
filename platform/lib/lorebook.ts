import fsp from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import { BACKUP_DIR } from "./backup";
import { REPO_ROOT } from "./paths";
import {
  isValidWorldName,
  type LorebookEntry,
  type LorebookFile,
  type MappingPayload,
  type WorldSummary,
} from "./lorebook-meta";

export {
  isValidWorldName,
  type LorebookEntry,
  type LorebookFile,
  type MappingPayload,
  type WorldSummary,
  type EntryPosition,
} from "./lorebook-meta";

const WORLD_DIR = path.join(REPO_ROOT, "world_info");
const MAPPING_FILE = path.join(WORLD_DIR, "mapping.json");
const PERSONA_DIR = path.join(REPO_ROOT, "persona");

function timestamp(d: Date = new Date()): string {
  const offsetMs = 9 * 60 * 60 * 1000;
  const kst = new Date(d.getTime() + offsetMs);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    kst.getUTCFullYear().toString() +
    pad(kst.getUTCMonth() + 1) +
    pad(kst.getUTCDate()) +
    "-" +
    pad(kst.getUTCHours()) +
    pad(kst.getUTCMinutes()) +
    pad(kst.getUTCSeconds())
  );
}

async function _readJson(file: string): Promise<unknown> {
  const text = await fsp.readFile(file, "utf8");
  return JSON.parse(text);
}

async function _writeJsonAtomic(file: string, content: unknown): Promise<void> {
  const serialized = JSON.stringify(content, null, 2) + "\n";
  const tmp = `${file}.partial`;
  await fsp.writeFile(tmp, serialized, "utf8");
  await fsp.rename(tmp, file);
}

async function _backup(file: string): Promise<string> {
  await fsp.mkdir(BACKUP_DIR, { recursive: true });
  const base = path.basename(file);
  const target = path.join(BACKUP_DIR, `${base}.${timestamp()}.bak`);
  const tmp = `${target}.partial`;
  try {
    await fsp.copyFile(file, tmp);
    await fsp.rename(tmp, target);
    return target;
  } catch {
    return "";
  }
}

// ── world files ─────────────────────────────────────────────────────────────

export async function listWorldFiles(): Promise<string[]> {
  let entries: string[] = [];
  try {
    entries = await fsp.readdir(WORLD_DIR);
  } catch {
    return [];
  }
  const out: string[] = [];
  for (const f of entries) {
    if (!f.endsWith(".json")) continue;
    const name = f.slice(0, -5);
    if (name === "mapping") continue; // mapping.json is handled separately
    out.push(name);
  }
  out.sort();
  return out;
}

const entrySchema = z
  .object({
    keywords: z.array(z.string().min(1)),
    content: z.string(),
    position: z.enum(["background", "active"]),
  })
  .strict();

const worldFileSchema = z
  .object({
    entries: z.array(entrySchema),
  })
  .passthrough(); // tolerate _doc and friends

export type ValidationError = { code: string; message: string };

export function validateWorldShape(
  content: unknown,
): { ok: true } | { ok: false; errors: ValidationError[] } {
  const r = worldFileSchema.safeParse(content);
  if (r.success) return { ok: true };
  return {
    ok: false,
    errors: r.error.issues.map((i) => ({
      code: "INVALID_SHAPE",
      message: `${i.path.join(".") || "<root>"}: ${i.message}`,
    })),
  };
}

export async function readWorld(name: string): Promise<{
  name: string;
  content: LorebookFile;
  mtime_ms: number;
  size_bytes: number;
}> {
  if (!isValidWorldName(name)) {
    throw Object.assign(new Error(`invalid world name: ${name}`), { code: "INVALID_NAME" });
  }
  const file = path.join(WORLD_DIR, `${name}.json`);
  const [stat, raw] = await Promise.all([fsp.stat(file), _readJson(file)]);
  const validation = validateWorldShape(raw);
  if (!validation.ok) {
    throw Object.assign(new Error(validation.errors.map((e) => e.message).join("; ")), {
      code: "INVALID_SHAPE",
    });
  }
  return {
    name,
    content: raw as LorebookFile,
    mtime_ms: stat.mtimeMs,
    size_bytes: stat.size,
  };
}

export async function writeWorld(
  name: string,
  content: unknown,
): Promise<{ backup_path: string }> {
  if (!isValidWorldName(name)) {
    throw Object.assign(new Error(`invalid world name: ${name}`), { code: "INVALID_NAME" });
  }
  const validation = validateWorldShape(content);
  if (!validation.ok) {
    throw Object.assign(new Error(validation.errors.map((e) => e.message).join("; ")), {
      code: "INVALID_SHAPE",
    });
  }
  await fsp.mkdir(WORLD_DIR, { recursive: true });
  const file = path.join(WORLD_DIR, `${name}.json`);
  let backup = "";
  try {
    backup = await _backup(file);
  } catch {
    // file may not exist yet (create flow); skip backup
  }
  await _writeJsonAtomic(file, content);
  return { backup_path: backup };
}

export async function createWorld(name: string): Promise<{ name: string }> {
  if (!isValidWorldName(name)) {
    throw Object.assign(new Error(`invalid world name: ${name}`), { code: "INVALID_NAME" });
  }
  const all = await listWorldFiles();
  if (all.includes(name)) {
    throw Object.assign(new Error(`world already exists: ${name}`), { code: "ALREADY_EXISTS" });
  }
  const seed: LorebookFile = {
    entries: [
      {
        keywords: ["example_keyword"],
        content: "Replace this with a real lorebook entry. Substring matched (case-insensitive) against the latest user message + last 4 turns.",
        position: "background",
      },
    ],
  };
  await fsp.mkdir(WORLD_DIR, { recursive: true });
  await _writeJsonAtomic(path.join(WORLD_DIR, `${name}.json`), seed);
  return { name };
}

export async function duplicateWorld(srcName: string): Promise<{ name: string }> {
  const src = await readWorld(srcName);
  const all = await listWorldFiles();
  // Pick "<src>_copy" / "<src>_copy2" / ...
  let candidate = `${srcName}_copy`;
  let i = 2;
  while (all.includes(candidate)) {
    candidate = `${srcName}_copy${i}`;
    i += 1;
  }
  if (!isValidWorldName(candidate)) {
    throw Object.assign(new Error(`could not derive a valid duplicate name from ${srcName}`), {
      code: "INVALID_NAME",
    });
  }
  await _writeJsonAtomic(path.join(WORLD_DIR, `${candidate}.json`), src.content);
  return { name: candidate };
}

export async function deleteWorld(name: string): Promise<{ backup_path: string }> {
  if (!isValidWorldName(name)) {
    throw Object.assign(new Error(`invalid world name: ${name}`), { code: "INVALID_NAME" });
  }
  // Refuse if any character is still mapped to this world.
  const mapping = await readMappingRaw();
  const inUseBy: string[] = [];
  for (const [charId, worldId] of Object.entries(mapping)) {
    if (worldId === name) inUseBy.push(charId);
  }
  if (inUseBy.length > 0) {
    throw Object.assign(
      new Error(`world '${name}' is still mapped to: ${inUseBy.join(", ")}`),
      { code: "WORLD_IN_USE" },
    );
  }
  const file = path.join(WORLD_DIR, `${name}.json`);
  const backup = await _backup(file);
  await fsp.unlink(file);
  return { backup_path: backup };
}

// ── mapping ─────────────────────────────────────────────────────────────────

async function readMappingRaw(): Promise<Record<string, string>> {
  let raw: unknown;
  try {
    raw = await _readJson(MAPPING_FILE);
  } catch {
    return {};
  }
  if (typeof raw !== "object" || raw === null) return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (k.startsWith("_")) continue;
    if (typeof v === "string" && v) out[k] = v;
  }
  return out;
}

async function listCharacterIds(): Promise<string[]> {
  let entries: string[] = [];
  try {
    entries = await fsp.readdir(PERSONA_DIR);
  } catch {
    return [];
  }
  const out: string[] = [];
  for (const f of entries) {
    const m = f.match(/^(char\d{2,3})\.json$/);
    if (m) out.push(m[1]);
  }
  out.sort();
  return out;
}

export async function readMapping(): Promise<MappingPayload> {
  const [mapping, characters, worlds] = await Promise.all([
    readMappingRaw(),
    listCharacterIds(),
    listWorldFiles(),
  ]);
  return { mapping, characters, worlds };
}

export async function writeMapping(
  next: Record<string, string>,
): Promise<{ backup_path: string }> {
  const characters = await listCharacterIds();
  const worlds = await listWorldFiles();
  const charSet = new Set(characters);
  const worldSet = new Set(worlds);
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(next)) {
    if (k === "" || k.startsWith("_")) continue;
    if (typeof v !== "string" || v === "") continue; // empty value = unset (legacy fallback)
    if (!charSet.has(k)) {
      throw Object.assign(new Error(`unknown character: ${k}`), { code: "UNKNOWN_CHARACTER" });
    }
    if (!worldSet.has(v)) {
      throw Object.assign(new Error(`unknown world: ${v}`), { code: "UNKNOWN_WORLD" });
    }
    cleaned[k] = v;
  }
  // Preserve the _doc passthrough on disk.
  const payload: Record<string, unknown> = {
    _doc:
      "Maps each character to its lorebook (world_info file). Lookup: world_info/<value>.json. Characters not present here fall back to world_info/<char_id>.json (legacy convention).",
    ...cleaned,
  };
  await fsp.mkdir(WORLD_DIR, { recursive: true });
  let backup = "";
  try {
    backup = await _backup(MAPPING_FILE);
  } catch {
    // mapping.json may not exist yet — skip backup
  }
  await _writeJsonAtomic(MAPPING_FILE, payload);
  return { backup_path: backup };
}

// ── summary list ────────────────────────────────────────────────────────────

export async function listWorldsSummary(): Promise<WorldSummary[]> {
  const [names, mapping] = await Promise.all([listWorldFiles(), readMappingRaw()]);
  // invert: world -> [chars]
  const byWorld: Record<string, string[]> = {};
  for (const [charId, worldId] of Object.entries(mapping)) {
    (byWorld[worldId] ||= []).push(charId);
  }
  const out: WorldSummary[] = [];
  for (const name of names) {
    const file = path.join(WORLD_DIR, `${name}.json`);
    const stat = await fsp.stat(file);
    let entry_count = 0;
    try {
      const content = (await _readJson(file)) as { entries?: unknown[] };
      entry_count = Array.isArray(content.entries) ? content.entries.length : 0;
    } catch {
      // unreadable — leave at 0
    }
    out.push({
      name,
      entry_count,
      mapped_chars: (byWorld[name] || []).slice().sort(),
      mtime_ms: stat.mtimeMs,
      size_bytes: stat.size,
    });
  }
  return out;
}

// previewMatches() lives in lorebook-meta.ts (client-safe) so client
// components like TestPane can import it without pulling in node:fs.
export { previewMatches, type EntryMatch } from "./lorebook-meta";
