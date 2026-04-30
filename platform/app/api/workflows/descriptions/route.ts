import { NextRequest, NextResponse } from "next/server";

import { readWorkflowDescriptions, writeWorkflowDescription } from "@/lib/workflows";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const content = await readWorkflowDescriptions();
    return NextResponse.json({ content });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "DESCRIPTIONS_READ_FAILED" },
      { status: 500 },
    );
  }
}

type PutBody = { filename?: string; description?: string };

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
  if (typeof body.filename !== "string" || typeof body.description !== "string") {
    return NextResponse.json(
      { error: "missing filename or description", code: "INVALID_PAYLOAD" },
      { status: 422 },
    );
  }
  try {
    const result = await writeWorkflowDescription(body.filename, body.description);
    return NextResponse.json({
      ok: true,
      backup_path: result.backup_path,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "UNKNOWN_FILE" ? 422 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "DESCRIPTIONS_WRITE_FAILED" },
      { status },
    );
  }
}
