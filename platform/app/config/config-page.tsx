"use client";

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import { PoseMotionPresetsTab } from "./pose-motion-presets-tab";
import { SfwDenylistTab } from "./sfw-denylist-tab";
import { SfwScenesTab } from "./sfw-scenes-tab";

const TABS = [
  { id: "sfw_scenes", label: "SFW scenes" },
  { id: "pose_motion_presets", label: "Pose motion presets" },
  { id: "sfw_denylist", label: "SFW denylist" },
] as const;

export function ConfigPage() {
  return (
    <Tabs defaultValue="sfw_scenes">
      <TabsList className="flex h-auto flex-wrap justify-start">
        {TABS.map((t) => (
          <TabsTrigger key={t.id} value={t.id}>
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>
      <TabsContent value="sfw_scenes">
        <SfwScenesTab />
      </TabsContent>
      <TabsContent value="pose_motion_presets">
        <PoseMotionPresetsTab />
      </TabsContent>
      <TabsContent value="sfw_denylist">
        <SfwDenylistTab />
      </TabsContent>
    </Tabs>
  );
}
