"use client";

import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";

export const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[60vh] items-center justify-center rounded-md border bg-muted/30 text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading editor…
      </div>
    ),
  },
);
