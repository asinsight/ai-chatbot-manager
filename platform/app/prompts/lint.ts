// Client-safe placeholder lint — mirror of lib/prompts.ts's lintPlaceholders.
// Kept separate because lib/prompts.ts imports node:fs and can't ship to the client.

export type LintIssue = {
  severity: "warning" | "error";
  message: string;
  line?: number;
};

export function lintPlaceholders(value: string): LintIssue[] {
  const issues: LintIssue[] = [];
  const lines = value.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    let cursor = 0;
    while (true) {
      const open = ln.indexOf("${", cursor);
      if (open < 0) break;
      const close = ln.indexOf("}", open);
      if (close < 0) {
        issues.push({
          severity: "warning",
          line: i + 1,
          message: `unterminated placeholder near \`${ln.slice(open, open + 20)}…\``,
        });
        break;
      }
      const inner = ln.slice(open + 2, close);
      if (inner.trim() === "") {
        issues.push({ severity: "warning", line: i + 1, message: "empty placeholder `${}`" });
      } else if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(inner)) {
        issues.push({
          severity: "warning",
          line: i + 1,
          message: `placeholder \`\${${inner}}\` has unusual characters`,
        });
      }
      cursor = close + 1;
    }
  }
  if (/\$\s+\{/.test(value)) {
    issues.push({
      severity: "warning",
      message: "found `$ {...}` (space between $ and {) — likely a typo",
    });
  }
  return issues;
}
