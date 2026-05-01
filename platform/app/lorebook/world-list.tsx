"use client";

import { useState } from "react";
import { Copy, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

import { isValidWorldName, type WorldSummary } from "@/lib/lorebook-meta";

export function WorldList({
  worlds,
  selected,
  onSelect,
  onChanged,
}: {
  worlds: WorldSummary[];
  selected: string | null;
  onSelect: (name: string) => void;
  onChanged: () => Promise<void> | void;
}) {
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const create = async () => {
    const name = newName.trim();
    if (!name) return;
    if (!isValidWorldName(name)) {
      toast.error(`invalid name (use lowercase letters, digits, underscores; can't be 'mapping')`);
      return;
    }
    setCreating(true);
    try {
      const r = await fetch("/api/lorebook/worlds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const body = (await r.json()) as { ok?: boolean; name?: string; error?: string; code?: string };
      if (!r.ok) {
        toast.error(`Create failed (${body.code ?? r.status}): ${body.error ?? ""}`);
        return;
      }
      toast.success(`Created world: ${body.name}`);
      setNewName("");
      await onChanged();
      if (body.name) onSelect(body.name);
    } catch (err) {
      toast.error(`Create failed: ${(err as Error).message}`);
    } finally {
      setCreating(false);
    }
  };

  const duplicate = async (name: string) => {
    const r = await fetch(`/api/lorebook/worlds/${encodeURIComponent(name)}/duplicate`, {
      method: "POST",
    });
    const body = (await r.json()) as { ok?: boolean; name?: string; error?: string; code?: string };
    if (!r.ok) {
      toast.error(`Duplicate failed (${body.code ?? r.status}): ${body.error ?? ""}`);
      return;
    }
    toast.success(`Duplicated → ${body.name}`);
    await onChanged();
    if (body.name) onSelect(body.name);
  };

  const del = async (name: string) => {
    const r = await fetch(`/api/lorebook/worlds/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    const body = (await r.json()) as { ok?: boolean; error?: string; code?: string };
    if (!r.ok) {
      toast.error(`Delete failed (${body.code ?? r.status}): ${body.error ?? ""}`);
      return;
    }
    toast.success(`Deleted: ${name}`);
    if (selected === name) onSelect("");
    await onChanged();
  };

  return (
    <div className="rounded-md border">
      <div className="space-y-2 border-b p-2">
        <Input
          value={newName}
          placeholder="new_world_id"
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void create();
            }
          }}
          className="font-mono text-xs"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full"
          disabled={creating}
          onClick={() => void create()}
        >
          <Plus /> Add world
        </Button>
      </div>
      <div className="max-h-[60vh] overflow-y-auto">
        {worlds.length === 0 && (
          <p className="p-3 text-xs italic text-muted-foreground">
            (no worlds yet — add one above)
          </p>
        )}
        {worlds.map((w) => (
          <div
            key={w.name}
            className={`group flex items-start gap-1 border-b px-2 py-2 hover:bg-muted/40 ${
              selected === w.name ? "bg-muted" : ""
            }`}
          >
            <button
              type="button"
              onClick={() => onSelect(w.name)}
              className="min-w-0 flex-1 text-left"
            >
              <div className="font-mono text-xs">{w.name}</div>
              <div className="text-[10px] text-muted-foreground">
                {w.entry_count} {w.entry_count === 1 ? "entry" : "entries"}
                {w.mapped_chars.length > 0 && (
                  <> · used by {w.mapped_chars.join(", ")}</>
                )}
              </div>
            </button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-6 w-6 opacity-0 group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                void duplicate(w.name);
              }}
              title="Duplicate"
            >
              <Copy className="h-3 w-3" />
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-6 w-6 opacity-0 group-hover:opacity-100"
                  onClick={(e) => e.stopPropagation()}
                  title="Delete"
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent onClick={(e) => e.stopPropagation()}>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete world &lsquo;{w.name}&rsquo;?</AlertDialogTitle>
                  <AlertDialogDescription>
                    {w.mapped_chars.length > 0 ? (
                      <>
                        Delete will fail with <code className="font-mono">WORLD_IN_USE</code>{" "}
                        because{" "}
                        <code className="font-mono">{w.mapped_chars.join(", ")}</code>{" "}
                        currently map to this world. Update the Character mapping
                        first.
                      </>
                    ) : (
                      <>
                        The file is removed; a backup `.bak` is written
                        automatically. The bot still needs a restart to drop
                        the cached lorebook.
                      </>
                    )}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => void del(w.name)}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        ))}
      </div>
    </div>
  );
}
