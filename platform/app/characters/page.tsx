import { CharactersList } from "./characters-list";
import { SchemaViewer } from "./schema-viewer";

export const dynamic = "force-dynamic";

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Characters</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Each character is a 3-file bundle (
            <code className="font-mono">behaviors/charNN.json</code> +{" "}
            <code className="font-mono">persona/charNN.json</code> +{" "}
            <code className="font-mono">images/charNN.json</code>) plus 2{" "}
            <code className="font-mono">.env</code> token lines (
            <code className="font-mono">CHAR_BOT_charNN</code> +{" "}
            <code className="font-mono">CHAR_USERNAME_charNN</code>). Bot
            restart required after add / edit / delete.
          </p>
        </div>
        <SchemaViewer />
      </div>
      <CharactersList />
    </div>
  );
}
