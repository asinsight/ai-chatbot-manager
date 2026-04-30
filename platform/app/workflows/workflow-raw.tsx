"use client";

import { MonacoEditor } from "@/components/monaco-client";

export function WorkflowRaw({ content }: { content: object }) {
  const text = JSON.stringify(content, null, 2);
  return (
    <div className="overflow-hidden rounded-md border">
      <MonacoEditor
        height="65vh"
        defaultLanguage="json"
        value={text}
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
  );
}
