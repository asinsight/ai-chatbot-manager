"use client";

import { useMemo, useState } from "react";

import { MonacoEditor } from "@/components/monaco-client";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

type CharacterCard = {
  charId: string;
  persona: Record<string, unknown>;
  behaviors: Record<string, unknown>;
  images: Record<string, unknown>;
};

type FileKey = "persona" | "behaviors" | "images";

const FILES: { id: FileKey; label: string }[] = [
  { id: "persona", label: "persona/charNN.json" },
  { id: "behaviors", label: "behaviors/charNN.json" },
  { id: "images", label: "images/charNN.json" },
];

export function RawTab({
  draft,
  onChange,
}: {
  draft: CharacterCard;
  onChange: (next: CharacterCard) => void;
}) {
  const initialJson = useMemo(
    () => ({
      persona: JSON.stringify(draft.persona, null, 2),
      behaviors: JSON.stringify(draft.behaviors, null, 2),
      images: JSON.stringify(draft.images, null, 2),
    }),
    // We only want the initial value; subsequent edits are tracked via setDraft
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [draft.charId],
  );
  const [text, setText] = useState(initialJson);
  const [errors, setErrors] = useState<Record<FileKey, string | null>>({
    persona: null,
    behaviors: null,
    images: null,
  });

  const update = (key: FileKey, raw: string) => {
    setText((prev) => ({ ...prev, [key]: raw }));
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      setErrors((prev) => ({ ...prev, [key]: null }));
      onChange({ ...draft, [key]: parsed });
    } catch (err) {
      setErrors((prev) => ({ ...prev, [key]: (err as Error).message }));
    }
  };

  return (
    <Tabs defaultValue="persona">
      <TabsList>
        {FILES.map((f) => (
          <TabsTrigger key={f.id} value={f.id}>
            {f.label}
            {errors[f.id] && (
              <span className="ml-2 inline-block h-2 w-2 rounded-full bg-destructive" />
            )}
          </TabsTrigger>
        ))}
      </TabsList>
      {FILES.map((f) => (
        <TabsContent key={f.id} value={f.id} className="space-y-2">
          {errors[f.id] && (
            <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
              JSON parse error: {errors[f.id]}
            </p>
          )}
          <div className="overflow-hidden rounded-md border">
            <MonacoEditor
              height="65vh"
              defaultLanguage="json"
              value={text[f.id]}
              onChange={(v) => update(f.id, v ?? "")}
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
        </TabsContent>
      ))}
    </Tabs>
  );
}
