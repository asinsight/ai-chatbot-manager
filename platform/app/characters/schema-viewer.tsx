"use client";

import { useEffect, useState } from "react";
import { BookOpen, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { MonacoEditor } from "@/components/monaco-client";

type Resp = {
  file_path: string;
  content: unknown;
};

export function SchemaViewer() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Resp | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || data) return;
    void (async () => {
      try {
        const r = await fetch("/api/character-schema", { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = (await r.json()) as Resp;
        setData(body);
      } catch (err) {
        setError((err as Error).message);
      }
    })();
  }, [open, data]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm">
          <BookOpen className="h-4 w-4" /> View schema
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>Character card schema (read-only)</DialogTitle>
          <DialogDescription>
            JSON Schema (draft-2020-12) used to validate persona/charNN.json.
            Reference for what each field means and which fields are required.
            The file lives at{" "}
            <code className="font-mono">character_card_schema.json</code> at the
            repo root.
          </DialogDescription>
        </DialogHeader>
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
            Load failed: {error}
          </p>
        )}
        {!data && !error && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading schema…
          </div>
        )}
        {data && (
          <div className="overflow-hidden rounded-md border">
            <MonacoEditor
              height="65vh"
              defaultLanguage="json"
              value={JSON.stringify(data.content, null, 2)}
              options={{
                readOnly: true,
                wordWrap: "on",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                fontSize: 12,
                tabSize: 2,
              }}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
