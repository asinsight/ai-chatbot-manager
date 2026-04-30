import { NextRequest, NextResponse } from "next/server";

import {
  createCharacter,
  listCharacters,
} from "@/lib/characters";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const characters = await listCharacters();
    return NextResponse.json({ characters });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "CHAR_LIST_FAILED" },
      { status: 500 },
    );
  }
}

type PostBody = { from?: string };

export async function POST(req: NextRequest) {
  let body: PostBody;
  try {
    body = (await req.json().catch(() => ({}))) as PostBody;
  } catch {
    body = {};
  }
  try {
    const result = await createCharacter({ from: body.from });
    return NextResponse.json({
      ok: true,
      charId: result.charId,
      restart_required: true,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "INVALID_CHAR_ID" || e.code === "UNKNOWN_CHARACTER"
      ? 422
      : e.code === "NO_FREE_SLOT"
        ? 409
        : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "CHAR_CREATE_FAILED" },
      { status },
    );
  }
}
