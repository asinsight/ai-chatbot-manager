import { NextResponse } from "next/server";

import { getConnectionDef, type ConnectionId } from "@/lib/connections";
import { recordPing } from "@/lib/db";
import { pingByEndpointId } from "@/lib/ping";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  _req: Request,
  { params }: { params: { id: string } },
) {
  const def = getConnectionDef(params.id);
  if (!def) {
    return NextResponse.json(
      { error: `unknown connection: ${params.id}`, code: "UNKNOWN_CONNECTION" },
      { status: 404 },
    );
  }
  const result = await pingByEndpointId(def.id as ConnectionId);
  recordPing({
    endpoint_id: def.id,
    ok: result.ok,
    status_code: result.status_code,
    duration_ms: result.duration_ms,
    message: result.message,
  });
  return NextResponse.json({ id: def.id, ...result });
}
