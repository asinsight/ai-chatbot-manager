import { NextRequest, NextResponse } from "next/server";

import { readStageAssignments, writeStageAssignments } from "@/lib/workflows";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const assignments = await readStageAssignments();
    return NextResponse.json(assignments);
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "ASSIGNMENTS_READ_FAILED" },
      { status: 500 },
    );
  }
}

type PutBody = { standard?: string; hq?: string };

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
  if (body.standard === undefined && body.hq === undefined) {
    return NextResponse.json(
      { error: "must specify standard and/or hq", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  try {
    const result = await writeStageAssignments(body);
    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_path: result.backup_path,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "UNKNOWN_FILE" ? 422 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "ASSIGNMENTS_WRITE_FAILED" },
      { status },
    );
  }
}
