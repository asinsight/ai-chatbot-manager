import path from "node:path";

export const REPO_ROOT = path.resolve(process.cwd(), "..");

export const RUN_DIR = path.join(REPO_ROOT, "run");
export const PID_FILE = path.join(RUN_DIR, "bot.pid");
export const META_FILE = path.join(RUN_DIR, "bot.meta.json");

export const LOGS_DIR = path.join(REPO_ROOT, "logs");
export const BOT_LOG = path.join(LOGS_DIR, "bot.log");

export const ENV_FILE = path.join(REPO_ROOT, ".env");
export const ENV_EXAMPLE_FILE = path.join(REPO_ROOT, ".env.example");

export const PLATFORM_DATA_DIR = path.join(REPO_ROOT, "platform", "data");
export const SQLITE_FILE = path.join(PLATFORM_DATA_DIR, "platform.sqlite");
