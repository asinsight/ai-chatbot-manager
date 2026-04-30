import { NextRequest, NextResponse } from "next/server";
import fsp from "node:fs/promises";

import { isAllowedLogFile, listLogFiles, logFilePath } from "@/lib/log-files";
import { BOT_LOG } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_TAIL = 5000;
const DEFAULT_TAIL = 200;
// 4 MB read window — covers ~40k typical log lines for the larger /logs page.
const READ_WINDOW = 4 * 1024 * 1024;

export async function GET(req: NextRequest) {
  const url = new URL(req.url);

  // Mode 1: list available log files.
  if (url.searchParams.get("listFiles") === "1") {
    try {
      const files = await listLogFiles();
      return NextResponse.json({ files });
    } catch (err) {
      const e = err as Error;
      return NextResponse.json(
        { error: e.message, code: "LOGS_FAILED" },
        { status: 500 },
      );
    }
  }

  // Mode 2: tail a log file (default bot.log).
  const fileParam = url.searchParams.get("file");
  let target = BOT_LOG;
  if (fileParam) {
    if (!isAllowedLogFile(fileParam)) {
      return NextResponse.json(
        { error: `invalid file name: ${fileParam}`, code: "INVALID_FILE" },
        { status: 422 },
      );
    }
    try {
      target = logFilePath(fileParam);
    } catch (err) {
      const e = err as NodeJS.ErrnoException;
      return NextResponse.json(
        { error: e.message, code: e.code ?? "INVALID_FILE" },
        { status: 422 },
      );
    }
  }

  const tailParam = url.searchParams.get("tail");
  const requested = tailParam ? parseInt(tailParam, 10) : DEFAULT_TAIL;
  const tail = Math.max(
    1,
    Math.min(MAX_TAIL, Number.isFinite(requested) ? requested : DEFAULT_TAIL),
  );

  try {
    let stat;
    try {
      stat = await fsp.stat(target);
    } catch {
      return NextResponse.json({ lines: [], note: "log file not yet created" });
    }
    if (stat.size === 0) {
      return NextResponse.json({ lines: [] });
    }

    const start = Math.max(0, stat.size - READ_WINDOW);
    const length = stat.size - start;
    const buf = Buffer.alloc(length);
    const fh = await fsp.open(target, "r");
    try {
      await fh.read(buf, 0, length, start);
    } finally {
      await fh.close();
    }
    const text = buf.toString("utf8");
    const all = text.split("\n");
    if (start > 0 && all.length > 0) all.shift();
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
