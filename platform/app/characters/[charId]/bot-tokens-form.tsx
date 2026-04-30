"use client";

import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, Loader2, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type FieldState = { value: string; present: boolean; masked: string | null };

type Resp = {
  charId: string;
  fields: {
    token: FieldState;
    username: FieldState;
  };
  keys: Record<string, string>;
};

type FieldKey = "token" | "username";

const FIELD_DEFS: { key: FieldKey; label: string; secret: boolean; placeholder: string }[] = [
  { key: "token", label: "Bot token", secret: true, placeholder: "12345:ABC… (from @BotFather)" },
  { key: "username", label: "Bot username", secret: false, placeholder: "MyCharBot" },
];

export function BotTokensForm({ charId }: { charId: string }) {
  const [data, setData] = useState<Resp | null>(null);
  const [edits, setEdits] = useState<Partial<Record<FieldKey, string>>>({});
  const [revealed, setRevealed] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/characters/${charId}/env`, {
        cache: "no-store",
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `status ${res.status}`);
      }
      const json = (await res.json()) as Resp;
      setData(json);
      setEdits({});
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [charId]);

  useEffect(() => {
    void load();
  }, [load]);

  const dirtyKeys = Object.keys(edits) as FieldKey[];
  const dirty = dirtyKeys.length > 0;

  const save = useCallback(async () => {
    if (!dirty) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/characters/${charId}/env`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(edits),
      });
      const body = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        backup_path?: string;
        updated_keys?: string[];
        error?: string;
      };
      if (!res.ok) throw new Error(body.error ?? `status ${res.status}`);
      const n = body.updated_keys?.length ?? 0;
      toast.success(`${n} env line(s) saved · restart bot to load`, {
        description: `backup: ${body.backup_path?.split("/").pop()}`,
        duration: 8000,
      });
      await load();
    } catch (err) {
      toast.error("Save failed", { description: (err as Error).message });
    } finally {
      setSaving(false);
    }
  }, [charId, dirty, edits, load]);

  if (error) {
    return <div className="text-sm text-destructive">Load failed: {error}</div>;
  }
  if (!data) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-md border border-border/60 bg-muted/30 p-3 text-xs text-muted-foreground">
        Telegram bot token + username for this character. Get the token + username from{" "}
        <a
          className="underline"
          href="https://t.me/BotFather"
          target="_blank"
          rel="noreferrer"
        >
          @BotFather
        </a>
        . Bot must be restarted for new tokens to take effect.
      </div>

      {FIELD_DEFS.map((f) => {
        const stored = data.fields[f.key];
        const draft = edits[f.key];
        const editing = draft !== undefined;
        const show = editing
          ? draft
          : f.secret && !revealed[f.key] && stored.present
            ? (stored.masked ?? "")
            : stored.value;
        const placeholderText = !stored.present ? f.placeholder : undefined;
        return (
          <div key={f.key} className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Label className="font-mono text-xs">{f.label}</Label>
              <span className="font-mono text-[10px] text-muted-foreground">
                {data.keys[f.key]}
              </span>
              {f.secret && (
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                  secret
                </span>
              )}
              {!stored.present && !editing && (
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                  empty
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Input
                type="text"
                value={show}
                placeholder={placeholderText}
                readOnly={!editing && f.secret && stored.present && !revealed[f.key]}
                onChange={(e) =>
                  setEdits((prev) => ({ ...prev, [f.key]: e.target.value }))
                }
                onFocus={() => {
                  if (!editing) {
                    setEdits((prev) => ({
                      ...prev,
                      [f.key]: stored.value,
                    }));
                  }
                }}
                className="font-mono text-xs"
              />
              {f.secret && stored.present && !editing && (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={() =>
                    setRevealed((p) => ({ ...p, [f.key]: !p[f.key] }))
                  }
                  aria-label={revealed[f.key] ? "Hide" : "Reveal"}
                >
                  {revealed[f.key] ? <EyeOff /> : <Eye />}
                </Button>
              )}
            </div>
          </div>
        );
      })}

      <div className="flex items-center justify-between pt-2">
        <p className="text-xs text-muted-foreground">
          {dirty ? `${dirtyKeys.length} field(s) modified` : "No changes"}
        </p>
        <Button onClick={save} disabled={!dirty || saving}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />}
          Save bot tokens
        </Button>
      </div>
    </div>
  );
}
