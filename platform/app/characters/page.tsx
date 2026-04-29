import { CharactersList } from "./characters-list";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Characters</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Each character is a 3-file bundle (
          <code className="font-mono">behaviors/charNN.json</code> +{" "}
          <code className="font-mono">persona/charNN.json</code> +{" "}
          <code className="font-mono">images/charNN.json</code>) plus 4{" "}
          <code className="font-mono">.env</code> token lines (TEST_/PROD_ ×
          BOT/USERNAME). Bot restart required after add / edit / delete.
        </p>
      </div>
      <CharactersList />
    </div>
  );
}
