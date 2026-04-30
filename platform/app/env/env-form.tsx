"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Eye, EyeOff, Lock, Save, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

type EnvVar = {
  key: string;
  value: string;
  default_value: string | null;
  comment: string | null;
  is_secret: boolean;
  editable: boolean;
  edit_redirect: string | null;
};

type EnvCategory = {
  id: string;
  label: string;
  description: string | null;
  vars: EnvVar[];
};

type EnvData = { categories: EnvCategory[] };

function maskValue(v: string): string {
  if (!v) return "";
  if (v.length <= 4) return "••••";
  return `••••••${v.slice(-4)}`;
}

export function EnvForm() {
  const [data, setData] = useState<EnvData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/env", { cache: "no-store" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `status ${res.status}`);
      }
      const json = (await res.json()) as EnvData;
      setData(json);
      setEdits({});
      if (!activeTab && json.categories[0]) setActiveTab(json.categories[0].id);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [activeTab]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const dirtyKeys = useMemo(() => Object.keys(edits), [edits]);

  const handleChange = (key: string, original: string, next: string) => {
    setEdits((prev) => {
      const copy = { ...prev };
      if (next === original) delete copy[key];
      else copy[key] = next;
      return copy;
    });
  };

  const submit = useCallback(async () => {
    if (dirtyKeys.length === 0) return;
    setSubmitting(true);
    try {
      const res = await fetch("/api/env", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ updates: edits }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        backup_path?: string;
        error?: string;
        code?: string;
      };
      if (!res.ok) {
        throw new Error(body.error ?? `status ${res.status}`);
      }
      const backupName = body.backup_path?.split("/").pop() ?? "(backup ok)";
      toast.success(
        `Saved ${dirtyKeys.length} variable(s). Restart the bot to apply.`,
        {
          description: `backup: ${backupName}`,
          duration: 8000,
          action: {
            label: "Go to Dashboard",
            onClick: () => {
              window.location.href = "/dashboard";
            },
          },
        },
      );
      await refresh();
    } catch (err) {
      toast.error("Save failed", { description: (err as Error).message });
    } finally {
      setSubmitting(false);
    }
  }, [dirtyKeys.length, edits, refresh]);

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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {dirtyKeys.length === 0
            ? `Root .env (${data.categories.reduce((n, c) => n + c.vars.length, 0)} variables)`
            : `${dirtyKeys.length} key(s) modified: ${dirtyKeys.join(", ")}`}
        </p>
        <Button
          size="sm"
          onClick={submit}
          disabled={dirtyKeys.length === 0 || submitting}
        >
          {submitting ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Save />
          )}
          Save
        </Button>
      </div>

      <Tabs
        value={activeTab ?? data.categories[0]?.id}
        onValueChange={setActiveTab}
      >
        <TabsList className="flex h-auto flex-wrap justify-start">
          {data.categories.map((c) => {
            const dirtyInCat = c.vars.filter((v) => v.key in edits).length;
            return (
              <TabsTrigger key={c.id} value={c.id}>
                {c.label}
                {dirtyInCat > 0 && (
                  <span className="ml-2 inline-block h-2 w-2 rounded-full bg-amber-500" />
                )}
              </TabsTrigger>
            );
          })}
        </TabsList>
        {data.categories.map((c) => {
          // Split the Bot tokens tab into two groups: native (main + imagegen)
          // on top, character bots (read-only, redirect-only) at the bottom.
          const isTokens = c.id === "tokens";
          const nativeVars = isTokens
            ? c.vars.filter((v) => !v.edit_redirect)
            : c.vars;
          const characterVars = isTokens
            ? c.vars.filter((v) => v.edit_redirect)
            : [];

          const renderField = (v: EnvVar) => {
            const current = edits[v.key] ?? v.value;
            const isRevealed = revealed[v.key];
            const isUnsetSecret = v.is_secret && !v.value;
            const showMasked = v.is_secret && !isRevealed && v.value !== "";
            const displayValue =
              showMasked && current === v.value
                ? maskValue(v.value)
                : current;
            const placeholder =
              v.value === ""
                ? v.default_value
                  ? `default: ${v.default_value}`
                  : isUnsetSecret
                    ? "(not set)"
                    : "(empty / optional)"
                : undefined;
            return (
              <div key={v.key} className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Label htmlFor={v.key} className="font-mono text-xs">
                    {v.key}
                  </Label>
                  {!v.editable && (
                    <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                      <Lock className="h-3 w-3" /> read-only
                    </span>
                  )}
                  {v.is_secret && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                      secret
                    </span>
                  )}
                  {v.value === "" && !v.is_secret && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                      empty
                    </span>
                  )}
                  {v.edit_redirect && (
                    <Link
                      href={v.edit_redirect}
                      className="ml-auto text-[11px] text-muted-foreground underline hover:text-foreground"
                    >
                      edit on character page →
                    </Link>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Input
                    id={v.key}
                    type="text"
                    value={displayValue}
                    placeholder={placeholder}
                    readOnly={showMasked && current === v.value}
                    disabled={!v.editable}
                    onChange={(e) =>
                      handleChange(v.key, v.value, e.target.value)
                    }
                    className="font-mono text-xs"
                  />
                  {v.is_secret && v.value !== "" && (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      onClick={() =>
                        setRevealed((p) => ({ ...p, [v.key]: !p[v.key] }))
                      }
                      aria-label={isRevealed ? "Hide value" : "Reveal value"}
                    >
                      {isRevealed ? <EyeOff /> : <Eye />}
                    </Button>
                  )}
                </div>
                {v.comment && (
                  <p className="text-xs text-muted-foreground">{v.comment}</p>
                )}
              </div>
            );
          };

          return (
            <TabsContent key={c.id} value={c.id}>
              {c.description && (
                <div className="mb-4 rounded-md border border-border/60 bg-muted/30 p-3 text-xs text-muted-foreground">
                  {c.description}
                </div>
              )}

              {isTokens ? (
                <>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Native bots — main + image generator
                  </div>
                  <div className="space-y-5">
                    {nativeVars.map(renderField)}
                  </div>
                  {characterVars.length > 0 && (
                    <>
                      <div className="mb-2 mt-8 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        Character bots — read-only
                      </div>
                      <p className="mb-3 text-xs text-muted-foreground">
                        Edit each character bot&apos;s token from its character page.
                        These rows mirror the live <code className="font-mono">.env</code> values.
                      </p>
                      <div className="space-y-5">
                        {characterVars.map(renderField)}
                      </div>
                    </>
                  )}
                </>
              ) : (
                <div className="space-y-5">{c.vars.map(renderField)}</div>
              )}
            </TabsContent>
          );
        })}
      </Tabs>

      {dirtyKeys.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Restart the bot from{" "}
          <Link href="/dashboard" className="underline">Dashboard</Link> to apply
          changes.
        </p>
      )}
    </div>
  );
}
