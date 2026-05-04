import { NextRequest, NextResponse } from "next/server";
import fsp from "node:fs/promises";

import { backupEnv } from "@/lib/backup";
import { getConnectionDef } from "@/lib/connections";
import {
  applyUpdates,
  parseEnv,
  serializeEnv,
} from "@/lib/env-parser";
import { ENV_FILE } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type PutBody = { url?: string; token?: string };

export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const def = getConnectionDef(params.id);
  if (!def) {
    return NextResponse.json(
      { error: `unknown connection: ${params.id}`, code: "UNKNOWN_CONNECTION" },
      { status: 404 },
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

  const updates: Record<string, string> = {};
  if (body.url !== undefined) {
    if (typeof body.url !== "string" || /\r|\n/.test(body.url)) {
      return NextResponse.json(
        { error: "invalid url value", code: "INVALID_VALUE" },
        { status: 422 },
      );
    }
    updates[def.url_var] = body.url;
  }
  if (body.token !== undefined) {
    if (typeof body.token !== "string" || /\r|\n/.test(body.token)) {
      return NextResponse.json(
        { error: "invalid token value", code: "INVALID_VALUE" },
        { status: 422 },
      );
    }
    if (!def.token_var) {
      return NextResponse.json(
        {
          error: `connection ${def.id} has no token`,
          code: "TOKEN_NOT_SUPPORTED",
        },
        { status: 422 },
      );
    }
    if (!def.token_blank_allowed && body.token.trim() === "") {
      return NextResponse.json(
        {
          error: `${def.token_var} is required for ${def.id}`,
          code: "TOKEN_REQUIRED",
        },
        { status: 422 },
      );
    }
    updates[def.token_var] = body.token;
  }

  if (Object.keys(updates).length === 0) {
    return NextResponse.json(
      { error: "no updates provided", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }

  try {
    const text = await fsp.readFile(ENV_FILE, "utf8").catch(() => "");
    const lines = parseEnv(text);
    const updated = applyUpdates(lines, updates);
    const serialized = serializeEnv(updated);

    const backupPath = await backupEnv();
    await fsp.writeFile(ENV_FILE, serialized, "utf8");

    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_path: backupPath,
      updated_keys: Object.keys(updates),
    });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "CONNECTION_WRITE_FAILED" },
      { status: 500 },
    );
  }
}
