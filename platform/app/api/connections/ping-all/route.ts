import { NextResponse } from "next/server";

import { CONNECTIONS } from "@/lib/connections";
import { recordPing } from "@/lib/db";
import { pingAll } from "@/lib/ping";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const results = await pingAll();
  for (const c of CONNECTIONS) {
    const r = results[c.id];
    if (!r) continue;
    recordPing({
      endpoint_id: c.id,
      ok: r.ok,
      status_code: r.status_code,
      duration_ms: r.duration_ms,
      message: r.message,
    });
  }
  return NextResponse.json({ results });
}
