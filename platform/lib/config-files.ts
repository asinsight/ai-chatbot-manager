import fsp from "node:fs/promises";
import path from "node:path";

import { BACKUP_DIR } from "./backup";
import {
  CONFIG_FILE_BASENAMES,
  type ConfigFileKey,
} from "./config-files-meta";
import { REPO_ROOT } from "./paths";

export {
  CONFIG_FILE_BASENAMES,
  CONFIG_FILE_KEYS,
  CONFIG_FILE_META,
  CONFIG_FILE_DISPLAY_PATHS,
  type ConfigFileKey,
} from "./config-files-meta";

export const CONFIG_FILE_PATHS: Record<ConfigFileKey, string> = {
  sfw_scenes: path.join(REPO_ROOT, "config", "sfw_scenes.json"),
  pose_motion_presets: path.join(REPO_ROOT, "config", "pose_motion_presets.json"),
  sfw_denylist: path.join(REPO_ROOT, "config", "sfw_denylist.json"),
  profile_keys: path.join(REPO_ROOT, "config", "profile_keys.json"),
};

function timestamp(d: Date = new Date()): string {
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

export async function readConfigFile(
  key: ConfigFileKey,
): Promise<{ key: ConfigFileKey; content: unknown; mtime: number }> {
  const file = CONFIG_FILE_PATHS[key];
  const [text, stat] = await Promise.all([
    fsp.readFile(file, "utf8"),
    fsp.stat(file),
  ]);
  const content = JSON.parse(text) as unknown;
  return { key, content, mtime: stat.mtimeMs };
}

export async function backupConfigFile(key: ConfigFileKey): Promise<string> {
  await fsp.mkdir(BACKUP_DIR, { recursive: true });
  const target = path.join(
    BACKUP_DIR,
    `${CONFIG_FILE_BASENAMES[key]}.${timestamp()}.bak`,
  );
  const tmp = `${target}.partial`;
  await fsp.copyFile(CONFIG_FILE_PATHS[key], tmp);
  await fsp.rename(tmp, target);
  return target;
}

export async function writeConfigFileAtomic(
  key: ConfigFileKey,
  content: unknown,
): Promise<void> {
  const file = CONFIG_FILE_PATHS[key];
  const serialized = JSON.stringify(content, null, 2) + "\n";
  const tmp = `${file}.partial`;
  await fsp.writeFile(tmp, serialized, "utf8");
  await fsp.rename(tmp, file);
}
