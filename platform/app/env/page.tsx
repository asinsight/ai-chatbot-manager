import { EnvForm } from "./env-form";

export const dynamic = "force-dynamic";

export default function EnvPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Env</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          루트 <code className="font-mono">.env</code> 변수 편집. 저장 시 자동
          백업, 봇 재시작 필요.
        </p>
      </div>
      <EnvForm />
    </div>
  );
}
