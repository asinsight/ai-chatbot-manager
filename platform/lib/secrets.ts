const SECRET_PATTERNS: RegExp[] = [
  /_API_KEY$/,
  /_BOT_TOKEN$/,
  /_API_TOKEN$/,
  /_SECRET$/,
  // Per-bot tokens follow the CHAR_BOT_<id> pattern (no _TOKEN suffix);
  // treat them as secrets too.
  /^CHAR_BOT_[A-Za-z0-9_]+$/,
];

export function isSecret(key: string): boolean {
  return SECRET_PATTERNS.some((re) => re.test(key));
}

export function maskValue(value: string): string {
  if (!value) return "";
  if (value.length <= 4) return "••••";
  return `••••••${value.slice(-4)}`;
}
