import { readEnvValues } from "./env-read";

export type FetchCheckpointsResult =
  | { ok: true; checkpoints: string[]; comfyui_url: string }
  | { ok: false; reason: "no_url" | "unreachable" | "shape_mismatch"; message: string };

const FETCH_TIMEOUT_MS = 8_000;

/**
 * Fetch the list of available checkpoints from a running ComfyUI server by
 * inspecting its `/object_info` response. Returns a structured result so
 * callers can fall back gracefully when the server is unreachable.
 */
export async function fetchCheckpoints(): Promise<FetchCheckpointsResult> {
  const env = await readEnvValues(["COMFYUI_URL"]);
  const url = env.COMFYUI_URL.trim().replace(/\/+$/, "");
  if (!url) {
    return {
      ok: false,
      reason: "no_url",
      message: "COMFYUI_URL is not set in .env",
    };
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(`${url}/object_info/CheckpointLoaderSimple`, {
      signal: ctrl.signal,
      cache: "no-store",
    });
    if (!resp.ok) {
      return {
        ok: false,
        reason: "unreachable",
        message: `ComfyUI returned HTTP ${resp.status}`,
      };
    }
    const body = (await resp.json()) as Record<string, unknown>;
    const node = body.CheckpointLoaderSimple as
      | { input?: { required?: { ckpt_name?: unknown } } }
      | undefined;
    const tuple = node?.input?.required?.ckpt_name;
    if (
      !Array.isArray(tuple) ||
      tuple.length === 0 ||
      !Array.isArray(tuple[0])
    ) {
      return {
        ok: false,
        reason: "shape_mismatch",
        message: "ComfyUI /object_info did not contain a checkpoint list",
      };
    }
    const list = (tuple[0] as unknown[]).filter((s): s is string => typeof s === "string");
    list.sort();
    return { ok: true, checkpoints: list, comfyui_url: url };
  } catch (err) {
    return {
      ok: false,
      reason: "unreachable",
      message:
        (err as Error).name === "AbortError"
          ? `timed out after ${FETCH_TIMEOUT_MS}ms`
          : (err as Error).message,
    };
  } finally {
    clearTimeout(timer);
  }
}
