import { NextResponse } from "next/server";

import { listWorkflowsSummary } from "@/lib/workflows";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const workflows = await listWorkflowsSummary();
    return NextResponse.json({ workflows });
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "WORKFLOWS_LIST_FAILED" },
      { status: 500 },
    );
  }
}
