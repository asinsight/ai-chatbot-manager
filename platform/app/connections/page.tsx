import { ConnectionsPage } from "./connections-page";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Connections</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Edit URLs + tokens for ComfyUI / OpenWebUI / Grok / Prompt Guard and verify with Ping.
        </p>
      </div>
      <ConnectionsPage />
    </div>
  );
}
