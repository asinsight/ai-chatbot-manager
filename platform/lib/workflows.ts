import fsp from "node:fs/promises";
import path from "node:path";

import { backupEnv, BACKUP_DIR } from "./backup";
import { applyUpdates, parseEnv, serializeEnv } from "./env-parser";
import { ENV_FILE, REPO_ROOT } from "./paths";
import {
  isAssignableWorkflow,
  type SafeFields,
  type StageAssignments,
  type WorkflowFacts,
  type WorkflowSummary,
} from "./workflows-meta";

export {
  isAssignableWorkflow,
  type SafeFields,
  type StageAssignments,
  type WorkflowFacts,
  type WorkflowSummary,
  type WorkflowStage,
} from "./workflows-meta";

const WORKFLOW_DIR = path.join(REPO_ROOT, "comfyui_workflow");
const DESCRIPTIONS_FILE = path.join(REPO_ROOT, "config", "workflow_descriptions.json");
const DEFAULT_STANDARD = "comfyui_workflow/main_character_build.json";
const DEFAULT_HQ = "comfyui_workflow/main_character_build_highqual.json";

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
  await fsp.copyFile(file, tmp);
  await fsp.rename(tmp, target);
  return target;
}

// ── workflow files ──────────────────────────────────────────────────────────

export async function listWorkflowFiles(): Promise<string[]> {
  const entries = await fsp.readdir(WORKFLOW_DIR);
  return entries
    .filter((f) => f.endsWith(".json"))
    .sort();
}

export async function readWorkflow(
  name: string,
): Promise<{ name: string; content: object; mtime_ms: number; size_bytes: number; facts: WorkflowFacts }> {
  if (!_isValidName(name)) {
    const err = new Error(`invalid workflow name: ${name}`);
    (err as NodeJS.ErrnoException).code = "INVALID_NAME";
    throw err;
  }
  const file = path.join(WORKFLOW_DIR, name);
  const [stat, content] = await Promise.all([fsp.stat(file), _readJson(file)]);
  if (typeof content !== "object" || content === null || Array.isArray(content)) {
    const err = new Error(`workflow ${name} is not an object`);
    (err as NodeJS.ErrnoException).code = "INVALID_SHAPE";
    throw err;
  }
  return {
    name,
    content: content as object,
    mtime_ms: stat.mtimeMs,
    size_bytes: stat.size,
    facts: computeFacts(content as Record<string, unknown>, stat.size),
  };
}

function _isValidName(name: string): boolean {
  return /^[A-Za-z0-9_.-]+\.json$/.test(name) && !name.includes("..");
}

// ── auto-facts ──────────────────────────────────────────────────────────────

// Post-processing detector — node `class_type` patterns we treat as a "refiner"
// signal: any KSamplerAdvanced second-stage, any *Upscale*, any *Detailer* (the
// HQ workflow uses FaceDetailer / DetailerForEach), and explicit *Refiner*.
const REFINER_RE = /^(KSamplerAdvanced|.*Upscale.*|UltimateSDUpscale.*|.*Refiner.*|.*Detailer.*)$/;

export function computeFacts(content: Record<string, unknown>, sizeBytes: number): WorkflowFacts {
  let nodeCount = 0;
  let stepsTotal = 0;
  let hasRefiner = false;
  for (const [, node] of Object.entries(content)) {
    if (typeof node !== "object" || node === null) continue;
    const n = node as { class_type?: unknown; inputs?: unknown };
    if (typeof n.class_type !== "string") continue;
    nodeCount += 1;
    if (REFINER_RE.test(n.class_type)) hasRefiner = true;
    if (n.class_type === "KSampler" || n.class_type === "KSamplerAdvanced") {
      const inputs = n.inputs;
      if (typeof inputs === "object" && inputs !== null) {
        const steps = (inputs as { steps?: unknown }).steps;
        if (typeof steps === "number" && Number.isFinite(steps)) {
          stepsTotal += steps;
        }
      }
    }
  }
  return {
    node_count: nodeCount,
    sampler_steps_total: stepsTotal,
    has_refiner_or_upscaler: hasRefiner,
    size_bytes: sizeBytes,
  };
}

// ── safe-field extraction ───────────────────────────────────────────────────

function _findNodeBy(
  content: Record<string, unknown>,
  predicate: (node: { class_type: string; meta_title: string; inputs: Record<string, unknown> }) => boolean,
): { id: string; node: Record<string, unknown> } | null {
  for (const [id, raw] of Object.entries(content)) {
    if (typeof raw !== "object" || raw === null) continue;
    const n = raw as { class_type?: unknown; inputs?: unknown; _meta?: unknown };
    if (typeof n.class_type !== "string") continue;
    const inputs = (typeof n.inputs === "object" && n.inputs !== null ? n.inputs : {}) as Record<string, unknown>;
    const meta = (typeof n._meta === "object" && n._meta !== null ? n._meta : {}) as { title?: unknown };
    const title = typeof meta.title === "string" ? meta.title : "";
    if (predicate({ class_type: n.class_type, meta_title: title, inputs })) {
      return { id, node: raw as Record<string, unknown> };
    }
  }
  return null;
}

export function extractSafeFields(content: object): SafeFields {
  const c = content as Record<string, unknown>;
  const ckptHit = _findNodeBy(c, ({ class_type }) => class_type === "CheckpointLoaderSimple");
  const checkpoint = ckptHit
    ? (() => {
        const inputs = ckptHit.node.inputs as Record<string, unknown>;
        const v = inputs?.ckpt_name;
        return typeof v === "string" ? v : null;
      })()
    : null;

  const sampHit = _findNodeBy(c, ({ class_type }) => class_type === "KSampler");
  const ksampler = sampHit
    ? (() => {
        const inputs = sampHit.node.inputs as Record<string, unknown>;
        const seed = typeof inputs?.seed === "number" ? (inputs.seed as number) : 0;
        const cfg = typeof inputs?.cfg === "number" ? (inputs.cfg as number) : 0;
        const steps = typeof inputs?.steps === "number" ? (inputs.steps as number) : 0;
        const sampler_name = typeof inputs?.sampler_name === "string" ? (inputs.sampler_name as string) : "";
        const scheduler = typeof inputs?.scheduler === "string" ? (inputs.scheduler as string) : "";
        return { seed, cfg, steps, sampler_name, scheduler };
      })()
    : null;

  const saveHit = _findNodeBy(c, ({ class_type }) => class_type === "SaveImage");
  const save_filename_prefix = saveHit
    ? (() => {
        const inputs = saveHit.node.inputs as Record<string, unknown>;
        const v = inputs?.filename_prefix;
        return typeof v === "string" ? v : null;
      })()
    : null;

  return { checkpoint, ksampler, save_filename_prefix };
}

export async function writeWorkflowSafeFields(
  name: string,
  fields: Partial<SafeFields>,
): Promise<{ backup_path: string }> {
  const file = path.join(WORKFLOW_DIR, name);
  const current = (await _readJson(file)) as Record<string, unknown>;

  if (fields.checkpoint !== undefined && fields.checkpoint !== null) {
    const hit = _findNodeBy(current, ({ class_type }) => class_type === "CheckpointLoaderSimple");
    if (hit) {
      const inputs = hit.node.inputs as Record<string, unknown>;
      inputs.ckpt_name = fields.checkpoint;
    }
  }
  if (fields.ksampler) {
    const hit = _findNodeBy(current, ({ class_type }) => class_type === "KSampler");
    if (hit) {
      const inputs = hit.node.inputs as Record<string, unknown>;
      const k = fields.ksampler;
      if (k.seed !== undefined) inputs.seed = k.seed;
      if (k.cfg !== undefined) inputs.cfg = k.cfg;
      if (k.steps !== undefined) inputs.steps = k.steps;
      if (k.sampler_name !== undefined) inputs.sampler_name = k.sampler_name;
      if (k.scheduler !== undefined) inputs.scheduler = k.scheduler;
    }
  }
  if (fields.save_filename_prefix !== undefined && fields.save_filename_prefix !== null) {
    const hit = _findNodeBy(current, ({ class_type }) => class_type === "SaveImage");
    if (hit) {
      const inputs = hit.node.inputs as Record<string, unknown>;
      inputs.filename_prefix = fields.save_filename_prefix;
    }
  }

  const backup = await _backup(file);
  await _writeJsonAtomic(file, current);
  return { backup_path: backup };
}

// ── shape validation (Replace flow) ─────────────────────────────────────────

export type ValidationError = { code: string; message: string };

export function validateWorkflowShape(content: unknown): { ok: true } | { ok: false; errors: ValidationError[] } {
  const errors: ValidationError[] = [];
  if (typeof content !== "object" || content === null || Array.isArray(content)) {
    return { ok: false, errors: [{ code: "INVALID_SHAPE", message: "root must be an object" }] };
  }
  const c = content as Record<string, unknown>;
  for (const [id, raw] of Object.entries(c)) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      errors.push({ code: "INVALID_SHAPE", message: `node ${id} must be an object` });
      continue;
    }
    const n = raw as { class_type?: unknown; inputs?: unknown };
    if (typeof n.class_type !== "string") {
      errors.push({ code: "INVALID_SHAPE", message: `node ${id} missing class_type` });
    }
    if (typeof n.inputs !== "object" || n.inputs === null || Array.isArray(n.inputs)) {
      errors.push({ code: "INVALID_SHAPE", message: `node ${id} missing inputs object` });
    }
  }
  if (errors.length > 0) return { ok: false, errors };

  const ckpt = _findNodeBy(c, ({ class_type }) => class_type === "CheckpointLoaderSimple");
  if (!ckpt) {
    errors.push({
      code: "NO_CHECKPOINT_LOADER",
      message: "workflow must contain a CheckpointLoaderSimple node",
    });
  }

  const positive = _findNodeBy(
    c,
    ({ class_type, meta_title }) => class_type === "CLIPTextEncode" && meta_title === "Positive",
  );
  if (!positive) {
    errors.push({
      code: "PLACEHOLDER_MISSING",
      message: "no CLIPTextEncode node with _meta.title === 'Positive' (where %prompt% lives)",
    });
  } else {
    const inputs = positive.node.inputs as Record<string, unknown>;
    const text = typeof inputs?.text === "string" ? inputs.text : "";
    if (!text.includes("%prompt%")) {
      errors.push({
        code: "PLACEHOLDER_MISSING",
        message: `Positive node ${positive.id} (CLIPTextEncode) inputs.text must contain the literal token %prompt% — runtime injection in src/comfyui.py:121 relies on it`,
      });
    }
  }

  const negative = _findNodeBy(
    c,
    ({ class_type, meta_title }) => class_type === "CLIPTextEncode" && meta_title === "Negative",
  );
  if (!negative) {
    errors.push({
      code: "PLACEHOLDER_MISSING",
      message: "no CLIPTextEncode node with _meta.title === 'Negative' (where %negative_prompt% lives)",
    });
  } else {
    const inputs = negative.node.inputs as Record<string, unknown>;
    const text = typeof inputs?.text === "string" ? inputs.text : "";
    if (!text.includes("%negative_prompt%")) {
      errors.push({
        code: "PLACEHOLDER_MISSING",
        message: `Negative node ${negative.id} (CLIPTextEncode) inputs.text must contain the literal token %negative_prompt% — runtime injection in src/comfyui.py:122 relies on it`,
      });
    }
  }

  return errors.length === 0 ? { ok: true } : { ok: false, errors };
}

export async function replaceWorkflow(
  name: string,
  content: unknown,
): Promise<{ backup_path: string }> {
  const validation = validateWorkflowShape(content);
  if (!validation.ok) {
    const err = new Error(validation.errors.map((e) => e.message).join("; "));
    (err as NodeJS.ErrnoException).code = validation.errors[0]?.code ?? "INVALID_SHAPE";
    throw err;
  }
  const file = path.join(WORKFLOW_DIR, name);
  const backup = await _backup(file);
  await _writeJsonAtomic(file, content);
  return { backup_path: backup };
}

// ── stage assignments (.env-backed) ─────────────────────────────────────────

function _basenameOrDefault(value: string | undefined, fallback: string): string {
  const v = (value ?? "").trim();
  if (v === "") return path.basename(fallback);
  // Accept either a basename or "comfyui_workflow/<basename>" — normalize to basename for the UI dropdown.
  return path.basename(v);
}

export async function readStageAssignments(): Promise<StageAssignments> {
  const text = await fsp.readFile(ENV_FILE, "utf8");
  const lines = parseEnv(text);
  let standardRaw: string | undefined;
  let hqRaw: string | undefined;
  for (const line of lines) {
    if (line.kind === "var") {
      if (line.key === "COMFYUI_WORKFLOW") standardRaw = line.value;
      if (line.key === "COMFYUI_WORKFLOW_HQ") hqRaw = line.value;
    }
  }
  const all = await listWorkflowFiles();
  return {
    standard: _basenameOrDefault(standardRaw, DEFAULT_STANDARD),
    hq: _basenameOrDefault(hqRaw, DEFAULT_HQ),
    options: all.filter(isAssignableWorkflow),
  };
}

export async function writeStageAssignments(
  next: Partial<Pick<StageAssignments, "standard" | "hq">>,
): Promise<{ backup_path: string }> {
  const all = await listWorkflowFiles();
  const updates: Record<string, string> = {};
  if (next.standard !== undefined) {
    if (!all.includes(next.standard) || !isAssignableWorkflow(next.standard)) {
      const err = new Error(`unknown or non-assignable file: ${next.standard}`);
      (err as NodeJS.ErrnoException).code = "UNKNOWN_FILE";
      throw err;
    }
    updates.COMFYUI_WORKFLOW = `comfyui_workflow/${next.standard}`;
  }
  if (next.hq !== undefined) {
    if (!all.includes(next.hq) || !isAssignableWorkflow(next.hq)) {
      const err = new Error(`unknown or non-assignable file: ${next.hq}`);
      (err as NodeJS.ErrnoException).code = "UNKNOWN_FILE";
      throw err;
    }
    updates.COMFYUI_WORKFLOW_HQ = `comfyui_workflow/${next.hq}`;
  }
  const backupPath = await backupEnv();
  const text = await fsp.readFile(ENV_FILE, "utf8");
  const merged = applyUpdates(parseEnv(text), updates);
  await fsp.writeFile(ENV_FILE, serializeEnv(merged), "utf8");
  return { backup_path: backupPath };
}

// ── descriptions ────────────────────────────────────────────────────────────

export async function readWorkflowDescriptions(): Promise<Record<string, string>> {
  try {
    const obj = (await _readJson(DESCRIPTIONS_FILE)) as Record<string, unknown>;
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(obj)) {
      if (k.startsWith("_")) continue;
      if (typeof v === "string") out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

export async function writeWorkflowDescription(
  name: string,
  description: string,
): Promise<{ backup_path: string }> {
  if (!_isValidName(name)) {
    const err = new Error(`invalid workflow name: ${name}`);
    (err as NodeJS.ErrnoException).code = "UNKNOWN_FILE";
    throw err;
  }
  // Guard against editing the "_doc" key or arbitrary new keys.
  const exists = (await listWorkflowFiles()).includes(name);
  if (!exists) {
    const err = new Error(`workflow file not found: ${name}`);
    (err as NodeJS.ErrnoException).code = "UNKNOWN_FILE";
    throw err;
  }

  let current: Record<string, unknown>;
  try {
    current = (await _readJson(DESCRIPTIONS_FILE)) as Record<string, unknown>;
  } catch {
    current = {
      _doc:
        "Free-form description shown next to each comfyui_workflow/*.json on the platform admin /workflows page. Editable in the UI; the bot does not read this file.",
    };
  }
  current[name] = description;

  const backup = await _backup(DESCRIPTIONS_FILE).catch(() => "");
  await _writeJsonAtomic(DESCRIPTIONS_FILE, current);
  return { backup_path: backup };
}

// ── summary list (used by /api/workflows GET) ───────────────────────────────

export async function listWorkflowsSummary(): Promise<WorkflowSummary[]> {
  const [files, descriptions, assignments] = await Promise.all([
    listWorkflowFiles(),
    readWorkflowDescriptions(),
    readStageAssignments(),
  ]);
  const out: WorkflowSummary[] = [];
  for (const name of files) {
    const file = path.join(WORKFLOW_DIR, name);
    const stat = await fsp.stat(file);
    let facts: WorkflowFacts = {
      node_count: 0,
      sampler_steps_total: 0,
      has_refiner_or_upscaler: false,
      size_bytes: stat.size,
    };
    try {
      const content = (await _readJson(file)) as Record<string, unknown>;
      facts = computeFacts(content, stat.size);
    } catch {
      // leave facts at defaults if the file can't be parsed
    }
    const stage_badges: ("standard" | "hq")[] = [];
    if (assignments.standard === name) stage_badges.push("standard");
    if (assignments.hq === name) stage_badges.push("hq");
    out.push({
      name,
      size_bytes: stat.size,
      mtime_ms: stat.mtimeMs,
      facts,
      description: descriptions[name] ?? "",
      stage_badges,
      assignable: isAssignableWorkflow(name),
    });
  }
  return out;
}
