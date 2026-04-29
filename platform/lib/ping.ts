import {
  CONNECTIONS,
  type ConnectionId,
  getConnectionDef,
} from "./connections";
import { readEnvValues } from "./env-read";

const TIMEOUT_MS = 10_000;

export type PingResult = {
  ok: boolean;
  status_code?: number;
  duration_ms: number;
  message: string;
};

function trimTrailingSlash(u: string): string {
  return u.replace(/\/+$/, "");
}

async function timedFetch(
  url: string,
  init: RequestInit,
): Promise<{ res?: Response; ms: number; err?: Error }> {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const start = Date.now();
  try {
    const res = await fetch(url, { ...init, signal: controller.signal });
    return { res, ms: Date.now() - start };
  } catch (err) {
    return { err: err as Error, ms: Date.now() - start };
  } finally {
    clearTimeout(t);
  }
}

async function pingComfyUI(url: string): Promise<PingResult> {
  if (!url) return { ok: false, duration_ms: 0, message: "URL required" };
  const target = `${trimTrailingSlash(url)}/system_stats`;
  const { res, ms, err } = await timedFetch(target, { method: "GET" });
  if (err)
    return {
      ok: false,
      duration_ms: ms,
      message: err.name === "AbortError" ? "timeout (10s)" : err.message,
    };
  if (!res!.ok) {
    return {
      ok: false,
      status_code: res!.status,
      duration_ms: ms,
      message: `HTTP ${res!.status}`,
    };
  }
  try {
    await res!.json();
  } catch {
    return {
      ok: false,
      status_code: res!.status,
      duration_ms: ms,
      message: "response is not JSON",
    };
  }
  return {
    ok: true,
    status_code: res!.status,
    duration_ms: ms,
    message: "OK",
  };
}

async function pingOpenWebUI(
  url: string,
  token: string,
): Promise<PingResult> {
  if (!url) return { ok: false, duration_ms: 0, message: "URL required" };
  const target = `${trimTrailingSlash(url)}/v1/models`;
  const headers: Record<string, string> = {};
  if (token) headers["authorization"] = `Bearer ${token}`;
  const { res, ms, err } = await timedFetch(target, {
    method: "GET",
    headers,
  });
  if (err)
    return {
      ok: false,
      duration_ms: ms,
      message: err.name === "AbortError" ? "timeout (10s)" : err.message,
    };
  if (!res!.ok) {
    return {
      ok: false,
      status_code: res!.status,
      duration_ms: ms,
      message: `HTTP ${res!.status}`,
    };
  }
  return {
    ok: true,
    status_code: res!.status,
    duration_ms: ms,
    message: "OK",
  };
}

async function pingGrok(baseUrl: string, token: string): Promise<PingResult> {
  if (!token) return { ok: false, duration_ms: 0, message: "token required" };
  const target = `${trimTrailingSlash(baseUrl)}/models`;
  const { res, ms, err } = await timedFetch(target, {
    method: "GET",
    headers: { authorization: `Bearer ${token}` },
  });
  if (err)
    return {
      ok: false,
      duration_ms: ms,
      message: err.name === "AbortError" ? "timeout (10s)" : err.message,
    };
  if (res!.status === 401) {
    return {
      ok: false,
      status_code: 401,
      duration_ms: ms,
      message: "credentials rejected (401)",
    };
  }
  if (!res!.ok) {
    return {
      ok: false,
      status_code: res!.status,
      duration_ms: ms,
      message: `HTTP ${res!.status}`,
    };
  }
  return {
    ok: true,
    status_code: res!.status,
    duration_ms: ms,
    message: "OK",
  };
}

async function pingPromptGuard(url: string): Promise<PingResult> {
  if (!url) return { ok: false, duration_ms: 0, message: "URL required" };
  const target = `${trimTrailingSlash(url)}/check`;
  const { res, ms, err } = await timedFetch(target, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text: "hello", threshold: 0.8 }),
  });
  if (err)
    return {
      ok: false,
      duration_ms: ms,
      message: err.name === "AbortError" ? "timeout (10s)" : err.message,
    };
  if (!res!.ok) {
    return {
      ok: false,
      status_code: res!.status,
      duration_ms: ms,
      message: `HTTP ${res!.status}`,
    };
  }
  return {
    ok: true,
    status_code: res!.status,
    duration_ms: ms,
    message: "OK",
  };
}

export async function pingByEndpointId(
  id: ConnectionId,
): Promise<PingResult> {
  const def = getConnectionDef(id);
  if (!def)
    return {
      ok: false,
      duration_ms: 0,
      message: `unknown endpoint: ${id}`,
    };
  const keys = [def.url_var];
  if (def.token_var) keys.push(def.token_var);
  const env = await readEnvValues(keys);
  const url = env[def.url_var] || def.default_url || "";
  const token = def.token_var ? env[def.token_var] : "";

  switch (id) {
    case "comfyui":
      return pingComfyUI(url);
    case "openwebui":
      return pingOpenWebUI(url, token);
    case "grok":
      return pingGrok(url, token);
    case "prompt_guard":
      return pingPromptGuard(url);
  }
}

export async function pingAll(): Promise<Record<ConnectionId, PingResult>> {
  const entries = await Promise.all(
    CONNECTIONS.map(async (c) => {
      const result = await pingByEndpointId(c.id);
      return [c.id, result] as const;
    }),
  );
  return Object.fromEntries(entries) as Record<ConnectionId, PingResult>;
}
