// Client-safe constants. Server module `workflows.ts` uses node:fs / node:path —
// import this file from client components instead.

export type WorkflowStage = "standard" | "hq";

export type WorkflowSummary = {
  name: string;            // basename, e.g. "main_character_build.json"
  size_bytes: number;
  mtime_ms: number;
  facts: WorkflowFacts;
  description: string;
  stage_badges: WorkflowStage[];
  assignable: boolean;     // false for *_archived files
};

export type WorkflowFacts = {
  node_count: number;
  sampler_steps_total: number;
  has_refiner_or_upscaler: boolean;
  size_bytes: number;
};

export type SafeFields = {
  checkpoint: string | null;
  ksampler: {
    seed: number;
    cfg: number;
    steps: number;
    sampler_name: string;
    scheduler: string;
  } | null;
  save_filename_prefix: string | null;
};

export type StageAssignments = {
  standard: string; // basename
  hq: string;       // basename
  options: string[];
};

// A workflow basename is "assignable" (eligible for stage selection) only if it
// is NOT an archived rollback snapshot.
export function isAssignableWorkflow(name: string): boolean {
  return name.endsWith(".json") && !name.includes("_archived");
}
