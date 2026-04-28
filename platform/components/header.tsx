export function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-6">
      <div className="text-sm text-muted-foreground">Local admin · 127.0.0.1:9000</div>
      <div className="text-xs text-muted-foreground">M0</div>
    </header>
  );
}
