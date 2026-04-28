import { NextRequest, NextResponse } from "next/server";
import fs from "node:fs";
import fsp from "node:fs/promises";

import { BOT_LOG } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_TAIL = 1000;
const DEFAULT_TAIL = 200;
// 1 MB read window — enough for ~10k lines in typical logs.
const READ_WINDOW = 1 * 1024 * 1024;

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const tailParam = url.searchParams.get("tail");
  const requested = tailParam ? parseInt(tailParam, 10) : DEFAULT_TAIL;
  const tail = Math.max(
    1,
    Math.min(MAX_TAIL, Number.isFinite(requested) ? requested : DEFAULT_TAIL),
  );

  try {
    let stat;
    try {
      stat = await fsp.stat(BOT_LOG);
    } catch {
      return NextResponse.json({ lines: [], note: "log file not yet created" });
    }
    if (stat.size === 0) {
      return NextResponse.json({ lines: [] });
    }

    const start = Math.max(0, stat.size - READ_WINDOW);
    const length = stat.size - start;
    const buf = Buffer.alloc(length);
    const fh = await fsp.open(BOT_LOG, "r");
    try {
      await fh.read(buf, 0, length, start);
    } finally {
      await fh.close();
    }
    const text = buf.toString("utf8");
    const all = text.split("\n");
    // If we started mid-line, drop the first (likely partial) line.
    if (start > 0 && all.length > 0) all.shift();
    // Drop trailing empty token from final newline.
    if (all.length > 0 && all[all.length - 1] === "") all.pop();
    const lines = all.slice(-tail);
    return NextResponse.json({ lines });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "LOGS_FAILED" },
      { status: 500 },
    );
  }
}
