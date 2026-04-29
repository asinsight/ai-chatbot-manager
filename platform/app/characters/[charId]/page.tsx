import { CharacterEditor } from "./character-editor";

export const dynamic = "force-dynamic";

export default function Page({ params }: { params: { charId: string } }) {
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <CharacterEditor charId={params.charId} />
    </div>
  );
}
