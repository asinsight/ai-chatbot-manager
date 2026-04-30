"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Copy,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type CharEntry = {
  charId: string;
  name: string;
  profile_summary_ko: string;
  mtime: number;
};

function formatTime(ms: number): string {
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return "—";
  }
}

export function CharactersList() {
  const router = useRouter();
  const [data, setData] = useState<CharEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<CharEntry | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/characters", { cache: "no-store" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `status ${res.status}`);
      }
      const json = (await res.json()) as { characters: CharEntry[] };
      setData(json.characters);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async () => {
    setBusy("create");
    try {
      const res = await fetch("/api/characters", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({}),
      });
      const body = (await res.json()) as { charId?: string; error?: string };
      if (!res.ok) throw new Error(body.error ?? `status ${res.status}`);
      toast.success(`Created ${body.charId} · restart bot to load`, {
        action: {
          label: "Go to Dashboard",
          onClick: () => router.push("/dashboard"),
        },
        duration: 8000,
      });
      router.push(`/characters/${body.charId}`);
    } catch (err) {
      toast.error("Create failed", { description: (err as Error).message });
    } finally {
      setBusy(null);
    }
  }, [router]);

  const duplicate = useCallback(
    async (charId: string) => {
      setBusy(`dup:${charId}`);
      try {
        const res = await fetch(`/api/characters/${charId}/duplicate`, {
          method: "POST",
        });
        const body = (await res.json()) as { charId?: string; error?: string };
        if (!res.ok) throw new Error(body.error ?? `status ${res.status}`);
        toast.success(`Duplicated to ${body.charId}`, {
          action: {
            label: "Go to Dashboard",
            onClick: () => router.push("/dashboard"),
          },
        });
        await refresh();
      } catch (err) {
        toast.error("Duplicate failed", { description: (err as Error).message });
      } finally {
        setBusy(null);
      }
    },
    [refresh, router],
  );

  const performDelete = useCallback(
    async (charId: string) => {
      setBusy(`del:${charId}`);
      try {
        const res = await fetch(`/api/characters/${charId}`, {
          method: "DELETE",
        });
        const body = (await res.json()) as {
          backup_dir?: string;
          error?: string;
        };
        if (!res.ok) throw new Error(body.error ?? `status ${res.status}`);
        toast.success(`Deleted ${charId} · restart bot to apply`, {
          description: `backup: ${body.backup_dir?.split("/").pop()}`,
          action: {
            label: "Go to Dashboard",
            onClick: () => router.push("/dashboard"),
          },
          duration: 8000,
        });
        await refresh();
      } catch (err) {
        toast.error("Delete failed", { description: (err as Error).message });
      } finally {
        setBusy(null);
        setPendingDelete(null);
      }
    },
    [refresh, router],
  );

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
          {data.length} character{data.length === 1 ? "" : "s"} · backed by 3
          files each (behaviors / persona / images).
        </p>
        <Button size="sm" onClick={create} disabled={busy !== null}>
          {busy === "create" ? <Loader2 className="animate-spin" /> : <Plus />}
          New character
        </Button>
      </div>

      {data.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No characters yet. Click <strong>New character</strong> to seed one.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {data.map((c) => (
            <Card key={c.charId}>
              <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 pb-2">
                <div>
                  <CardTitle className="font-mono text-sm">
                    {c.charId} · {c.name || <span className="text-muted-foreground">(unnamed)</span>}
                  </CardTitle>
                  <CardDescription className="mt-1 text-xs">
                    {formatTime(c.mtime)}
                  </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button asChild size="sm" variant="default">
                    <Link href={`/characters/${c.charId}`}>
                      <Pencil /> Edit
                    </Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() => duplicate(c.charId)}
                  >
                    {busy === `dup:${c.charId}` ? (
                      <Loader2 className="animate-spin" />
                    ) : (
                      <Copy />
                    )}
                    Duplicate
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={busy !== null}
                    onClick={() => setPendingDelete(c)}
                  >
                    <Trash2 /> Delete
                  </Button>
                </div>
              </CardHeader>
              {c.profile_summary_ko && (
                <CardContent className="pt-0 text-sm text-muted-foreground">
                  {c.profile_summary_ko}
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete {pendingDelete?.charId}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              The 3 character files are moved into{" "}
              <code className="font-mono text-xs">
                platform/data/backups/deleted/{pendingDelete?.charId}.&lt;timestamp&gt;/
              </code>{" "}
              and the matching{" "}
              <code className="font-mono text-xs">.env</code> lines are removed
              (also backed up). Recovery is a manual file copy. Restart the bot
              after delete to release the slot.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => pendingDelete && performDelete(pendingDelete.charId)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
