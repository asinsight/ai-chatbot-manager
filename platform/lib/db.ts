import fs from "node:fs";
import Database from "better-sqlite3";

import { PLATFORM_DATA_DIR, SQLITE_FILE } from "./paths";

let _db: Database.Database | null = null;

const SCHEMA_STATEMENTS: string[] = [
  `CREATE TABLE IF NOT EXISTS connection_check (
     id           INTEGER PRIMARY KEY AUTOINCREMENT,
     endpoint_id  TEXT NOT NULL,
     ts           INTEGER NOT NULL,
     ok           INTEGER NOT NULL,
     status_code  INTEGER,
     duration_ms  INTEGER,
     message      TEXT
   )`,
  `CREATE INDEX IF NOT EXISTS idx_connection_check_endpoint_ts
     ON connection_check (endpoint_id, ts DESC)`,
];

function init(): Database.Database {
  fs.mkdirSync(PLATFORM_DATA_DIR, { recursive: true });
  const db = new Database(SQLITE_FILE);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  for (const stmt of SCHEMA_STATEMENTS) {
    db.prepare(stmt).run();
  }
  return db;
}

export function getDb(): Database.Database {
  if (!_db) _db = init();
  return _db;
}

export type PingRow = {
  endpoint_id: string;
  ts: number;
  ok: 0 | 1;
  status_code: number | null;
  duration_ms: number | null;
  message: string | null;
};

export type RecordPingInput = {
  endpoint_id: string;
  ok: boolean;
  status_code?: number;
  duration_ms: number;
  message: string;
};

export function recordPing(input: RecordPingInput): void {
  const db = getDb();
  db.prepare(
    `INSERT INTO connection_check (endpoint_id, ts, ok, status_code, duration_ms, message)
     VALUES (@endpoint_id, @ts, @ok, @status_code, @duration_ms, @message)`,
  ).run({
    endpoint_id: input.endpoint_id,
    ts: Date.now(),
    ok: input.ok ? 1 : 0,
    status_code: input.status_code ?? null,
    duration_ms: input.duration_ms,
    message: input.message,
  });
}

export function getLastPing(endpoint_id: string): PingRow | null {
  const db = getDb();
  const row = db
    .prepare<{ endpoint_id: string }, PingRow>(
      `SELECT endpoint_id, ts, ok, status_code, duration_ms, message
       FROM connection_check
       WHERE endpoint_id = @endpoint_id
       ORDER BY ts DESC
       LIMIT 1`,
    )
    .get({ endpoint_id });
  return row ?? null;
}

export function getLastPingsAll(): Record<string, PingRow> {
  const db = getDb();
  const rows = db
    .prepare<[], PingRow>(
      `SELECT c.endpoint_id, c.ts, c.ok, c.status_code, c.duration_ms, c.message
       FROM connection_check c
       JOIN (
         SELECT endpoint_id, MAX(ts) AS max_ts
         FROM connection_check
         GROUP BY endpoint_id
       ) m ON m.endpoint_id = c.endpoint_id AND m.max_ts = c.ts`,
    )
    .all();
  const out: Record<string, PingRow> = {};
  for (const r of rows) out[r.endpoint_id] = r;
  return out;
}
