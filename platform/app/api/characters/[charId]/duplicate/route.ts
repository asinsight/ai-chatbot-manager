import { NextResponse } from "next/server";

import { createCharacter } from "@/lib/characters";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  _req: Request,
  { params }: { params: { charId: string } },
) {
  try {
    const result = await createCharacter({ from: params.charId });
    return NextResponse.json({
      ok: true,
      charId: result.charId,
      restart_required: true,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status =
      e.code === "INVALID_CHAR_ID" || e.code === "UNKNOWN_CHARACTER"
        ? 404
        : e.code === "NO_FREE_SLOT"
          ? 409
          : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "CHAR_DUPLICATE_FAILED" },
      { status },
    );
  }
}
