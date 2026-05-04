"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import { ChipsWidget } from "@/app/characters/[charId]/widgets";
import {
  CONFIG_FILE_DISPLAY_PATHS,
  CONFIG_FILE_META,
} from "@/lib/config-files-meta";

import { MasterDetail } from "./master-detail";
import { RawJsonPane } from "./raw-json-pane";
import { TabHeader } from "./tab-header";
import { useConfigFile } from "./use-config-file";

type ProfileKeysFile = {
  _doc?: string;
  canonical_keys: Record<string, string[]>;
};

const KEY_RE = /^[a-z][a-z0-9_]*$/;

export function ProfileKeysTab() {
  const { data, setData, loading, saving, dirty, save, error } =
    useConfigFile<ProfileKeysFile>("profile_keys");
  const [selected, setSelected] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState<string>("");

  const keys = useMemo(() => {
    if (!data) return [];
    return Object.keys(data.canonical_keys).sort();
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (error || !data) {
    return <p className="text-sm text-destructive">Load failed: {error}</p>;
  }

  const meta = CONFIG_FILE_META.profile_keys;
  const filePath = CONFIG_FILE_DISPLAY_PATHS.profile_keys;

  const setAliases = (key: string, aliases: string[]) => {
    setData({
      ...data,
      canonical_keys: { ...data.canonical_keys, [key]: aliases },
    });
  };

  const addKey = (newKey: string) => {
    setData({
      ...data,
      canonical_keys: { ...data.canonical_keys, [newKey]: [newKey] },
    });
    setSelected(newKey);
  };

  const deleteKey = (key: string) => {
    const next = { ...data.canonical_keys };
    delete next[key];
    setData({ ...data, canonical_keys: next });
    setSelected(null);
  };

  const renameKey = (oldKey: string, newKey: string) => {
    if (!KEY_RE.test(newKey)) return;
    if (newKey === oldKey) return;
    if (data.canonical_keys[newKey] !== undefined) return;
    const aliases = data.canonical_keys[oldKey];
    const next: Record<string, string[]> = {};
    for (const k of Object.keys(data.canonical_keys)) {
      if (k === oldKey) {
        next[newKey] = aliases;
      } else {
        next[k] = data.canonical_keys[k];
      }
    }
    setData({ ...data, canonical_keys: next });
    setSelected(newKey);
  };

  const aliases = selected ? data.canonical_keys[selected] ?? [] : null;

  return (
    <div className="space-y-4">
      <TabHeader
        title={meta.title}
        summary={meta.summary}
        usedBy={meta.usedBy}
        filePath={filePath}
      />
      <Tabs defaultValue="form">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="form">Form</TabsTrigger>
            <TabsTrigger value="raw">Raw JSON</TabsTrigger>
          </TabsList>
          <div className="flex items-center gap-2 text-xs">
            {dirty && <span className="text-amber-600">● unsaved</span>}
            <Button size="sm" disabled={!dirty || saving} onClick={() => void save(data)}>
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
            </Button>
          </div>
        </div>
        <TabsContent value="form">
          <MasterDetail
            keys={keys}
            selected={selected}
            onSelect={(k) => {
              setSelected(k);
              setRenameDraft(k);
            }}
            onAdd={addKey}
            onDelete={deleteKey}
            itemLabel="key"
            newKeyHint="canonical_key"
            newKeyValidator={(k) => (!KEY_RE.test(k) ? "key must match /^[a-z][a-z0-9_]*$/" : null)}
          >
            {selected && aliases && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">Canonical key (rename on blur)</Label>
                  <div className="flex gap-2">
                    <Input
                      value={renameDraft}
                      onChange={(e) => setRenameDraft(e.target.value)}
                      onBlur={() => {
                        if (renameDraft !== selected) renameKey(selected, renameDraft);
                      }}
                      className="font-mono text-xs"
                    />
                  </div>
                </div>
                <div>
                  <Label className="text-xs">Aliases</Label>
                  <ChipsWidget value={aliases} onChange={(v) => setAliases(selected, v)} />
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    The canonical key itself is included in aliases by convention; remove
                    it manually if you really want to exclude self-match.
                  </p>
                </div>
              </div>
            )}
          </MasterDetail>
        </TabsContent>
        <TabsContent value="raw">
          <RawJsonPane value={data} onChange={setData} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
