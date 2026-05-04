"use client";

import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
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

import { RawJsonPane } from "./raw-json-pane";
import { TabHeader } from "./tab-header";
import { useConfigFile } from "./use-config-file";

type DenylistFile = {
  _doc?: string;
  outfit_state_keywords: string[];
};

export function SfwDenylistTab() {
  const { data, setData, loading, saving, dirty, save, error } =
    useConfigFile<DenylistFile>("sfw_denylist");

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

  const meta = CONFIG_FILE_META.sfw_denylist;
  const filePath = CONFIG_FILE_DISPLAY_PATHS.sfw_denylist;

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
          <div className="space-y-3 rounded-md border p-4">
            <p className="text-xs text-muted-foreground">
              Words inside <code>[OUTFIT: …]</code> tags are silently dropped if they
              match any of these (case-insensitive, whole-word).
            </p>
            <div>
              <Label className="text-xs">Outfit state keywords</Label>
              <ChipsWidget
                value={data.outfit_state_keywords}
                onChange={(v) => setData({ ...data, outfit_state_keywords: v })}
              />
            </div>
          </div>
        </TabsContent>
        <TabsContent value="raw">
          <RawJsonPane value={data} onChange={setData} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
