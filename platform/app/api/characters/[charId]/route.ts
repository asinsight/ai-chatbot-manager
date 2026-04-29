import { NextRequest, NextResponse } from "next/server";

import {
  deleteCharacter,
  readCharacter,
  writeCharacter,
  type CharacterCard,
} from "@/lib/characters";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: { charId: string } },
) {
  try {
    const card = await readCharacter(params.charId);
    return NextResponse.json(card);
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "UNKNOWN_CHARACTER" ? 404 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "CHAR_READ_FAILED" },
      { status },
    );
  }
}

type PutBody = Partial<Pick<CharacterCard, "persona" | "behaviors" | "images">>;

export async function PUT(
  req: NextRequest,
  { params }: { params: { charId: string } },
) {
  let body: PutBody;
  try {
    body = (await req.json()) as PutBody;
  } catch {
    return NextResponse.json(
      { error: "invalid JSON body", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  if (!body.persona || !body.behaviors || !body.images) {
    return NextResponse.json(
      {
        error: "persona, behaviors, and images all required in PUT body",
        code: "INCOMPLETE_BUNDLE",
      },
      { status: 400 },
    );
  }
  try {
    const card: CharacterCard = {
      charId: params.charId,
      persona: body.persona,
      behaviors: body.behaviors,
      images: body.images,
    };
    const result = await writeCharacter(params.charId, card);
    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_paths: result.backup_paths,
      warnings: result.warnings,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status =
      e.code === "INVALID_CARD" || e.code === "INVALID_CHAR_ID"
        ? 422
        : e.code === "UNKNOWN_CHARACTER"
          ? 404
          : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "CHAR_WRITE_FAILED" },
      { status },
    );
  }
}

export async function DELETE(
  _req: Request,
  { params }: { params: { charId: string } },
) {
  try {
    const result = await deleteCharacter(params.charId);
    return NextResponse.json({
      ok: true,
      restart_required: true,
      backup_dir: result.backup_dir,
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    const status = e.code === "INVALID_CHAR_ID" ? 422 : 500;
    return NextResponse.json(
      { error: e.message, code: e.code ?? "CHAR_DELETE_FAILED" },
      { status },
    );
  }
}
