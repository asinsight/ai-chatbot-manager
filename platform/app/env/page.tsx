import { EnvForm } from "./env-form";

export const dynamic = "force-dynamic";

export default function EnvPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Env</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Edit root <code className="font-mono">.env</code> variables. Saves are
          auto-backed up; bot restart required to apply.
        </p>
      </div>
      <EnvForm />
    </div>
  );
}
