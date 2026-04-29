"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Play, RotateCw, Square } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type BotStatus =
  | { state: "running"; pid: number; startedAt: string; uptimeSec: number }
  | { state: "stopped" }
  | { state: "unknown"; reason: string };

type ApiError = { error: string; code?: string };

const POLL_MS = 5000;

function formatUptime(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatStarted(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export function BotStatusCard() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"start" | "stop" | "restart" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/bot/status", { cache: "no-store" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as ApiError;
        throw new Error(body.error ?? `status ${res.status}`);
      }
      const data = (await res.json()) as BotStatus;
      if (mountedRef.current) {
        setStatus(data);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchStatus();
    const id = setInterval(fetchStatus, POLL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [fetchStatus]);

  const callAction = useCallback(
    async (action: "start" | "stop" | "restart") => {
      setBusy(action);
      setActionError(null);
      try {
        const res = await fetch(`/api/bot/${action}`, { method: "POST" });
        const body = (await res.json().catch(() => ({}))) as
          | ApiError
          | Record<string, unknown>;
        if (!res.ok) {
          const msg =
            (body as ApiError).error ?? `${action} failed (${res.status})`;
          throw new Error(msg);
        }
        await fetchStatus();
      } catch (err) {
        setActionError((err as Error).message);
      } finally {
        setBusy(null);
      }
    },
    [fetchStatus],
  );

  const state = status?.state ?? "loading";
  const isRunning = state === "running";
  const isStopped = state === "stopped";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Bot</CardTitle>
          <StatusBadge state={state} />
        </div>
        <CardDescription>
          Telegram bot lifecycle (single instance).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-[120px_1fr] gap-y-1 text-sm">
          <dt className="text-muted-foreground">PID</dt>
          <dd className="font-mono">
            {isRunning ? (status as { pid: number }).pid : "—"}
          </dd>
          <dt className="text-muted-foreground">Uptime</dt>
          <dd className="font-mono">
            {isRunning
              ? formatUptime((status as { uptimeSec: number }).uptimeSec)
              : "—"}
          </dd>
          <dt className="text-muted-foreground">Started</dt>
          <dd className="font-mono">
            {isRunning
              ? formatStarted((status as { startedAt: string }).startedAt)
              : "—"}
          </dd>
          {state === "unknown" && (
            <>
              <dt className="text-muted-foreground">Reason</dt>
              <dd className="text-amber-600">
                {(status as { reason: string }).reason}
              </dd>
            </>
          )}
        </dl>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="default"
            disabled={busy !== null || isRunning}
            onClick={() => callAction("start")}
          >
            {busy === "start" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Play />
            )}
            Start
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={busy !== null || isStopped}
            onClick={() => callAction("stop")}
          >
            {busy === "stop" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Square />
            )}
            Stop
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null || isStopped}
            onClick={() => callAction("restart")}
          >
            {busy === "restart" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <RotateCw />
            )}
            Restart
          </Button>
        </div>

        {(error || actionError) && (
          <p className="text-sm text-destructive">
            {actionError ?? error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function StatusBadge({ state }: { state: string }) {
  if (state === "running") return <Badge variant="success">● Running</Badge>;
  if (state === "stopped") return <Badge variant="secondary">● Stopped</Badge>;
  if (state === "unknown") return <Badge variant="warning">● Unknown</Badge>;
  return <Badge variant="outline">…</Badge>;
}
