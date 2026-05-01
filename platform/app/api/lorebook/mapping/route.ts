import { NextRequest, NextResponse } from "next/server";

import { readMapping, writeMapping } from "@/lib/lorebook";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const payload = await readMapping();
    return NextResponse.json(payload);
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "MAPPING_READ_FAILED" },
      { status: 500 },
    );
  }
}

type PutBody = { mapping?: Record<string, string> };

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
  if (!body.mapping || typeof body.mapping !== "object") {
    return NextResponse.json(
      { error: "missing 'mapping'", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  try {
    const r = await writeMapping(body.mapping);
    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_path: r.backup_path,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "UNKNOWN_WORLD" || e.code === "UNKNOWN_CHARACTER" ? 422 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "WRITE_FAILED" },
      { status },
    );
  }
}
