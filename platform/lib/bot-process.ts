import { spawn } from "node:child_process";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";

import { readEnvValues } from "./env-read";
import {
  BOT_LOG,
  ENV_FILE,
  LOGS_DIR,
  META_FILE,
  PID_FILE,
  REPO_ROOT,
  RUN_DIR,
} from "./paths";

export type BotStatus =
  | { state: "running"; pid: number; startedAt: string; uptimeSec: number }
  | { state: "stopped" }
  | { state: "unknown"; reason: string };

type Meta = {
  startedAt: string;
  command: string;
};

let _chain: Promise<unknown> = Promise.resolve();

function withLock<T>(fn: () => Promise<T>): Promise<T> {
  const next = _chain.then(fn, fn);
  _chain = next.catch(() => undefined);
  return next;
}

async function ensureDirs() {
  await fsp.mkdir(RUN_DIR, { recursive: true });
  await fsp.mkdir(LOGS_DIR, { recursive: true });
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code === "EPERM") return true;
    return false;
  }
}

async function readPid(): Promise<number | null> {
  try {
    const raw = await fsp.readFile(PID_FILE, "utf8");
    const pid = parseInt(raw.trim(), 10);
    return Number.isFinite(pid) && pid > 0 ? pid : null;
  } catch {
    return null;
  }
}

async function readMeta(): Promise<Meta | null> {
  try {
    const raw = await fsp.readFile(META_FILE, "utf8");
    return JSON.parse(raw) as Meta;
  } catch {
    return null;
  }
}

async function clearPidFiles() {
  await Promise.allSettled([
    fsp.unlink(PID_FILE),
    fsp.unlink(META_FILE),
  ]);
}

function readPythonBin(): string {
  // Read .env at status-check time so changes apply without restarting Next.
  try {
    const raw = fs.readFileSync(ENV_FILE, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq <= 0) continue;
      const key = trimmed.slice(0, eq).trim();
      if (key !== "PYTHON_BIN") continue;
      let val = trimmed.slice(eq + 1).trim();
      if (
        (val.startsWith('"') && val.endsWith('"')) ||
        (val.startsWith("'") && val.endsWith("'"))
      ) {
        val = val.slice(1, -1);
      }
      if (val) return val;
    }
  } catch {
    // .env missing — fall through to default
  }
  return "python3";
}

export async function getStatus(): Promise<BotStatus> {
  return withLock(async () => {
    const pid = await readPid();
    if (pid === null) return { state: "stopped" };
    if (!isAlive(pid)) {
      await clearPidFiles();
      return { state: "stopped" };
    }
    const meta = await readMeta();
    if (!meta) {
      return {
        state: "unknown",
        reason: "PID file present but meta missing",
      };
    }
    const startedAtMs = Date.parse(meta.startedAt);
    const uptimeSec = Math.max(
      0,
      Math.floor((Date.now() - startedAtMs) / 1000),
    );
    return {
      state: "running",
      pid,
      startedAt: meta.startedAt,
      uptimeSec,
    };
  });
}

export async function start(): Promise<{ pid: number }> {
  return withLock(async () => {
    // Pre-flight: refuse to start when the main bot is unconfigured. The
    // Python entry-point also enforces this, but failing here gives a fast,
    // clean 422 on the dashboard instead of a spawn-then-exit cycle.
    const env = await readEnvValues(["MAIN_BOT_TOKEN", "MAIN_BOT_USERNAME"]);
    const missing: string[] = [];
    if (!env.MAIN_BOT_TOKEN.trim()) missing.push("MAIN_BOT_TOKEN");
    if (!env.MAIN_BOT_USERNAME.trim()) missing.push("MAIN_BOT_USERNAME");
    if (missing.length > 0) {
      const err = new Error(
        `Main bot is not configured — missing ${missing.join(" + ")} in .env. Set the values in /env (Bot tokens tab) and try again.`,
      );
      (err as NodeJS.ErrnoException).code = "MAIN_BOT_NOT_CONFIGURED";
      throw err;
    }

    const existing = await readPid();
    if (existing !== null && isAlive(existing)) {
      const err = new Error("bot is already running");
      (err as NodeJS.ErrnoException).code = "ALREADY_RUNNING";
      throw err;
    }
    if (existing !== null) {
      // Stale PID — clean up before starting.
      await clearPidFiles();
    }

    await ensureDirs();
    const pythonBin = readPythonBin();
    const args = ["-m", "src.bot"];

    const logFd = fs.openSync(BOT_LOG, "a");
    try {
      const child = spawn(pythonBin, args, {
        cwd: REPO_ROOT,
        detached: true,
        stdio: ["ignore", logFd, logFd],
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
        },
      });

      if (!child.pid) {
        throw new Error("spawn returned no pid");
      }

      const pid = child.pid;
      child.unref();

      // Give the process a brief moment to die immediately (e.g. ImportError).
      await new Promise((resolve) => setTimeout(resolve, 250));
      if (!isAlive(pid)) {
        throw new Error(
          `bot died immediately after start — check ${path.relative(REPO_ROOT, BOT_LOG)} (using ${pythonBin})`,
        );
      }

      const meta: Meta = {
        startedAt: new Date().toISOString(),
        command: `${pythonBin} ${args.join(" ")}`,
      };
      await fsp.writeFile(PID_FILE, String(pid), "utf8");
      await fsp.writeFile(META_FILE, JSON.stringify(meta, null, 2), "utf8");
      return { pid };
    } finally {
      try {
        fs.closeSync(logFd);
      } catch {
        // already inherited by child; safe to ignore
      }
    }
  });
}

export async function stop(): Promise<void> {
  return withLock(async () => {
    const pid = await readPid();
    if (pid === null || !isAlive(pid)) {
      await clearPidFiles();
      const err = new Error("bot is not running");
      (err as NodeJS.ErrnoException).code = "NOT_RUNNING";
      throw err;
    }

    try {
      process.kill(pid, "SIGTERM");
    } catch {
      // already dead — nothing to do
    }

    const deadline = Date.now() + 5000;
    while (Date.now() < deadline) {
      if (!isAlive(pid)) break;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    if (isAlive(pid)) {
      try {
        process.kill(pid, "SIGKILL");
      } catch {
        // race with natural exit — fine
      }
      // Brief wait for OS to reap.
      const killDeadline = Date.now() + 2000;
      while (Date.now() < killDeadline && isAlive(pid)) {
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
    }

    await clearPidFiles();
  });
}

export async function restart(): Promise<{ pid: number }> {
  // restart = stop (best-effort) + start. Both are themselves locked.
  try {
    await stop();
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code !== "NOT_RUNNING") throw err;
  }
  return start();
}
