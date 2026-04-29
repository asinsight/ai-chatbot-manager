import fsp from "node:fs/promises";
import path from "node:path";

import { backupEnv, BACKUP_DIR } from "./backup";
import { applyUpdates, parseEnv, serializeEnv } from "./env-parser";
import { ENV_FILE, REPO_ROOT } from "./paths";
import {
  BLANK_BEHAVIORS,
  BLANK_IMAGES,
  BLANK_PERSONA,
} from "./char-schema";
import { validatePersona, type ValidationIssue } from "./ajv";

const CHAR_ID_RE = /^char(\d{2,3})$/;

export type CharacterCard = {
  charId: string;
  persona: Record<string, unknown>;
  behaviors: Record<string, unknown>;
  images: Record<string, unknown>;
};

export type CharacterListEntry = {
  charId: string;
  name: string;
  profile_summary_ko: string;
  mtime: number;
};

const DELETED_DIR = path.join(BACKUP_DIR, "deleted");

const FILE_FOR = (kind: "persona" | "behaviors" | "images", charId: string): string =>
  path.join(REPO_ROOT, kind, `${charId}.json`);

async function _readJson(file: string): Promise<Record<string, unknown>> {
  const text = await fsp.readFile(file, "utf8");
  return JSON.parse(text) as Record<string, unknown>;
}

async function _writeJsonAtomic(file: string, content: unknown): Promise<void> {
  const serialized = JSON.stringify(content, null, 2) + "\n";
  const tmp = `${file}.partial`;
  await fsp.writeFile(tmp, serialized, "utf8");
  await fsp.rename(tmp, file);
}

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

async function _backupOne(file: string): Promise<string> {
  await fsp.mkdir(BACKUP_DIR, { recursive: true });
  const base = path.basename(file);
  const dir = path.basename(path.dirname(file));
  const target = path.join(BACKUP_DIR, `${dir}_${base}.${timestamp()}.bak`);
  const tmp = `${target}.partial`;
  await fsp.copyFile(file, tmp);
  await fsp.rename(tmp, target);
  return target;
}

function _envCharLines(charId: string): string[] {
  return [
    `TEST_CHAR_BOT_${charId}`,
    `TEST_CHAR_USERNAME_${charId}`,
    `PROD_CHAR_BOT_${charId}`,
    `PROD_CHAR_USERNAME_${charId}`,
  ];
}

async function _appendEnvCharLines(charId: string): Promise<void> {
  const text = await fsp.readFile(ENV_FILE, "utf8");
  const lines = parseEnv(text);
  const updates: Record<string, string> = {};
  for (const k of _envCharLines(charId)) {
    // skip keys that already exist (idempotent)
    if (
      !lines.some(
        (l) =>
          (l.kind === "var" || l.kind === "comment-var") && l.key === k,
      )
    ) {
      updates[k] = "";
    }
  }
  if (Object.keys(updates).length === 0) return;
  await backupEnv();
  const updated = applyUpdates(lines, updates);
  await fsp.writeFile(ENV_FILE, serializeEnv(updated), "utf8");
}

async function _removeEnvCharLines(charId: string): Promise<void> {
  const text = await fsp.readFile(ENV_FILE, "utf8");
  const lines = parseEnv(text);
  const targets = new Set(_envCharLines(charId));
  const filtered = lines.filter((l) => {
    if (l.kind === "var" && targets.has(l.key)) return false;
    if (l.kind === "comment-var" && targets.has(l.key)) return false;
    return true;
  });
  if (filtered.length === lines.length) return;
  await backupEnv();
  await fsp.writeFile(ENV_FILE, serializeEnv(filtered), "utf8");
}

export async function listCharacters(): Promise<CharacterListEntry[]> {
  const personaDir = path.join(REPO_ROOT, "persona");
  let entries: string[] = [];
  try {
    entries = await fsp.readdir(personaDir);
  } catch {
    return [];
  }
  const out: CharacterListEntry[] = [];
  for (const f of entries) {
    const m = f.match(/^(char\d{2,3})\.json$/);
    if (!m) continue;
    const charId = m[1];
    try {
      const personaPath = FILE_FOR("persona", charId);
      const content = await _readJson(personaPath);
      const stat = await fsp.stat(personaPath);
      // Use the latest mtime across the 3 files for ordering accuracy.
      let mtime = stat.mtimeMs;
      for (const kind of ["behaviors", "images"] as const) {
        try {
          const s = await fsp.stat(FILE_FOR(kind, charId));
          if (s.mtimeMs > mtime) mtime = s.mtimeMs;
        } catch {
          // missing companion file — listing still proceeds, but flag below.
        }
      }
      out.push({
        charId,
        name: typeof content.name === "string" ? content.name : charId,
        profile_summary_ko:
          typeof content.profile_summary_ko === "string"
            ? content.profile_summary_ko
            : "",
        mtime: Math.round(mtime),
      });
    } catch {
      // skip unreadable files
    }
  }
  out.sort((a, b) => b.mtime - a.mtime);
  return out;
}

export async function readCharacter(charId: string): Promise<CharacterCard> {
  if (!CHAR_ID_RE.test(charId)) {
    throw Object.assign(new Error(`invalid charId: ${charId}`), {
      code: "INVALID_CHAR_ID",
    });
  }
  try {
    const persona = await _readJson(FILE_FOR("persona", charId));
    const behaviors = await _readJson(FILE_FOR("behaviors", charId));
    const images = await _readJson(FILE_FOR("images", charId));
    return { charId, persona, behaviors, images };
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code === "ENOENT") {
      throw Object.assign(new Error(`unknown character: ${charId}`), {
        code: "UNKNOWN_CHARACTER",
      });
    }
    throw err;
  }
}

export type WriteResult = {
  backup_paths: string[];
  warnings: ValidationIssue[];
};

export async function writeCharacter(
  charId: string,
  card: CharacterCard,
): Promise<WriteResult> {
  if (!CHAR_ID_RE.test(charId)) {
    throw Object.assign(new Error(`invalid charId: ${charId}`), {
      code: "INVALID_CHAR_ID",
    });
  }
  const issues = validatePersona(card.persona);
  if (issues.length > 0) {
    throw Object.assign(
      new Error(
        issues.map((i) => `${i.path}: ${i.message}`).join("; "),
      ),
      { code: "INVALID_CARD" },
    );
  }
  const personaFile = FILE_FOR("persona", charId);
  const behaviorsFile = FILE_FOR("behaviors", charId);
  const imagesFile = FILE_FOR("images", charId);
  const existed = await fsp
    .access(personaFile)
    .then(() => true)
    .catch(() => false);
  const backups: string[] = [];
  if (existed) {
    backups.push(await _backupOne(personaFile));
    backups.push(await _backupOne(behaviorsFile).catch(() => ""));
    backups.push(await _backupOne(imagesFile).catch(() => ""));
  }
  await _writeJsonAtomic(personaFile, card.persona);
  await _writeJsonAtomic(behaviorsFile, card.behaviors);
  await _writeJsonAtomic(imagesFile, card.images);
  return { backup_paths: backups.filter(Boolean), warnings: [] };
}

export async function deleteCharacter(
  charId: string,
): Promise<{ backup_dir: string }> {
  if (!CHAR_ID_RE.test(charId)) {
    throw Object.assign(new Error(`invalid charId: ${charId}`), {
      code: "INVALID_CHAR_ID",
    });
  }
  const dir = path.join(DELETED_DIR, `${charId}.${timestamp()}`);
  await fsp.mkdir(dir, { recursive: true });
  for (const kind of ["persona", "behaviors", "images"] as const) {
    const src = FILE_FOR(kind, charId);
    const dst = path.join(dir, `${kind}.json`);
    try {
      await fsp.rename(src, dst);
    } catch (err) {
      const e = err as NodeJS.ErrnoException;
      if (e.code !== "ENOENT") throw err;
    }
  }
  await _removeEnvCharLines(charId);
  return { backup_dir: dir };
}

export async function nextFreeCharId(): Promise<string> {
  const personaDir = path.join(REPO_ROOT, "persona");
  let entries: string[] = [];
  try {
    entries = await fsp.readdir(personaDir);
  } catch {
    return "char01";
  }
  const used = new Set<number>();
  for (const f of entries) {
    const m = f.match(/^char(\d{2,3})\.json$/);
    if (m) used.add(parseInt(m[1], 10));
  }
  for (let i = 1; i < 1000; i++) {
    if (!used.has(i)) return `char${String(i).padStart(2, "0")}`;
  }
  throw Object.assign(new Error("no free charNN slot"), {
    code: "NO_FREE_SLOT",
  });
}

export async function createCharacter(opts: {
  from?: string;
}): Promise<{ charId: string }> {
  const charId = await nextFreeCharId();

  let persona: Record<string, unknown>;
  let behaviors: Record<string, unknown>;
  let images: Record<string, unknown>;

  if (opts.from) {
    if (!CHAR_ID_RE.test(opts.from)) {
      throw Object.assign(new Error(`invalid source charId: ${opts.from}`), {
        code: "INVALID_CHAR_ID",
      });
    }
    const src = await readCharacter(opts.from);
    persona = { ...src.persona };
    behaviors = JSON.parse(JSON.stringify(src.behaviors)) as Record<
      string,
      unknown
    >;
    images = JSON.parse(JSON.stringify(src.images)) as Record<string, unknown>;
    const baseName = typeof persona.name === "string" ? persona.name : "";
    persona.name = `Copy of ${baseName}`;
    persona.anchor_image = "";
    if ("char_id" in images) images.char_id = charId;
  } else {
    persona = { ...BLANK_PERSONA };
    behaviors = JSON.parse(JSON.stringify(BLANK_BEHAVIORS)) as Record<
      string,
      unknown
    >;
    images = BLANK_IMAGES(charId);
  }

  await _writeJsonAtomic(FILE_FOR("persona", charId), persona);
  await _writeJsonAtomic(FILE_FOR("behaviors", charId), behaviors);
  await _writeJsonAtomic(FILE_FOR("images", charId), images);
  await _appendEnvCharLines(charId);
  return { charId };
}
