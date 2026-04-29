import Ajv2020 from "ajv/dist/2020";
import type { ValidateFunction } from "ajv";
import fs from "node:fs";
import path from "node:path";

import { REPO_ROOT } from "./paths";

// character_card_schema.json declares draft-2020-12; use Ajv2020.
const _ajv = new Ajv2020({ allErrors: true, strict: false });

let _personaValidator: ValidateFunction | null = null;

function loadSchema(name: string): object {
  const p = path.join(REPO_ROOT, name);
  const text = fs.readFileSync(p, "utf8");
  return JSON.parse(text) as object;
}

export function getPersonaValidator(): ValidateFunction {
  if (!_personaValidator) {
    _personaValidator = _ajv.compile(loadSchema("character_card_schema.json"));
  }
  return _personaValidator;
}

export type ValidationIssue = {
  path: string;
  message: string;
};

export function validatePersona(card: unknown): ValidationIssue[] {
  const validate = getPersonaValidator();
  const ok = validate(card);
  if (ok) return [];
  return (validate.errors ?? []).map((e) => ({
    path: e.instancePath || "/",
    message: e.message ?? "validation error",
  }));
}
