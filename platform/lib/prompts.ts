import fsp from "node:fs/promises";
import path from "node:path";

import { BACKUP_DIR } from "./backup";
import { REPO_ROOT } from "./paths";

export const GROK_PROMPT_KEYS = [
  "system",
  "video_analyzer",
  "random",
  "classify",
  "partial_edit",
] as const;

export const SYSTEM_PROMPT_KEYS = [
  "master_prompt",
  "image_signal_format",
  "image_signal_regex",
] as const;

export type PromptFile = "grok" | "system";

const FILE_PATHS: Record<PromptFile, string> = {
  grok: path.join(REPO_ROOT, "config", "grok_prompts.json"),
  system: path.join(REPO_ROOT, "config", "system_prompt.json"),
};

const FILE_BASENAMES: Record<PromptFile, string> = {
  grok: "grok_prompts.json",
  system: "system_prompt.json",
};

const REQUIRED_KEYS: Record<PromptFile, readonly string[]> = {
  grok: GROK_PROMPT_KEYS,
  system: ["master_prompt", "image_signal_format"],
};

export type PromptPayload = {
  file: PromptFile;
  keys: { name: string; value: string; size: number }[];
};

export async function readPromptFile(file: PromptFile): Promise<PromptPayload> {
  const text = await fsp.readFile(FILE_PATHS[file], "utf8");
  const parsed = JSON.parse(text) as Record<string, unknown>;
  const keys: PromptPayload["keys"] = [];
  for (const k of Object.keys(parsed)) {
    const v = parsed[k];
    if (typeof v !== "string") continue;
    keys.push({ name: k, value: v, size: v.length });
  }
  return { file, keys };
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

async function backupPromptFile(file: PromptFile): Promise<string> {
  await fsp.mkdir(BACKUP_DIR, { recursive: true });
  const target = path.join(
    BACKUP_DIR,
    `${FILE_BASENAMES[file]}.${timestamp()}.bak`,
  );
  const tmp = `${target}.partial`;
  await fsp.copyFile(FILE_PATHS[file], tmp);
  await fsp.rename(tmp, target);
  return target;
}

export type LintIssue = {
  key: string;
  severity: "warning" | "error";
  message: string;
  /** 1-indexed line number where the issue was detected, when known. */
  line?: number;
};

const PLACEHOLDER_OK = /\$\{[A-Za-z_][A-Za-z0-9_]*\}/g;
const UNTERMINATED = /\$\{[^}\n]*$/m;
const SPACED = /\$\s+\{/;
const EMPTY_BRACES = /\$\{\s*\}/;

function lintPlaceholdersInValue(key: string, value: string): LintIssue[] {
  const issues: LintIssue[] = [];

  // unterminated ${...
  const lines = value.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    // line containing `${` but not closed before line end
    let cursor = 0;
    while (true) {
      const open = ln.indexOf("${", cursor);
      if (open < 0) break;
      const close = ln.indexOf("}", open);
      if (close < 0) {
        issues.push({
          key,
          severity: "warning",
          line: i + 1,
          message: `unterminated placeholder near \`${ln.slice(open, open + 20)}…\``,
        });
        break;
      }
      const inner = ln.slice(open + 2, close);
      if (inner.trim() === "") {
        issues.push({
          key,
          severity: "warning",
          line: i + 1,
          message: "empty placeholder `${}`",
        });
      } else if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(inner)) {
        issues.push({
          key,
          severity: "warning",
          line: i + 1,
          message: `placeholder \`\${${inner}}\` has unusual characters`,
        });
      }
      cursor = close + 1;
    }
  }

  // `$ {var}` (space between $ and {)
  if (SPACED.test(value)) {
    issues.push({
      key,
      severity: "warning",
      message: "found `$ {...}` (space between $ and {) — likely a typo",
    });
  }

  return issues;
}

export function lintPlaceholders(value: string): LintIssue[] {
  return lintPlaceholdersInValue("", value);
}

export function validatePayload(
  file: PromptFile,
  updates: Record<string, string>,
): LintIssue[] {
  const issues: LintIssue[] = [];
  const required = REQUIRED_KEYS[file];

  for (const [key, value] of Object.entries(updates)) {
    if (typeof value !== "string") {
      issues.push({
        key,
        severity: "error",
        message: `value must be a string, got ${typeof value}`,
      });
      continue;
    }
    if (required.includes(key) && value.trim().length === 0) {
      issues.push({
        key,
        severity: "error",
        message: "required key cannot be empty",
      });
    }
    issues.push(...lintPlaceholdersInValue(key, value));
  }
  return issues;
}

export async function writePromptFile(
  file: PromptFile,
  updates: Record<string, string>,
): Promise<{ backup_path: string; warnings: LintIssue[] }> {
  const issues = validatePayload(file, updates);
  const errors = issues.filter((i) => i.severity === "error");
  if (errors.length > 0) {
    const err = new Error(
      errors.map((e) => `${e.key}: ${e.message}`).join("; "),
    );
    (err as NodeJS.ErrnoException).code = "INVALID_PAYLOAD";
    throw err;
  }
  // load + merge — preserve existing keys not in updates
  const text = await fsp.readFile(FILE_PATHS[file], "utf8");
  const current = JSON.parse(text) as Record<string, unknown>;
  for (const [key, value] of Object.entries(updates)) {
    current[key] = value;
  }
  // re-check required keys after merge
  for (const k of REQUIRED_KEYS[file]) {
    const v = current[k];
    if (typeof v !== "string" || v.trim() === "") {
      const err = new Error(`required key missing or empty after merge: ${k}`);
      (err as NodeJS.ErrnoException).code = "MISSING_REQUIRED_KEY";
      throw err;
    }
  }
  const backupPath = await backupPromptFile(file);
  const serialized = JSON.stringify(current, null, 2) + "\n";
  await fsp.writeFile(FILE_PATHS[file], serialized, "utf8");
  return {
    backup_path: backupPath,
    warnings: issues.filter((i) => i.severity === "warning"),
  };
}
