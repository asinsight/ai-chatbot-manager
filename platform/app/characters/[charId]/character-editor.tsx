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

export function CharacterEditor({ charId }: { charId: string }) {
  const router = useRouter();
  const [original, setOriginal] = useState<CharacterCard | null>(null);
  const [draft, setDraft] = useState<CharacterCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<"form" | "raw">("form");

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
      setDraft(card);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [charId]);

  useEffect(() => {
    void load();
  }, [load]);

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
            ● dirty
          </span>
        )}
      </div>

      {mode === "form" ? (
        <FormMode
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
  draft,
  onChange,
  charName,
}: {
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
    </Tabs>
  );
}
