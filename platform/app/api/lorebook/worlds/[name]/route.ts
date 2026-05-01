import { NextRequest, NextResponse } from "next/server";

import { deleteWorld, readMapping, readWorld, writeWorld } from "@/lib/lorebook";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteCtx = { params: { name: string } };

export async function GET(_req: NextRequest, { params }: RouteCtx) {
  try {
    const r = await readWorld(params.name);
    const m = await readMapping();
    const mapped_chars = Object.entries(m.mapping)
      .filter(([, v]) => v === params.name)
      .map(([k]) => k)
      .sort();
    return NextResponse.json({
      name: r.name,
      content: r.content,
      mtime_ms: r.mtime_ms,
      size_bytes: r.size_bytes,
      mapped_chars,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code === "ENOENT") {
      return NextResponse.json(
        { error: `unknown world: ${params.name}`, code: "UNKNOWN_WORLD" },
        { status: 404 },
      );
    }
    const status = e.code === "INVALID_NAME" || e.code === "INVALID_SHAPE" ? 422 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "WORLD_READ_FAILED" },
      { status },
    );
  }
}

type PutBody = { content?: unknown };

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
  if (body.content === undefined) {
    return NextResponse.json(
      { error: "missing 'content'", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  try {
    const r = await writeWorld(params.name, body.content);
    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_path: r.backup_path,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "INVALID_SHAPE" || e.code === "INVALID_NAME" ? 422 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "WRITE_FAILED" },
      { status },
    );
  }
}

export async function DELETE(_req: NextRequest, { params }: RouteCtx) {
  try {
    const r = await deleteWorld(params.name);
    return NextResponse.json({ ok: true, backup_path: r.backup_path });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "WORLD_IN_USE" ? 422 : e.code === "ENOENT" ? 404 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "DELETE_FAILED" },
      { status },
    );
  }
}
