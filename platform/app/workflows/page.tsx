import { WorkflowsPage } from "./workflows-page";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Workflows</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage the ComfyUI workflow JSONs in{" "}
          <code className="font-mono">comfyui_workflow/</code>. Pick which file
          backs each rendering stage (Standard / HQ), edit safe parameters
          (checkpoint, sampler, save filename) without touching graph topology,
          or paste a fresh export from ComfyUI&apos;s &ldquo;Save (API
          Format)&rdquo; via Replace. Saves are auto-backed up; bot restart is
          required.
        </p>
      </div>
      <WorkflowsPage />
    </div>
  );
}
