export type EnvLine =
  | { kind: "blank" }
  | { kind: "comment"; raw: string }
  | {
      kind: "var";
      key: string;
      value: string;
      quoted: '"' | "'" | null;
      trailingComment: string | null;
    }
  | { kind: "comment-var"; key: string; value: string; raw: string };

const KEY_RE = /^[A-Z_][A-Z0-9_]*$/;

function parseLine(raw: string): EnvLine {
  if (raw.trim() === "") return { kind: "blank" };

  // commented-out var: leading '#' immediately followed by KEY=...
  const commentedVarMatch = raw.match(/^#\s*([A-Z_][A-Z0-9_]*)\s*=(.*)$/);
  if (commentedVarMatch) {
    return {
      kind: "comment-var",
      key: commentedVarMatch[1],
      value: commentedVarMatch[2].trim(),
      raw,
    };
  }

  if (raw.trimStart().startsWith("#")) {
    return { kind: "comment", raw };
  }

  const eq = raw.indexOf("=");
  if (eq <= 0) return { kind: "comment", raw };

  const key = raw.slice(0, eq).trim();
  if (!KEY_RE.test(key)) return { kind: "comment", raw };

  let rest = raw.slice(eq + 1);

  // strip trailing comment (only if not inside quotes)
  let value = "";
  let quoted: '"' | "'" | null = null;
  let trailingComment: string | null = null;

  rest = rest.replace(/^\s+/, "");

  if (rest.startsWith('"') || rest.startsWith("'")) {
    const q = rest[0] as '"' | "'";
    const closeIdx = rest.indexOf(q, 1);
    if (closeIdx > 0) {
      value = rest.slice(1, closeIdx);
      quoted = q;
      const after = rest.slice(closeIdx + 1).trim();
      if (after.startsWith("#")) trailingComment = after;
    } else {
      value = rest.slice(1);
    }
  } else {
    // unquoted — split on first ' #' for trailing comment
    const hashMatch = rest.match(/\s+#.*$/);
    if (hashMatch) {
      trailingComment = hashMatch[0].trimStart();
      value = rest.slice(0, hashMatch.index).trimEnd();
    } else {
      value = rest.trimEnd();
    }
  }

  return { kind: "var", key, value, quoted, trailingComment };
}

export function parseEnv(text: string): EnvLine[] {
  const result: EnvLine[] = [];
  for (const raw of text.split(/\r?\n/)) {
    result.push(parseLine(raw));
  }
  // trailing newline produces a final empty token; drop it for round-trip cleanliness
  if (
    result.length > 0 &&
    result[result.length - 1].kind === "blank" &&
    text.endsWith("\n")
  ) {
    result.pop();
  }
  return result;
}

function quoteIfNeeded(value: string, prevQuoted: '"' | "'" | null): {
  serialized: string;
  quoted: '"' | "'" | null;
} {
  if (prevQuoted === '"' || prevQuoted === "'") {
    const escaped = value.replace(
      new RegExp(prevQuoted, "g"),
      `\\${prevQuoted}`,
    );
    return { serialized: `${prevQuoted}${escaped}${prevQuoted}`, quoted: prevQuoted };
  }
  // No prior quoting — only quote if value has whitespace, '#', or starts with quote.
  if (/[\s#]/.test(value) || value.startsWith('"') || value.startsWith("'")) {
    return { serialized: `"${value.replace(/"/g, '\\"')}"`, quoted: '"' };
  }
  return { serialized: value, quoted: null };
}

function serializeLine(line: EnvLine): string {
  switch (line.kind) {
    case "blank":
      return "";
    case "comment":
      return line.raw;
    case "comment-var":
      return line.raw;
    case "var": {
      const { serialized } = quoteIfNeeded(line.value, line.quoted);
      const trailing = line.trailingComment ? `  ${line.trailingComment}` : "";
      return `${line.key}=${serialized}${trailing}`;
    }
  }
}

export function serializeEnv(lines: EnvLine[]): string {
  return lines.map(serializeLine).join("\n") + "\n";
}

export function applyUpdates(
  lines: EnvLine[],
  updates: Record<string, string>,
): EnvLine[] {
  const remaining = new Map(Object.entries(updates));
  const result = lines.map((line): EnvLine => {
    if (line.kind === "var" && remaining.has(line.key)) {
      const newValue = remaining.get(line.key)!;
      remaining.delete(line.key);
      return { ...line, value: newValue };
    }
    if (line.kind === "comment-var" && remaining.has(line.key)) {
      const newValue = remaining.get(line.key)!;
      remaining.delete(line.key);
      const promoted: EnvLine = {
        kind: "var",
        key: line.key,
        value: newValue,
        quoted: null,
        trailingComment: null,
      };
      return promoted;
    }
    return line;
  });

  // append leftover keys at the end
  for (const [key, value] of remaining) {
    if (!KEY_RE.test(key)) {
      throw new Error(`invalid env key: ${key}`);
    }
    result.push({
      kind: "var",
      key,
      value,
      quoted: null,
      trailingComment: null,
    });
  }
  return result;
}

/**
 * Extract the contiguous block of `# ...` comment lines immediately above each
 * KEY=... line in the .env.example. Used as inline help in the env editor.
 */
export function parseExampleComments(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  const rawLines = text.split(/\r?\n/);
  let buffer: string[] = [];
  for (const raw of rawLines) {
    const trimmed = raw.trim();
    if (trimmed === "" || /^#\s*═+\s*$/.test(trimmed)) {
      buffer = [];
      continue;
    }
    // Commented-out variable (e.g. `#GROK_BASE_URL=...`) — not human help itself,
    // but the buffer above it documents this very key.
    const commentedKey = trimmed.match(/^#\s*([A-Z_][A-Z0-9_]*)\s*=/);
    if (commentedKey) {
      if (buffer.length > 0) {
        out[commentedKey[1]] = buffer.join(" ").trim();
      }
      buffer = [];
      continue;
    }
    if (trimmed.startsWith("#")) {
      buffer.push(trimmed.replace(/^#\s?/, ""));
      continue;
    }
    const m = raw.match(/^([A-Z_][A-Z0-9_]*)\s*=/);
    if (m) {
      const key = m[1];
      if (buffer.length > 0) {
        out[key] = buffer.join(" ").trim();
      }
      buffer = [];
    } else {
      buffer = [];
    }
  }
  return out;
}
