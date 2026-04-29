"use client";

import { useCallback, useState } from "react";
import { Eye, EyeOff, Loader2, Save, Zap } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type ConnectionPayload = {
  id: string;
  label: string;
  url_var: string;
  token_var: string | null;
  url: string;
  url_default: string | null;
  token_blank_allowed: boolean;
  token_present: boolean;
  token_masked: string | null;
  last_ping: {
    ok: boolean;
    status_code: number | null;
    duration_ms: number | null;
    message: string | null;
    ts: number;
  } | null;
};

type PingResponse = {
  id: string;
  ok: boolean;
  status_code?: number;
  duration_ms: number;
  message: string;
};

function formatTs(ts: number): string {
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return "—";
  }
}

export function ConnectionCard({
  conn,
  onChanged,
}: {
  conn: ConnectionPayload;
  onChanged: () => Promise<void> | void;
}) {
  const [url, setUrl] = useState(conn.url);
  const [token, setToken] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [transient, setTransient] = useState<PingResponse | null>(null);

  const lastPing = transient ?? conn.last_ping;
  const isUrlDirty = url !== conn.url;
  const isTokenDirty = token.length > 0;
  const dirty = isUrlDirty || isTokenDirty;

  const save = useCallback(async (): Promise<boolean> => {
    if (!dirty) return true;
    setSaving(true);
    try {
      const body: Record<string, string> = {};
      if (isUrlDirty) body.url = url;
      if (isTokenDirty) body.token = token;
      const res = await fetch(`/api/connections/${conn.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        backup_path?: string;
        error?: string;
      };
      if (!res.ok) throw new Error(json.error ?? `status ${res.status}`);
      toast.success(`${conn.label} 저장됨`, {
        description: `백업: ${json.backup_path?.split("/").pop()}`,
      });
      setToken(""); // clear secret input after save
      await onChanged();
      return true;
    } catch (err) {
      toast.error(`${conn.label} 저장 실패`, {
        description: (err as Error).message,
      });
      return false;
    } finally {
      setSaving(false);
    }
  }, [conn.id, conn.label, dirty, isTokenDirty, isUrlDirty, onChanged, token, url]);

  const ping = useCallback(async () => {
    setPinging(true);
    try {
      const res = await fetch(`/api/connections/${conn.id}/ping`, {
        method: "POST",
      });
      const json = (await res.json()) as PingResponse;
      setTransient(json);
      if (json.ok) {
        toast.success(`${conn.label} ping OK`, {
          description: `${json.duration_ms} ms`,
        });
      } else {
        toast.error(`${conn.label} ping 실패`, {
          description: json.message,
        });
      }
      await onChanged();
    } catch (err) {
      toast.error(`${conn.label} ping 실패`, {
        description: (err as Error).message,
      });
    } finally {
      setPinging(false);
    }
  }, [conn.id, conn.label, onChanged]);

  const saveAndPing = useCallback(async () => {
    const ok = await save();
    if (ok) await ping();
  }, [ping, save]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{conn.label}</CardTitle>
          <PingBadge ping={lastPing} />
        </div>
        <CardDescription className="font-mono text-xs">
          {conn.url_var}
          {conn.token_var ? ` · ${conn.token_var}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor={`${conn.id}-url`} className="text-xs">
            URL
          </Label>
          <Input
            id={`${conn.id}-url`}
            value={url}
            placeholder={conn.url_default ?? "http://..."}
            onChange={(e) => setUrl(e.target.value)}
            className="font-mono text-xs"
          />
        </div>

        {conn.token_var && (
          <div className="space-y-1.5">
            <Label htmlFor={`${conn.id}-token`} className="text-xs">
              Token{" "}
              {!conn.token_blank_allowed && (
                <span className="text-destructive">*</span>
              )}
            </Label>
            <div className="flex items-center gap-2">
              <Input
                id={`${conn.id}-token`}
                type={revealed ? "text" : "password"}
                value={token}
                placeholder={
                  conn.token_present ? (conn.token_masked ?? "(set)") : "(blank)"
                }
                onChange={(e) => setToken(e.target.value)}
                className="font-mono text-xs"
              />
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => setRevealed((r) => !r)}
                aria-label={revealed ? "Hide token" : "Reveal token"}
              >
                {revealed ? <EyeOff /> : <Eye />}
              </Button>
            </div>
            {!isTokenDirty && conn.token_present && (
              <p className="text-[11px] text-muted-foreground">
                현재 저장된 토큰. 새 값을 입력해야 갱신됩니다.
              </p>
            )}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="default"
            onClick={ping}
            disabled={pinging || saving}
          >
            {pinging ? <Loader2 className="animate-spin" /> : <Zap />}
            Ping
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={save}
            disabled={!dirty || saving}
          >
            {saving ? <Loader2 className="animate-spin" /> : <Save />}
            Save
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={saveAndPing}
            disabled={!dirty || saving || pinging}
          >
            Save & Ping
          </Button>
        </div>

        {lastPing && (
          <p className="text-[11px] text-muted-foreground">
            {lastPing.duration_ms ?? "—"} ms
            {lastPing.status_code != null && ` · HTTP ${lastPing.status_code}`}
            {(lastPing as { ts?: number }).ts &&
              ` · ${formatTs((lastPing as { ts: number }).ts)}`}
            {lastPing.message && ` · ${lastPing.message}`}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function PingBadge({ ping }: { ping: ConnectionPayload["last_ping"] | PingResponse | null }) {
  if (!ping) return <Badge variant="outline">⚪ Untested</Badge>;
  if (ping.ok) return <Badge variant="success">🟢 OK</Badge>;
  const code = "status_code" in ping ? ping.status_code : null;
  return <Badge variant="destructive">🔴 {code ?? "Fail"}</Badge>;
}
