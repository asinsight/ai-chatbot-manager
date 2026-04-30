"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type LogFileInfo = {
  name: string;
  size_bytes: number;
  mtime_ms: number;
  is_current: boolean;
};

type FilesResp = { files: LogFileInfo[] };
type LinesResp = { lines?: string[]; note?: string; error?: string };

const TAIL_OPTIONS = [200, 500, 1000, 2000, 5000];
const INTERVAL_OPTIONS: { label: string; ms: number | null }[] = [
  { label: "1s", ms: 1000 },
  { label: "2s", ms: 2000 },
  { label: "5s", ms: 5000 },
  { label: "Paused", ms: null },
];

export function LogsPage() {
  const [files, setFiles] = useState<LogFileInfo[]>([]);
  const [activeFile, setActiveFile] = useState<string>("bot.log");
  const [tail, setTail] = useState<number>(1000);
  const [intervalMs, setIntervalMs] = useState<number | null>(1000);
  const [filter, setFilter] = useState("");
  const [debouncedFilter, setDebouncedFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [lines, setLines] = useState<string[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchAt, setLastFetchAt] = useState<number | null>(null);

  const preRef = useRef<HTMLPreElement | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedFilter(filter), 200);
    return () => clearTimeout(id);
  }, [filter]);

  const loadFiles = useCallback(async () => {
    try {
      const r = await fetch("/api/bot/logs?listFiles=1", { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as FilesResp;
      if (!mountedRef.current) return;
      setFiles(body.files);
      if (body.files.length > 0 && !body.files.some((f) => f.name === activeFile)) {
        setActiveFile(body.files[0].name);
      }
    } catch (err) {
      if (mountedRef.current) setError((err as Error).message);
    }
  }, [activeFile]);

  const fetchLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      params.set("tail", String(tail));
      if (activeFile) params.set("file", activeFile);
      const r = await fetch(`/api/bot/logs?${params.toString()}`, { cache: "no-store" });
      const body = (await r.json().catch(() => ({}))) as LinesResp;
      if (!r.ok) throw new Error(body.error ?? `status ${r.status}`);
      if (!mountedRef.current) return;
      setLines(body.lines ?? []);
      setNote(body.note ?? null);
      setError(null);
      setLastFetchAt(Date.now());
    } catch (err) {
      if (mountedRef.current) setError((err as Error).message);
    }
  }, [activeFile, tail]);

  useEffect(() => {
    mountedRef.current = true;
    void loadFiles();
    return () => {
      mountedRef.current = false;
    };
  }, [loadFiles]);

  useEffect(() => {
    void fetchLogs();
    if (intervalMs === null) return;
    const id = setInterval(() => void fetchLogs(), intervalMs);
    return () => clearInterval(id);
  }, [fetchLogs, intervalMs]);

  useEffect(() => {
    const id = setInterval(() => void loadFiles(), 30000);
    return () => clearInterval(id);
  }, [loadFiles]);

  const filterRe = useMemo<RegExp | null>(() => {
    if (debouncedFilter.trim() === "") return null;
    try {
      return new RegExp(debouncedFilter, "i");
    } catch {
      return null;
    }
  }, [debouncedFilter]);

  const filtered = useMemo(() => {
    if (!filterRe) return lines;
    return lines.filter((l) => filterRe.test(l));
  }, [lines, filterRe]);

  useEffect(() => {
    if (!autoScroll) return;
    const el = preRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [filtered, autoScroll]);

  const downloadHref = useMemo(() => {
    const params = new URLSearchParams();
    params.set("tail", "5000");
    if (activeFile) params.set("file", activeFile);
    return `/api/bot/logs?${params.toString()}`;
  }, [activeFile]);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 rounded-md border p-3 md:grid-cols-[200px_140px_140px_1fr_auto]">
        <div className="space-y-1">
          <Label className="text-xs">File</Label>
          <Select value={activeFile} onValueChange={setActiveFile}>
            <SelectTrigger className="text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {files.map((f) => (
                <SelectItem key={f.name} value={f.name}>
                  {f.name}
                  {f.is_current ? " (current)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Tail</Label>
          <Select value={String(tail)} onValueChange={(v) => setTail(parseInt(v, 10))}>
            <SelectTrigger className="text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TAIL_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Refresh</Label>
          <Select
            value={intervalMs === null ? "paused" : String(intervalMs)}
            onValueChange={(v) => setIntervalMs(v === "paused" ? null : parseInt(v, 10))}
          >
            <SelectTrigger className="text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INTERVAL_OPTIONS.map((opt) => (
                <SelectItem key={opt.label} value={opt.ms === null ? "paused" : String(opt.ms)}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Filter (regex, case-insensitive)</Label>
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="e.g. ERROR | char05 | ^2026-04"
            className="font-mono text-xs"
          />
        </div>
        <div className="flex items-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void fetchLogs()}
            title="Refresh now"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button asChild type="button" size="sm" variant="outline" title="Download">
            <a href={downloadHref} download={activeFile}>
              <Download className="h-4 w-4" />
            </a>
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-1">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
          <span>
            {filterRe ? `match: ${filtered.length}/${lines.length}` : `${lines.length} lines`}
          </span>
          {note && <span className="italic">{note}</span>}
          {error && <span className="text-destructive">{error}</span>}
        </div>
        <span>
          {lastFetchAt ? `fetched at ${new Date(lastFetchAt).toLocaleTimeString()}` : "—"}
          {" · "}
          {intervalMs === null ? "paused" : INTERVAL_OPTIONS.find((o) => o.ms === intervalMs)?.label}
        </span>
      </div>

      <pre
        ref={preRef}
        className="h-[75vh] overflow-auto rounded-md border bg-muted/20 p-3 font-mono text-[11px] leading-tight"
      >
        {filtered.length === 0 && (
          <span className="italic text-muted-foreground">
            {filterRe ? "(no matches)" : "(empty)"}
          </span>
        )}
        {filtered.map((line, i) => {
          if (!filterRe) return <div key={i}>{line || " "}</div>;
          return (
            <div key={i} className="bg-amber-500/5">
              {highlight(line, filterRe)}
            </div>
          );
        })}
      </pre>
    </div>
  );
}

function highlight(line: string, re: RegExp): React.ReactNode[] {
  if (line === "") return [<span key={0}>&nbsp;</span>];
  const flags = re.flags.includes("g") ? re.flags : re.flags + "g";
  const g = new RegExp(re.source, flags);
  const out: React.ReactNode[] = [];
  let last = 0;
  let i = 0;
  let m = g.exec(line);
  while (m !== null) {
    if (m.index > last) out.push(<span key={i++}>{line.slice(last, m.index)}</span>);
    out.push(
      <span key={i++} className="bg-amber-500/30 font-semibold">
        {m[0]}
      </span>,
    );
    last = m.index + m[0].length;
    if (m[0].length === 0) g.lastIndex += 1;
    m = g.exec(line);
  }
  if (last < line.length) out.push(<span key={i++}>{line.slice(last)}</span>);
  return out;
}
