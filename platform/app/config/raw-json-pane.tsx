"use client";

import { useEffect, useState } from "react";

import { MonacoEditor } from "@/components/monaco-client";

export function RawJsonPane<T>({
  value,
  onChange,
  height = "60vh",
}: {
  value: T;
  onChange: (next: T) => void;
  height?: string;
}) {
  const [text, setText] = useState<string>(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [seeded, setSeeded] = useState<string>(() => JSON.stringify(value));

  // If the parent value changes (e.g. after save → state reset), reseed the editor.
  useEffect(() => {
    const cur = JSON.stringify(value);
    if (cur !== seeded) {
      setText(JSON.stringify(value, null, 2));
      setError(null);
      setSeeded(cur);
    }
  }, [value, seeded]);

  return (
    <div className="space-y-2">
      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
          JSON parse error: {error}
        </p>
      )}
      <div className="overflow-hidden rounded-md border">
        <MonacoEditor
          height={height}
          defaultLanguage="json"
          value={text}
          onChange={(v) => {
            const raw = v ?? "";
            setText(raw);
            try {
              const parsed = JSON.parse(raw) as T;
              setError(null);
              setSeeded(JSON.stringify(parsed));
              onChange(parsed);
            } catch (err) {
              setError((err as Error).message);
            }
          }}
          options={{
            wordWrap: "on",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 12,
            tabSize: 2,
            formatOnPaste: true,
          }}
        />
      </div>
    </div>
  );
}
