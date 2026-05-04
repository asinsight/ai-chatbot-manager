import { NextResponse } from "next/server";

import { start } from "@/lib/bot-process";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const result = await start();
    return NextResponse.json(result);
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code === "ALREADY_RUNNING") {
      return NextResponse.json(
        { error: e.message, code: e.code },
        { status: 409 },
      );
    }
    if (e.code === "MAIN_BOT_NOT_CONFIGURED") {
      return NextResponse.json(
        { error: e.message, code: e.code },
        { status: 422 },
      );
    }
    return NextResponse.json(
      { error: e.message, code: "START_FAILED" },
      { status: 500 },
    );
  }
}
