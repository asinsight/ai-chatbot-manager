import { NextRequest, NextResponse } from "next/server";

import { createWorld, listWorldsSummary } from "@/lib/lorebook";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const worlds = await listWorldsSummary();
    return NextResponse.json({ worlds });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "WORLDS_LIST_FAILED" },
      { status: 500 },
    );
  }
}

type PostBody = { name?: string };

export async function POST(req: NextRequest) {
  let body: PostBody;
  try {
    body = (await req.json()) as PostBody;
  } catch {
    return NextResponse.json(
      { error: "invalid JSON body", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  if (typeof body.name !== "string" || !body.name) {
    return NextResponse.json(
      { error: "missing 'name'", code: "INVALID_NAME" },
      { status: 422 },
    );
  }
  try {
    const r = await createWorld(body.name);
    return NextResponse.json({ ok: true, name: r.name });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "INVALID_NAME" ? 422 : e.code === "ALREADY_EXISTS" ? 409 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "CREATE_FAILED" },
      { status },
    );
  }
}
