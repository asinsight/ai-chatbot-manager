import fsp from "node:fs/promises";
import path from "node:path";

import { ENV_FILE, REPO_ROOT } from "./paths";

export const BACKUP_DIR = path.join(REPO_ROOT, "platform", "data", "backups");

function timestamp(d: Date = new Date()): string {
  // KST = UTC+9 — match server local presentation
  const offsetMs = 9 * 60 * 60 * 1000;
  const kst = new Date(d.getTime() + offsetMs);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    kst.getUTCFullYear().toString() +
    pad(kst.getUTCMonth() + 1) +
    pad(kst.getUTCDate()) +
    "-" +
    pad(kst.getUTCHours()) +
    pad(kst.getUTCMinutes()) +
    pad(kst.getUTCSeconds())
  );
}

/**
 * Copy the current root .env to platform/data/backups/.env.<KST timestamp>.bak
 * Returns the absolute backup path.
 */
export async function backupEnv(): Promise<string> {
  await fsp.mkdir(BACKUP_DIR, { recursive: true });
  const ts = timestamp();
  const target = path.join(BACKUP_DIR, `.env.${ts}.bak`);
  const tmp = `${target}.partial`;
  await fsp.copyFile(ENV_FILE, tmp);
  await fsp.rename(tmp, target);
  return target;
}
