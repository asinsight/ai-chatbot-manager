import fsp from "node:fs/promises";
import path from "node:path";

import { NextResponse } from "next/server";

import { REPO_ROOT } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SCHEMA_PATH = path.join(REPO_ROOT, "character_card_schema.json");

export async function GET() {
  try {
    const text = await fsp.readFile(SCHEMA_PATH, "utf8");
    const content = JSON.parse(text) as unknown;
    return NextResponse.json({
      file_path: "character_card_schema.json",
      content,
    });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "SCHEMA_READ_FAILED" },
      { status: 500 },
    );
  }
}
