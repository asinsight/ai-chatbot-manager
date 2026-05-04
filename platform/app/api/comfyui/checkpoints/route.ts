import { NextResponse } from "next/server";

import { fetchCheckpoints } from "@/lib/comfyui-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const result = await fetchCheckpoints();
  if (!result.ok) {
    return NextResponse.json(
      { ok: false, reason: result.reason, message: result.message, checkpoints: [] },
      { status: 200 },
    );
  }
  return NextResponse.json({
    ok: true,
    comfyui_url: result.comfyui_url,
    checkpoints: result.checkpoints,
  });
}
