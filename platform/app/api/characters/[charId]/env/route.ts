import { NextRequest, NextResponse } from "next/server";
import fsp from "node:fs/promises";

import { backupEnv } from "@/lib/backup";
import { applyUpdates, parseEnv, serializeEnv } from "@/lib/env-parser";
import { ENV_FILE } from "@/lib/paths";
import { isSecret, maskValue } from "@/lib/secrets";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CHAR_ID_RE = /^char(\d{2,3})$/;

function keysFor(charId: string): {
  token: string;
  username: string;
} {
  return {
    token: `CHAR_BOT_${charId}`,
    username: `CHAR_USERNAME_${charId}`,
  };
}

export async function GET(
  _req: Request,
  { params }: { params: { charId: string } },
) {
  if (!CHAR_ID_RE.test(params.charId)) {
    return NextResponse.json(
      { error: "invalid charId", code: "INVALID_CHAR_ID" },
      { status: 422 },
    );
  }
  try {
    const text = await fsp.readFile(ENV_FILE, "utf8").catch(() => "");
    const lines = parseEnv(text);
    const k = keysFor(params.charId);
    const find = (key: string): string => {
      for (const line of lines) {
        if (line.kind === "var" && line.key === key) return line.value;
      }
      return "";
    };
    const out: Record<string, { value: string; masked: string | null; present: boolean }> = {};
    for (const [field, key] of Object.entries(k)) {
      const v = find(key);
      out[field] = {
        value: v,
        present: v.length > 0,
        masked: isSecret(key) && v ? maskValue(v) : null,
      };
    }
    return NextResponse.json({ charId: params.charId, fields: out, keys: k });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "CHAR_ENV_READ_FAILED" },
      { status: 500 },
    );
  }
}

type PutBody = {
  token?: string;
  username?: string;
};

export async function PUT(
  req: NextRequest,
  { params }: { params: { charId: string } },
) {
  if (!CHAR_ID_RE.test(params.charId)) {
    return NextResponse.json(
      { error: "invalid charId", code: "INVALID_CHAR_ID" },
      { status: 422 },
    );
  }
  let body: PutBody;
  try {
    body = (await req.json()) as PutBody;
  } catch {
    return NextResponse.json(
      { error: "invalid JSON body", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  const k = keysFor(params.charId);
  const updates: Record<string, string> = {};
  for (const [field, key] of Object.entries(k)) {
    const value = (body as Record<string, unknown>)[field];
    if (typeof value === "string") {
      if (/\r|\n/.test(value)) {
        return NextResponse.json(
          { error: `value contains newline for ${key}`, code: "INVALID_VALUE" },
          { status: 422 },
        );
      }
      updates[key] = value;
    }
  }
  if (Object.keys(updates).length === 0) {
    return NextResponse.json(
      { error: "no fields to update", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  try {
    const text = await fsp.readFile(ENV_FILE, "utf8");
    const lines = parseEnv(text);
    const updated = applyUpdates(lines, updates);
    const backupPath = await backupEnv();
    await fsp.writeFile(ENV_FILE, serializeEnv(updated), "utf8");
    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_path: backupPath,
      updated_keys: Object.keys(updates),
    });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "CHAR_ENV_WRITE_FAILED" },
      { status: 500 },
    );
  }
}
