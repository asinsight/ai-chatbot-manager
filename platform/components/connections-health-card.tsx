"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Conn = {
  id: string;
  label: string;
  last_ping: { ok: boolean; ts: number } | null;
};

type Resp = { connections: Conn[] };

const POLL_MS = 30_000;

function dot(state: "ok" | "fail" | "untested"): JSX.Element {
  if (state === "ok") return <span className="text-emerald-500">●</span>;
  if (state === "fail") return <span className="text-red-500">●</span>;
  return <span className="text-muted-foreground">○</span>;
}

export function ConnectionsHealthCard() {
  const [data, setData] = useState<Conn[] | null>(null);
  const mountedRef = useRef(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch("/api/connections", { cache: "no-store" });
      if (!res.ok) return;
      const body = (await res.json()) as Resp;
      if (mountedRef.current) setData(body.connections);
    } catch {
      // swallow — dashboard card is best-effort
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void fetchData();
    const id = setInterval(fetchData, POLL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [fetchData]);

  const okCount =
    data?.filter((c) => c.last_ping?.ok).length ?? 0;
  const failCount =
    data?.filter((c) => c.last_ping && !c.last_ping.ok).length ?? 0;
  const total = data?.length ?? 0;
  const summary = data
    ? failCount > 0
      ? `${okCount}/${total} OK · ${failCount} failing`
      : okCount === total
      ? `${total}/${total} OK`
      : `${okCount}/${total} OK · ${total - okCount} untested`
    : "…";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Connections health</CardTitle>
          <Link
            href="/connections"
            className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground"
          >
            Manage <ChevronRight className="h-3 w-3" />
          </Link>
        </div>
        <CardDescription>
          Last ping results · auto-refresh every 30 seconds.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="mb-2 text-sm">{summary}</p>
        <div className="flex flex-wrap gap-3 text-xs">
          {data?.map((c) => {
            const state: "ok" | "fail" | "untested" = !c.last_ping
              ? "untested"
              : c.last_ping.ok
              ? "ok"
              : "fail";
            return (
              <span key={c.id} className="inline-flex items-center gap-1">
                {dot(state)} {c.label}
              </span>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
