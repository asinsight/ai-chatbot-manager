import { NextResponse } from "next/server";

import { getStatus } from "@/lib/bot-process";
import { readEnvValues } from "@/lib/env-read";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [status, envValues] = await Promise.all([
      getStatus(),
      readEnvValues(["MAIN_BOT_TOKEN", "MAIN_BOT_USERNAME"]),
    ]);
    return NextResponse.json({
      ...status,
      main_bot: {
        token_set: envValues.MAIN_BOT_TOKEN.trim().length > 0,
        username_set: envValues.MAIN_BOT_USERNAME.trim().length > 0,
      },
    });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "STATUS_FAILED" },
      { status: 500 },
    );
  }
}
