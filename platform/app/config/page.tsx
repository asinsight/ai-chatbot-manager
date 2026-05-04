import { ConfigPage } from "./config-page";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Image Config</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Edit the SFW scene catalog, pose-motion presets, outfit denylist, and
          the character-card JSON Schema. Saves are auto-backed up; bot restart
          is required for the bot to reload.
        </p>
      </div>
      <ConfigPage />
    </div>
  );
}
