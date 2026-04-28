import { NextResponse } from "next/server";

import { getStatus } from "@/lib/bot-process";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const status = await getStatus();
    return NextResponse.json(status);
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "STATUS_FAILED" },
      { status: 500 },
    );
  }
}
