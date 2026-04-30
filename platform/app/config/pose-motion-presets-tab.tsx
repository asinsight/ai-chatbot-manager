"use client";

import { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import {
  CONFIG_FILE_DISPLAY_PATHS,
  CONFIG_FILE_META,
} from "@/lib/config-files-meta";

import { MasterDetail } from "./master-detail";
import { RawJsonPane } from "./raw-json-pane";
import { TabHeader } from "./tab-header";
import { useConfigFile } from "./use-config-file";

type PresetEntry = {
  primary: string;
  camera: string;
  audio: string;
  ambient_fallback: string;
  anchor_risk: "low" | "medium" | "high";
  notes?: string;
};

type PresetFile = Record<string, PresetEntry | unknown>;

const TEMPLATE: PresetEntry = {
  primary: "",
  camera: "fixed lens, slow push-in",
  audio: "soft breath, quiet room tone",
  ambient_fallback: "micro-blink, soft breath, subtle weight shift",
  anchor_risk: "low",
  notes: "",
};

const KEY_RE = /^[a-z][a-z0-9_]*$/;

export function PoseMotionPresetsTab() {
  const { data, setData, loading, saving, dirty, save, error } =
    useConfigFile<PresetFile>("pose_motion_presets");
  const [selected, setSelected] = useState<string | null>("generic");

  const keys = useMemo(() => {
    if (!data) return [];
    return Object.keys(data)
      .filter((k) => !k.startsWith("_"))
      .sort();
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

  const meta = CONFIG_FILE_META.pose_motion_presets;
  const filePath = CONFIG_FILE_DISPLAY_PATHS.pose_motion_presets;

  const updateEntry = (key: string, patch: Partial<PresetEntry>) => {
    const current = data[key];
    if (typeof current !== "object" || !current) return;
    setData({ ...data, [key]: { ...(current as PresetEntry), ...patch } });
  };

  const addPreset = (newKey: string) => {
    setData({ ...data, [newKey]: { ...TEMPLATE } });
    setSelected(newKey);
  };

  const deletePreset = (key: string) => {
    if (key === "generic") return;
    const next = { ...data };
    delete next[key];
    setData(next);
    setSelected(null);
  };

  const sel = selected && data[selected];
  const selEntry =
    sel && typeof sel === "object" && "primary" in sel
      ? (sel as PresetEntry)
      : null;

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
            onSelect={setSelected}
            onAdd={addPreset}
            onDelete={deletePreset}
            itemLabel="preset"
            newKeyHint="new_pose_key"
            newKeyValidator={(k) => (!KEY_RE.test(k) ? "key must match /^[a-z][a-z0-9_]*$/" : null)}
            protectedKeys={["generic"]}
          >
            {selEntry && selected && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">Primary motion</Label>
                  <Textarea
                    value={selEntry.primary}
                    onChange={(e) => updateEntry(selected, { primary: e.target.value })}
                    rows={4}
                    className="font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Camera</Label>
                  <Input
                    value={selEntry.camera}
                    onChange={(e) => updateEntry(selected, { camera: e.target.value })}
                    className="font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Audio</Label>
                  <Input
                    value={selEntry.audio}
                    onChange={(e) => updateEntry(selected, { audio: e.target.value })}
                    className="font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Ambient fallback</Label>
                  <Input
                    value={selEntry.ambient_fallback}
                    onChange={(e) => updateEntry(selected, { ambient_fallback: e.target.value })}
                    className="font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">Anchor risk</Label>
                  <Select
                    value={selEntry.anchor_risk}
                    onValueChange={(v) =>
                      updateEntry(selected, { anchor_risk: v as PresetEntry["anchor_risk"] })
                    }
                  >
                    <SelectTrigger className="text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">low</SelectItem>
                      <SelectItem value="medium">medium</SelectItem>
                      <SelectItem value="high">high</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Notes</Label>
                  <Textarea
                    value={selEntry.notes ?? ""}
                    onChange={(e) => updateEntry(selected, { notes: e.target.value })}
                    rows={3}
                    className="text-xs"
                  />
                </div>
                {selected === "generic" && (
                  <p className="text-xs text-muted-foreground">
                    Note: <code>generic</code> is the lookup() fallback and cannot be deleted.
                  </p>
                )}
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
