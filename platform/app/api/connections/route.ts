import { NextResponse } from "next/server";

import { CONNECTIONS } from "@/lib/connections";
import { getLastPingsAll } from "@/lib/db";
import { readEnvValues } from "@/lib/env-read";
import { isSecret, maskValue } from "@/lib/secrets";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const keys = CONNECTIONS.flatMap((c) =>
      c.token_var ? [c.url_var, c.token_var] : [c.url_var],
    );
    const env = await readEnvValues(keys);
    const lastPings = getLastPingsAll();

    const connections = CONNECTIONS.map((c) => {
      const url = env[c.url_var] ?? "";
      const token = c.token_var ? env[c.token_var] ?? "" : "";
      const last = lastPings[c.id];
      return {
        id: c.id,
        label: c.label,
        url_var: c.url_var,
        token_var: c.token_var,
        url,
        url_default: c.default_url,
        token_blank_allowed: c.token_blank_allowed,
        token_present: token.length > 0,
        token_masked:
          c.token_var && isSecret(c.token_var) && token
            ? maskValue(token)
            : null,
        last_ping: last
          ? {
              ok: last.ok === 1,
              status_code: last.status_code,
              duration_ms: last.duration_ms,
              message: last.message,
              ts: last.ts,
            }
          : null,
      };
    });
    return NextResponse.json({ connections });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "CONNECTIONS_LIST_FAILED" },
      { status: 500 },
    );
  }
}
