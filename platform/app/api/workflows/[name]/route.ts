import { NextRequest, NextResponse } from "next/server";

import {
  extractSafeFields,
  readWorkflow,
  replaceWorkflow,
  writeWorkflowSafeFields,
  type SafeFields,
} from "@/lib/workflows";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteCtx = { params: { name: string } };

export async function GET(_req: NextRequest, { params }: RouteCtx) {
  try {
    const r = await readWorkflow(params.name);
    return NextResponse.json({
      name: r.name,
      content: r.content,
      mtime_ms: r.mtime_ms,
      size_bytes: r.size_bytes,
      facts: r.facts,
      safe_fields: extractSafeFields(r.content),
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "INVALID_NAME" || e.code === "INVALID_SHAPE" ? 422 : 500;
    if (e.code === "ENOENT") {
      return NextResponse.json(
        { error: `unknown workflow: ${params.name}`, code: "UNKNOWN_WORKFLOW" },
        { status: 404 },
      );
    }
    return NextResponse.json(
      { error: e.message, code: e.code ?? "WORKFLOW_READ_FAILED" },
      { status },
    );
  }
}

type PutBody =
  | { kind: "safe_fields"; fields: Partial<SafeFields> }
  | { kind: "replace"; content: object };

export async function PUT(req: NextRequest, { params }: RouteCtx) {
  let body: PutBody;
  try {
    body = (await req.json()) as PutBody;
  } catch {
    return NextResponse.json(
      { error: "invalid JSON body", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  try {
    if (body.kind === "safe_fields") {
      const result = await writeWorkflowSafeFields(params.name, body.fields);
      return NextResponse.json({
        ok: true,
        restart_required: true,
        backup_path: result.backup_path,
      });
    }
    if (body.kind === "replace") {
      const result = await replaceWorkflow(params.name, body.content);
      return NextResponse.json({
        ok: true,
        restart_required: true,
        backup_path: result.backup_path,
      });
    }
    return NextResponse.json(
      { error: "unknown kind — expected 'safe_fields' or 'replace'", code: "BAD_REQUEST" },
      { status: 400 },
    );
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const code = e.code ?? "WORKFLOW_WRITE_FAILED";
    const status =
      code === "INVALID_SHAPE" || code === "NO_CHECKPOINT_LOADER" || code === "PLACEHOLDER_MISSING"
        ? 422
        : 500;
    return NextResponse.json({ error: e.message, code }, { status });
  }
}
