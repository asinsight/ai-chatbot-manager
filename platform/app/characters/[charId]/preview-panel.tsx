"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function PreviewPanel({
  charName,
  firstMes,
  description,
}: {
  charName: string;
  firstMes: string;
  description: string;
}) {
  const substitute = (s: string) =>
    s
      .replaceAll("{{char}}", charName || "Character")
      .replaceAll("{{user}}", "User");

  return (
    <div className="sticky top-4 space-y-4 rounded-md border bg-muted/20 p-4 text-xs">
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Preview · first_mes
        </h3>
        {firstMes ? (
          <div className="prose prose-sm max-w-none text-foreground dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {substitute(firstMes)}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="italic text-muted-foreground">(empty)</p>
        )}
      </div>
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Preview · description
        </h3>
        {description ? (
          <div className="prose prose-sm max-w-none text-foreground dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {substitute(description)}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="italic text-muted-foreground">(empty)</p>
        )}
      </div>
      <p className="text-[10px] text-muted-foreground">
        Macros: {"{{user}}"} → "User", {"{{char}}"} → character name.
      </p>
    </div>
  );
}
