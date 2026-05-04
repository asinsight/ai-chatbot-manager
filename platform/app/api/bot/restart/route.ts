import { NextResponse } from "next/server";

import { restart } from "@/lib/bot-process";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const result = await restart();
    return NextResponse.json(result);
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "RESTART_FAILED" },
      { status: 500 },
    );
  }
}
