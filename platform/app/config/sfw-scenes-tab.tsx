"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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

type SceneEntry = {
  label: string;
  person_tags: string;
  pose_pool: string[];
  camera_pool: string[];
  location_pool: string[];
  activity_tags: string;
  expression_hint: string;
  notes?: string;
};

type ScenesFile = Record<string, SceneEntry | string>;

const TEMPLATE: SceneEntry = {
  label: "PLACEHOLDER — short English description",
  person_tags: "1girl, solo",
  pose_pool: [],
  camera_pool: [],
  location_pool: [],
  activity_tags: "",
  expression_hint: "",
  notes: "",
};

const KEY_RE = /^[a-z][a-z0-9_]*$/;

export function SfwScenesTab() {
  const { data, setData, loading, saving, dirty, save, error } =
    useConfigFile<ScenesFile>("sfw_scenes");
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const sceneKeys = useMemo(() => {
    if (!data) return [];
    return Object.keys(data)
      .filter((k) => !k.startsWith("_"))
      .sort();
  }, [data]);

  const filteredKeys = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return sceneKeys;
    return sceneKeys.filter((k) => {
      if (k.toLowerCase().includes(q)) return true;
      const v = data?.[k];
      if (typeof v === "object" && v && "label" in v) {
        return String((v as SceneEntry).label).toLowerCase().includes(q);
      }
      return false;
    });
  }, [sceneKeys, filter, data]);

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

  const meta = CONFIG_FILE_META.sfw_scenes;
  const filePath = CONFIG_FILE_DISPLAY_PATHS.sfw_scenes;

  const updateEntry = (key: string, patch: Partial<SceneEntry>) => {
    if (!data) return;
    const current = data[key];
    if (typeof current !== "object" || !current) return;
    setData({ ...data, [key]: { ...(current as SceneEntry), ...patch } });
  };

  const addScene = (newKey: string) => {
    if (!data) return;
    setData({ ...data, [newKey]: { ...TEMPLATE, pose_pool: [], camera_pool: [], location_pool: [] } });
    setSelected(newKey);
  };

  const deleteScene = (key: string) => {
    if (!data) return;
    const next = { ...data };
    delete next[key];
    setData(next);
    setSelected(null);
  };

  const sel = selected && data[selected];
  const selEntry = sel && typeof sel === "object" ? (sel as SceneEntry) : null;

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
            <Button
              size="sm"
              disabled={!dirty || saving}
              onClick={() => void save(data)}
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
            </Button>
          </div>
        </div>
        <TabsContent value="form">
          <div className="mb-3">
            <Input
              value={filter}
              placeholder="Filter scenes by key or label…"
              onChange={(e) => setFilter(e.target.value)}
              className="max-w-md text-xs"
            />
          </div>
          <MasterDetail
            keys={filteredKeys}
            selected={selected}
            onSelect={setSelected}
            onAdd={addScene}
            onDelete={deleteScene}
            itemLabel="scene"
            newKeyHint="new_scene_key"
            newKeyValidator={(k) =>
              !KEY_RE.test(k)
                ? "key must match /^[a-z][a-z0-9_]*$/"
                : null
            }
            renderRow={(k) => {
              const v = data[k];
              const lbl = typeof v === "object" && v && "label" in v ? String((v as SceneEntry).label) : "";
              return (
                <div>
                  <div className="font-mono">{k}</div>
                  <div className="text-[10px] text-muted-foreground truncate">{lbl}</div>
                </div>
              );
            }}
          >
            {selEntry && selected && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">Label</Label>
                  <Input
                    value={selEntry.label}
                    onChange={(e) => updateEntry(selected, { label: e.target.value })}
                    className="text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Person tags (Danbooru, comma-sep)</Label>
                  <Input
                    value={selEntry.person_tags}
                    onChange={(e) => updateEntry(selected, { person_tags: e.target.value })}
                    className="font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Pose pool</Label>
                  <ChipsWidget
                    value={selEntry.pose_pool}
                    onChange={(v) => updateEntry(selected, { pose_pool: v })}
                  />
                </div>
                <div>
                  <Label className="text-xs">Camera pool</Label>
                  <ChipsWidget
                    value={selEntry.camera_pool}
                    onChange={(v) => updateEntry(selected, { camera_pool: v })}
                  />
                </div>
                <div>
                  <Label className="text-xs">Location pool</Label>
                  <ChipsWidget
                    value={selEntry.location_pool}
                    onChange={(v) => updateEntry(selected, { location_pool: v })}
                  />
                </div>
                <div>
                  <Label className="text-xs">Activity tags (comma-sep)</Label>
                  <Input
                    value={selEntry.activity_tags}
                    onChange={(e) => updateEntry(selected, { activity_tags: e.target.value })}
                    className="font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Expression hint</Label>
                  <Input
                    value={selEntry.expression_hint}
                    onChange={(e) => updateEntry(selected, { expression_hint: e.target.value })}
                    className="font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Notes</Label>
                  <Textarea
                    value={selEntry.notes ?? ""}
                    onChange={(e) => updateEntry(selected, { notes: e.target.value })}
                    rows={2}
                    className="text-xs"
                  />
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
