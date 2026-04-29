import { PromptsPage } from "./prompts-page";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Prompts</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Edit <code className="font-mono">config/grok_prompts.json</code> +{" "}
          <code className="font-mono">config/system_prompt.json</code> with
          per-key save, diff preview, and ${"${var}"} placeholder lint. Saves are
          auto-backed up; bot restart required to apply.
        </p>
      </div>
      <PromptsPage />
    </div>
  );
}
