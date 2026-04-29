import { NextRequest, NextResponse } from "next/server";
import fsp from "node:fs/promises";

import { backupEnv } from "@/lib/backup";
import {
  CATEGORIES,
  categoryFor,
  isEditable,
  isRecognized,
  READ_ONLY_KEYS,
} from "@/lib/env-categories";
import {
  applyUpdates,
  parseEnv,
  parseExampleComments,
  serializeEnv,
  type EnvLine,
} from "@/lib/env-parser";
import { ENV_EXAMPLE_FILE, ENV_FILE } from "@/lib/paths";
import { isSecret } from "@/lib/secrets";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type EnvVarPayload = {
  key: string;
  value: string;
  comment: string | null;
  is_secret: boolean;
  editable: boolean;
};

async function readEnvText(): Promise<string> {
  try {
    return await fsp.readFile(ENV_FILE, "utf8");
  } catch {
    return "";
  }
}

async function readExampleText(): Promise<string> {
  try {
    return await fsp.readFile(ENV_EXAMPLE_FILE, "utf8");
  } catch {
    return "";
  }
}

export async function GET() {
  try {
    const [envText, exampleText] = await Promise.all([
      readEnvText(),
      readExampleText(),
    ]);
    const lines = parseEnv(envText);
    const help = parseExampleComments(exampleText);

    // Collect every key seen in the .env file (var or comment-var).
    const seen = new Map<string, string>();
    for (const line of lines) {
      if (line.kind === "var" || line.kind === "comment-var") {
        seen.set(line.key, line.kind === "var" ? line.value : "");
      }
    }
    // Add keys that are documented in .env.example or in our static categories
    // but aren't yet present in .env (so the form shows blank inputs for them).
    for (const cat of CATEGORIES) {
      for (const k of cat.keys) if (!seen.has(k)) seen.set(k, "");
    }
    for (const k of Object.keys(help)) if (!seen.has(k)) seen.set(k, "");

    const buckets = new Map<string, EnvVarPayload[]>();
    for (const [key, value] of seen) {
      const cat = categoryFor(key);
      const payload: EnvVarPayload = {
        key,
        value,
        comment: help[key] ?? null,
        is_secret: isSecret(key),
        editable: isEditable(key),
      };
      if (!buckets.has(cat)) buckets.set(cat, []);
      buckets.get(cat)!.push(payload);
    }
    for (const arr of buckets.values()) arr.sort((a, b) => a.key.localeCompare(b.key));

    const orderedIds = [
      ...CATEGORIES.map((c) => c.id),
      ...Array.from(buckets.keys()).filter(
        (id) => !CATEGORIES.find((c) => c.id === id),
      ),
    ];
    const categories = orderedIds
      .filter((id) => buckets.has(id))
      .map((id) => {
        const c = CATEGORIES.find((x) => x.id === id);
        return {
          id,
          label: c ? c.label : "Misc",
          vars: buckets.get(id) ?? [],
        };
      });

    return NextResponse.json({ categories });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "ENV_READ_FAILED" },
      { status: 500 },
    );
  }
}

type PutBody = { updates?: Record<string, string> };

export async function PUT(req: NextRequest) {
  let body: PutBody;
  try {
    body = (await req.json()) as PutBody;
  } catch {
    return NextResponse.json(
      { error: "invalid JSON body", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  const updates = body.updates ?? {};
  const keys = Object.keys(updates);
  if (keys.length === 0) {
    return NextResponse.json(
      { error: "no updates provided", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }

  for (const key of keys) {
    if (!/^[A-Z_][A-Z0-9_]*$/.test(key)) {
      return NextResponse.json(
        { error: `invalid env key format: ${key}`, code: "INVALID_KEY" },
        { status: 422 },
      );
    }
    if (READ_ONLY_KEYS.has(key)) {
      return NextResponse.json(
        { error: `key is read-only: ${key}`, code: "READ_ONLY_KEY" },
        { status: 422 },
      );
    }
    if (!isRecognized(key)) {
      return NextResponse.json(
        { error: `unknown env key: ${key}`, code: "UNKNOWN_KEY" },
        { status: 422 },
      );
    }
    const value = updates[key];
    if (typeof value !== "string") {
      return NextResponse.json(
        { error: `value must be string for ${key}`, code: "INVALID_VALUE" },
        { status: 422 },
      );
    }
    if (/\r|\n/.test(value)) {
      return NextResponse.json(
        { error: `value contains newline for ${key}`, code: "INVALID_VALUE" },
        { status: 422 },
      );
    }
  }

  try {
    const envText = await readEnvText();
    const lines: EnvLine[] = parseEnv(envText);
    const updatedLines = applyUpdates(lines, updates);
    const serialized = serializeEnv(updatedLines);

    const backupPath = await backupEnv();
    await fsp.writeFile(ENV_FILE, serialized, "utf8");

    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_path: backupPath,
      updated_keys: keys,
    });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "ENV_WRITE_FAILED" },
      { status: 500 },
    );
  }
}
