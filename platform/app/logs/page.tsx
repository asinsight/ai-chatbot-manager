import { LogsPage } from "./logs-page";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Logs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Tail <code className="font-mono">logs/bot.log</code> and the dated
          archives. Pick a file, set the tail size, refresh interval, and an
          optional regex filter (case-insensitive). The dashboard log card stays
          for quick glances; this page is the full viewer.
        </p>
      </div>
      <LogsPage />
    </div>
  );
}
