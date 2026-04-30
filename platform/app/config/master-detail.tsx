"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export function MasterDetail({
  keys,
  selected,
  onSelect,
  onAdd,
  onDelete,
  itemLabel,
  newKeyHint,
  newKeyValidator,
  protectedKeys = [],
  renderRow,
  children,
}: {
  keys: string[];
  selected: string | null;
  onSelect: (key: string) => void;
  onAdd: (newKey: string) => void;
  onDelete: (key: string) => void;
  itemLabel: string;
  newKeyHint?: string;
  newKeyValidator?: (k: string, existing: string[]) => string | null;
  protectedKeys?: string[];
  renderRow?: (key: string) => React.ReactNode;
  children: React.ReactNode;
}) {
  const [newKey, setNewKey] = useState("");
  const [newKeyError, setNewKeyError] = useState<string | null>(null);

  const tryAdd = () => {
    const k = newKey.trim();
    if (!k) return;
    if (keys.includes(k)) {
      setNewKeyError(`'${k}' already exists`);
      return;
    }
    const validateError = newKeyValidator?.(k, keys) ?? null;
    if (validateError) {
      setNewKeyError(validateError);
      return;
    }
    onAdd(k);
    setNewKey("");
    setNewKeyError(null);
  };

  return (
    <div className="grid grid-cols-[280px_1fr] gap-4">
      <div className="rounded-md border">
        <div className="border-b p-2">
          <Input
            value={newKey}
            placeholder={newKeyHint ?? `New ${itemLabel} key`}
            onChange={(e) => {
              setNewKey(e.target.value);
              setNewKeyError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                tryAdd();
              }
            }}
            className="font-mono text-xs"
          />
          {newKeyError && (
            <p className="mt-1 text-xs text-destructive">{newKeyError}</p>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="mt-2 w-full"
            onClick={tryAdd}
          >
            <Plus /> Add {itemLabel}
          </Button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          {keys.length === 0 && (
            <p className="p-3 text-xs italic text-muted-foreground">
              (empty — add a {itemLabel} above)
            </p>
          )}
          {keys.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => onSelect(k)}
              className={`flex w-full items-start justify-between border-b px-3 py-2 text-left text-xs hover:bg-muted/40 ${
                selected === k ? "bg-muted" : ""
              }`}
            >
              <div className="min-w-0 flex-1 truncate font-mono">
                {renderRow ? renderRow(k) : k}
              </div>
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-3">
        {selected && (
          <div className="flex items-center justify-between border-b pb-2">
            <code className="font-mono text-sm font-semibold">{selected}</code>
            {!protectedKeys.includes(selected) && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button type="button" size="sm" variant="ghost">
                    <Trash2 className="h-4 w-4" /> Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete {selected}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      The entry will be removed when you Save the file. A
                      backup of the previous content is written automatically.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => onDelete(selected)}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        )}
        {selected ? children : (
          <p className="text-sm italic text-muted-foreground">
            Select a {itemLabel} from the list to edit.
          </p>
        )}
      </div>
    </div>
  );
}
