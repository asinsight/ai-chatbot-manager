const SECRET_PATTERNS: RegExp[] = [
  /_API_KEY$/,
  /_BOT_TOKEN$/,
  /_API_TOKEN$/,
  /_SECRET$/,
];

export function isSecret(key: string): boolean {
  return SECRET_PATTERNS.some((re) => re.test(key));
}

export function maskValue(value: string): string {
  if (!value) return "";
  if (value.length <= 4) return "••••";
  return `••••••${value.slice(-4)}`;
}
