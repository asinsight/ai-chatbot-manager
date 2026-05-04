export function TabHeader({
  title,
  summary,
  usedBy,
  filePath,
}: {
  title: string;
  summary: string;
  usedBy: string;
  filePath: string;
}) {
  return (
    <div className="space-y-1 rounded-md border bg-muted/30 p-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        <code className="font-mono text-xs text-muted-foreground">{filePath}</code>
      </div>
      <p className="text-xs text-muted-foreground">{summary}</p>
      <p className="text-xs text-muted-foreground">
        <span className="font-semibold">Used by:</span> {usedBy}
      </p>
    </div>
  );
}
