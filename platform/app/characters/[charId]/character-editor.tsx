"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import { SchemaViewer } from "../schema-viewer";

import { BotTokensForm } from "./bot-tokens-form";
import { PersonaForm } from "./persona-form";
import { BehaviorsForm } from "./behaviors-form";
import { ImagesForm } from "./images-form";
import { PreviewPanel } from "./preview-panel";
import { RawTab } from "./raw-tab";

type CharacterCard = {
  charId: string;
  persona: Record<string, unknown>;
  behaviors: Record<string, unknown>;
  images: Record<string, unknown>;
};

type DraftBlob = {
  ts: number;
  card: CharacterCard;
};

function draftKey(charId: string): string {
  return `char-draft-${charId}`;
}

function readDraft(charId: string): DraftBlob | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(draftKey(charId));
    if (!raw) return null;
    return JSON.parse(raw) as DraftBlob;
  } catch {
    return null;
  }
}

function writeDraft(charId: string, card: CharacterCard): void {
  try {
    window.localStorage.setItem(
      draftKey(charId),
      JSON.stringify({ ts: Date.now(), card }),
    );
  } catch {
    // quota exceeded — ignore (drafts are best-effort)
  }
}

function clearDraft(charId: string): void {
  try {
    window.localStorage.removeItem(draftKey(charId));
  } catch {
    // ignore
  }
}

export function CharacterEditor({ charId }: { charId: string }) {
  const router = useRouter();
  const [original, setOriginal] = useState<CharacterCard | null>(null);
  const [draft, setDraft] = useState<CharacterCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<"form" | "raw">("form");
  const [pendingRestore, setPendingRestore] = useState<DraftBlob | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/characters/${charId}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `status ${res.status}`);
      }
      const card = (await res.json()) as CharacterCard;
      setOriginal(card);
      // Probe for an unsaved draft. Show restore banner if it differs from disk.
      const stored = readDraft(charId);
      if (
        stored &&
        JSON.stringify(stored.card) !== JSON.stringify(card)
      ) {
        setPendingRestore(stored);
        setDraft(card); // start from disk; user picks restore via banner
      } else {
        if (stored) clearDraft(charId);
        setDraft(card);
      }
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [charId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Persist draft to localStorage whenever it diverges from original.
  useEffect(() => {
    if (!original || !draft) return;
    if (JSON.stringify(original) === JSON.stringify(draft)) {
      clearDraft(charId);
      return;
    }
    const id = setTimeout(() => writeDraft(charId, draft), 400);
    return () => clearTimeout(id);
  }, [charId, draft, original]);

  const dirty = original && draft
    ? JSON.stringify(original.persona) !== JSON.stringify(draft.persona) ||
      JSON.stringify(original.behaviors) !== JSON.stringify(draft.behaviors) ||
      JSON.stringify(original.images) !== JSON.stringify(draft.images)
    : false;

  const save = useCallback(async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/characters/${charId}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          persona: draft.persona,
          behaviors: draft.behaviors,
          images: draft.images,
        }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        backup_paths?: string[];
        error?: string;
      };
      if (!res.ok) throw new Error(body.error ?? `status ${res.status}`);
      const n = body.backup_paths?.length ?? 0;
      toast.success(`${charId} saved · restart bot to load`, {
        description: n > 0 ? `${n} backups created` : undefined,
        action: {
          label: "Go to Dashboard",
          onClick: () => router.push("/dashboard"),
        },
        duration: 8000,
      });
      clearDraft(charId);
      await load();
    } catch (err) {
      toast.error("Save failed", { description: (err as Error).message });
    } finally {
      setSaving(false);
    }
  }, [charId, draft, load, router]);

  if (error) {
    return <div className="text-sm text-destructive">Load failed: {error}</div>;
  }
  if (!draft || !original) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  const charName = typeof draft.persona.name === "string" ? draft.persona.name : "";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Button asChild size="sm" variant="ghost">
          <a href="/characters">
            <ArrowLeft /> Back to list
          </a>
        </Button>
        <div className="flex items-center gap-2">
          <SchemaViewer />
          <Tabs
            value={mode}
            onValueChange={(v) => setMode(v as "form" | "raw")}
          >
            <TabsList>
              <TabsTrigger value="form">Form</TabsTrigger>
              <TabsTrigger value="raw">Raw JSON</TabsTrigger>
            </TabsList>
          </Tabs>
          <Button onClick={save} disabled={!dirty || saving}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />}
            Save all
          </Button>
        </div>
      </div>

      <div className="rounded-md border bg-muted/20 p-3 text-xs">
        <span className="font-mono">{charId}</span>
        {charName && <> · {charName}</>}
        {dirty && (
          <span className="ml-2 inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-700 dark:text-amber-400">
            ● dirty (auto-saved as draft)
          </span>
        )}
      </div>

      {pendingRestore && (
        <div className="flex items-center justify-between rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
          <span className="text-amber-700 dark:text-amber-400">
            Unsaved draft from{" "}
            {new Date(pendingRestore.ts).toLocaleString()} found.
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                clearDraft(charId);
                setPendingRestore(null);
              }}
            >
              Discard
            </Button>
            <Button
              size="sm"
              onClick={() => {
                setDraft(pendingRestore.card);
                setPendingRestore(null);
              }}
            >
              Restore draft
            </Button>
          </div>
        </div>
      )}

      {mode === "form" ? (
        <FormMode
          charId={charId}
          draft={draft}
          onChange={setDraft}
          charName={charName}
        />
      ) : (
        <RawTab draft={draft} onChange={setDraft} />
      )}
    </div>
  );
}

function FormMode({
  charId,
  draft,
  onChange,
  charName,
}: {
  charId: string;
  draft: CharacterCard;
  onChange: (next: CharacterCard) => void;
  charName: string;
}) {
  return (
    <Tabs defaultValue="persona">
      <TabsList>
        <TabsTrigger value="persona">Persona</TabsTrigger>
        <TabsTrigger value="behaviors">Behaviors</TabsTrigger>
        <TabsTrigger value="images">Images</TabsTrigger>
        <TabsTrigger value="bot-tokens">Bot tokens</TabsTrigger>
      </TabsList>

      <TabsContent value="persona">
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <PersonaForm
            value={draft.persona}
            onChange={(persona) => onChange({ ...draft, persona })}
          />
          <PreviewPanel
            charName={charName}
            firstMes={
              typeof draft.persona.first_mes === "string"
                ? draft.persona.first_mes
                : ""
            }
            description={
              typeof draft.persona.description === "string"
                ? draft.persona.description
                : ""
            }
          />
        </div>
      </TabsContent>

      <TabsContent value="behaviors">
        <BehaviorsForm
          value={draft.behaviors}
          onChange={(behaviors) => onChange({ ...draft, behaviors })}
        />
      </TabsContent>

      <TabsContent value="images">
        <ImagesForm
          value={draft.images}
          onChange={(images) => onChange({ ...draft, images })}
        />
      </TabsContent>

      <TabsContent value="bot-tokens">
        <BotTokensForm charId={charId} />
      </TabsContent>
    </Tabs>
  );
}
