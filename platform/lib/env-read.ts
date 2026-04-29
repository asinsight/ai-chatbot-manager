import fsp from "node:fs/promises";

import { parseEnv } from "./env-parser";
import { ENV_FILE } from "./paths";

/**
 * Read the current values of the given keys from the root `.env` file.
 * Missing keys yield empty string.
 */
export async function readEnvValues(
  keys: string[],
): Promise<Record<string, string>> {
  let text = "";
  try {
    text = await fsp.readFile(ENV_FILE, "utf8");
  } catch {
    // .env missing → all empty
  }
  const lines = parseEnv(text);
  const out: Record<string, string> = {};
  for (const k of keys) out[k] = "";
  for (const line of lines) {
    if (line.kind === "var" && keys.includes(line.key)) {
      out[line.key] = line.value;
    }
  }
  return out;
}
