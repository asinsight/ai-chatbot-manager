import { NextRequest, NextResponse } from "next/server";

import {
  readPromptFile,
  writePromptFile,
} from "@/lib/prompts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const payload = await readPromptFile("system");
    return NextResponse.json(payload);
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "PROMPT_READ_FAILED" },
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
  if (Object.keys(updates).length === 0) {
    return NextResponse.json(
      { error: "no updates provided", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  try {
    const result = await writePromptFile("system", updates);
    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_path: result.backup_path,
      updated_keys: Object.keys(updates),
      warnings: result.warnings,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "INVALID_PAYLOAD" || e.code === "MISSING_REQUIRED_KEY"
      ? 422
      : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "PROMPT_WRITE_FAILED" },
      { status },
    );
  }
}
