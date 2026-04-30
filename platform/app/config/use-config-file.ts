"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import type { ConfigFileKey } from "@/lib/config-files-meta";

type Loaded = {
  key: ConfigFileKey;
  content: unknown;
  mtime: number;
};

export function useConfigFile<T>(fileKey: ConfigFileKey) {
  const [data, setData] = useState<T | null>(null);
  const [original, setOriginal] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastBackup, setLastBackup] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/config/${fileKey}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const payload = (await r.json()) as Loaded;
      setData(payload.content as T);
      setOriginal(JSON.parse(JSON.stringify(payload.content)) as T);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [fileKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = useCallback(
    async (next: T): Promise<{ ok: boolean; warnings?: { path: string; message: string }[] }> => {
      setSaving(true);
      try {
        const r = await fetch(`/api/config/${fileKey}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: next }),
        });
        const body = (await r.json()) as {
          ok?: boolean;
          backup_path?: string;
          warnings?: { path: string; message: string }[];
          error?: string;
          code?: string;
          details?: string[];
        };
        if (!r.ok) {
          const detail =
            body.details && body.details.length
              ? `: ${body.details.slice(0, 3).join("; ")}${body.details.length > 3 ? "…" : ""}`
              : body.error
                ? `: ${body.error}`
                : "";
          toast.error(`Save failed (${body.code ?? r.status})${detail}`);
          return { ok: false };
        }
        if (body.backup_path) setLastBackup(body.backup_path);
        setData(next);
        setOriginal(JSON.parse(JSON.stringify(next)) as T);
        if (body.warnings && body.warnings.length > 0) {
          toast.warning(`Saved with ${body.warnings.length} warning(s) · restart bot to load`);
        } else {
          toast.success("Saved · restart bot to load");
        }
        return { ok: true, warnings: body.warnings };
      } catch (err) {
        toast.error(`Save failed: ${(err as Error).message}`);
        return { ok: false };
      } finally {
        setSaving(false);
      }
    },
    [fileKey],
  );

  const dirty = data !== null && original !== null && JSON.stringify(data) !== JSON.stringify(original);

  return {
    data,
    setData,
    original,
    loading,
    saving,
    error,
    dirty,
    lastBackup,
    save,
    reload: load,
  };
}
