"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const POLL_MS = 5000;
const TAIL = 200;

type ApiResponse = { lines?: string[]; note?: string; error?: string };

export function LogTail() {
  const [lines, setLines] = useState<string[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const preRef = useRef<HTMLPreElement | null>(null);
  const mountedRef = useRef(true);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`/api/bot/logs?tail=${TAIL}`, {
        cache: "no-store",
      });
      const body = (await res.json().catch(() => ({}))) as ApiResponse;
      if (!res.ok) throw new Error(body.error ?? `status ${res.status}`);
      if (mountedRef.current) {
        setLines(body.lines ?? []);
        setNote(body.note ?? null);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchLogs();
    const id = setInterval(fetchLogs, POLL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [fetchLogs]);

  useEffect(() => {
    if (!autoScroll) return;
    const el = preRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines, autoScroll]);

  const onScroll = useCallback(() => {
    const el = preRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 20;
    setAutoScroll(atBottom);
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent logs</CardTitle>
        <CardDescription>
          {`Last ${TAIL} lines of logs/bot.log · polled every ${POLL_MS / 1000}s${
            autoScroll ? "" : " · auto-scroll paused"
          }`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="mb-2 text-sm text-destructive">Log fetch failed: {error}</p>
        )}
        {note && !error && (
          <p className="mb-2 text-sm text-muted-foreground">{note}</p>
        )}
        <pre
          ref={preRef}
          onScroll={onScroll}
          className="h-[420px] overflow-auto rounded-md border bg-muted/40 p-3 text-xs leading-relaxed font-mono whitespace-pre-wrap"
        >
          {lines.length === 0 ? (
            <span className="text-muted-foreground">No logs yet</span>
          ) : (
            lines.join("\n")
          )}
        </pre>
      </CardContent>
    </Card>
  );
}
