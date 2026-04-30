import fsp from "node:fs/promises";
import path from "node:path";

import { LOGS_DIR } from "./paths";

export type LogFileInfo = {
  name: string;       // "bot.log" or "bot.log.YYYY-MM-DD"
  size_bytes: number;
  mtime_ms: number;
  is_current: boolean;
};

const ALLOWED_RE = /^bot\.log(?:\.\d{4}-\d{2}-\d{2})?$/;

export function isAllowedLogFile(name: string): boolean {
  return ALLOWED_RE.test(name);
}

export async function listLogFiles(): Promise<LogFileInfo[]> {
  let entries: string[];
  try {
    entries = await fsp.readdir(LOGS_DIR);
  } catch {
    return [];
  }
  const out: LogFileInfo[] = [];
  for (const name of entries) {
    if (!isAllowedLogFile(name)) continue;
    try {
      const stat = await fsp.stat(path.join(LOGS_DIR, name));
      out.push({
        name,
        size_bytes: stat.size,
        mtime_ms: stat.mtimeMs,
        is_current: name === "bot.log",
      });
    } catch {
      // file removed between readdir + stat — skip
    }
  }
  // current first, then dated descending (newest first).
  out.sort((a, b) => {
    if (a.is_current && !b.is_current) return -1;
    if (!a.is_current && b.is_current) return 1;
    return b.name.localeCompare(a.name);
  });
  return out;
}

export function logFilePath(name: string): string {
  if (!isAllowedLogFile(name)) {
    throw Object.assign(new Error(`invalid log file name: ${name}`), { code: "INVALID_FILE" });
  }
  return path.join(LOGS_DIR, name);
}
