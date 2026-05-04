import { LorebookPage } from "./lorebook-page";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Lorebook</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Per-character world knowledge. Each entry&apos;s keywords are
          substring-matched (case-insensitive) against the latest user message
          + last 4 chat turns; matching content is injected into the system
          prompt at runtime by{" "}
          <code className="font-mono">src/prompt.py</code>. Saves are auto-backed
          up; bot restart required.
        </p>
      </div>
      <LorebookPage />
    </div>
  );
}
