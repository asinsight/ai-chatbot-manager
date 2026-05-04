"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import { ProfileKeysTab } from "@/app/config/profile-keys-tab";

import { PromptEditor } from "./prompt-editor";

type PromptKey = { name: string; value: string; size: number };
type PromptFile = "grok" | "system";
type Resp = { file: PromptFile; keys: PromptKey[] };

const FILES: { id: PromptFile; label: string }[] = [
  { id: "grok", label: "Grok prompting" },
  { id: "system", label: "System prompt" },
];

export function PromptsPage() {
  const [data, setData] = useState<Record<PromptFile, PromptKey[]> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [g, s] = await Promise.all([
        fetch("/api/prompts/grok", { cache: "no-store" }).then(
          (r) => r.json() as Promise<Resp>,
        ),
        fetch("/api/prompts/system", { cache: "no-store" }).then(
          (r) => r.json() as Promise<Resp>,
        ),
      ]);
      setData({ grok: g.keys, system: s.keys });
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return <div className="text-sm text-destructive">Load failed: {error}</div>;
  }
  if (!data) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading prompts…
      </div>
    );
  }

  return (
    <Tabs defaultValue="grok">
      <TabsList>
        {FILES.map((f) => (
          <TabsTrigger key={f.id} value={f.id}>
            {f.label}
          </TabsTrigger>
        ))}
        <TabsTrigger value="profile_keys">Profile keys</TabsTrigger>
      </TabsList>
      {FILES.map((f) => (
        <TabsContent key={f.id} value={f.id}>
          <KeyTabs file={f.id} keys={data[f.id]} onSaved={load} />
        </TabsContent>
      ))}
      <TabsContent value="profile_keys">
        <ProfileKeysTab />
      </TabsContent>
    </Tabs>
  );
}

function KeyTabs({
  file,
  keys,
  onSaved,
}: {
  file: PromptFile;
  keys: PromptKey[];
  onSaved: () => Promise<void> | void;
}) {
  const [active, setActive] = useState<string>(keys[0]?.name ?? "");
  if (keys.length === 0) return null;
  return (
    <Tabs value={active} onValueChange={setActive}>
      <TabsList className="flex h-auto flex-wrap justify-start">
        {keys.map((k) => (
          <TabsTrigger key={k.name} value={k.name}>
            {k.name}
          </TabsTrigger>
        ))}
      </TabsList>
      {keys.map((k) => (
        <TabsContent key={k.name} value={k.name}>
          <PromptEditor file={file} initial={k} onSaved={onSaved} />
        </TabsContent>
      ))}
    </Tabs>
  );
}
