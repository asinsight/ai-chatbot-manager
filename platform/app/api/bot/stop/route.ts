import { NextResponse } from "next/server";

import { stop } from "@/lib/bot-process";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    await stop();
    return NextResponse.json({ ok: true });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code === "NOT_RUNNING") {
      return NextResponse.json(
        { error: e.message, code: e.code },
        { status: 409 },
      );
    }
    return NextResponse.json(
      { error: e.message, code: "STOP_FAILED" },
      { status: 500 },
    );
  }
}
