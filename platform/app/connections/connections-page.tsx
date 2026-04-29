"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Zap } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { ConnectionCard, type ConnectionPayload } from "./connection-card";

type ListResponse = { connections: ConnectionPayload[] };

export function ConnectionsPage() {
  const [data, setData] = useState<ConnectionPayload[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pingingAll, setPingingAll] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/connections", { cache: "no-store" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `status ${res.status}`);
      }
      const json = (await res.json()) as ListResponse;
      setData(json.connections);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const pingAll = useCallback(async () => {
    setPingingAll(true);
    try {
      const res = await fetch("/api/connections/ping-all", { method: "POST" });
      const body = (await res.json()) as {
        results: Record<string, { ok: boolean; message: string }>;
      };
      const okCount = Object.values(body.results).filter((r) => r.ok).length;
      const total = Object.keys(body.results).length;
      if (okCount === total) toast.success(`${okCount}/${total} 모두 OK`);
      else toast.warning(`${okCount}/${total} OK · ${total - okCount} 실패`);
      await refresh();
    } catch (err) {
      toast.error("전체 Ping 실패", { description: (err as Error).message });
    } finally {
      setPingingAll(false);
    }
  }, [refresh]);

  if (error) {
    return <div className="text-sm text-destructive">로드 실패: {error}</div>;
  }
  if (!data) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> 로드 중…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {data.length}개 endpoint · 마지막 ping 결과는 `platform.sqlite` 에 누적
          기록됨.
        </p>
        <Button size="sm" onClick={pingAll} disabled={pingingAll}>
          {pingingAll ? <Loader2 className="animate-spin" /> : <Zap />}
          전체 Ping
        </Button>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {data.map((c) => (
          <ConnectionCard key={c.id} conn={c} onChanged={refresh} />
        ))}
      </div>
    </div>
  );
}
