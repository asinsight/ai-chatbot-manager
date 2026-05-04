import { NextRequest, NextResponse } from "next/server";

import { duplicateWorld } from "@/lib/lorebook";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteCtx = { params: { name: string } };

export async function POST(_req: NextRequest, { params }: RouteCtx) {
  try {
    const r = await duplicateWorld(params.name);
    return NextResponse.json({ ok: true, name: r.name });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code === "ENOENT") {
      return NextResponse.json(
        { error: `unknown world: ${params.name}`, code: "UNKNOWN_WORLD" },
        { status: 404 },
      );
    }
    return NextResponse.json(
      { error: e.message, code: e.code ?? "DUPLICATE_FAILED" },
      { status: 500 },
    );
  }
}
