import { NextRequest, NextResponse } from "next/server";

import {
  CONFIG_FILE_KEYS,
  type ConfigFileKey,
  backupConfigFile,
  readConfigFile,
  writeConfigFileAtomic,
} from "@/lib/config-files";
import {
  validatePoseMotionPresets,
  validateProfileKeys,
  validateSfwDenylist,
  validateSfwScenes,
} from "@/lib/config-schemas";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isKnownFileKey(key: string): key is ConfigFileKey {
  return (CONFIG_FILE_KEYS as string[]).includes(key);
}

type RouteCtx = { params: { fileKey: string } };

export async function GET(_req: NextRequest, { params }: RouteCtx) {
  const { fileKey } = params;
  if (!isKnownFileKey(fileKey)) {
    return NextResponse.json(
      { error: `unknown config file: ${fileKey}`, code: "UNKNOWN_FILE_KEY" },
      { status: 404 },
    );
  }
  try {
    const payload = await readConfigFile(fileKey);
    return NextResponse.json(payload);
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "CONFIG_READ_FAILED" },
      { status: 500 },
    );
  }
}

type PutBody = { content?: unknown };

export async function PUT(req: NextRequest, { params }: RouteCtx) {
  const { fileKey } = params;
  if (!isKnownFileKey(fileKey)) {
    return NextResponse.json(
      { error: `unknown config file: ${fileKey}`, code: "UNKNOWN_FILE_KEY" },
      { status: 404 },
    );
  }
  let body: PutBody;
  try {
    body = (await req.json()) as PutBody;
  } catch {
    return NextResponse.json(
      { error: "invalid JSON body", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  if (body.content === undefined) {
    return NextResponse.json(
      { error: "missing `content` field", code: "BAD_REQUEST" },
      { status: 400 },
    );
  }
  const content = body.content;

  // Per-file shape validation.
  switch (fileKey) {
    case "sfw_scenes": {
      const r = validateSfwScenes(content);
      if (!r.ok) {
        return NextResponse.json(
          { error: r.errors.join("; "), code: "INVALID_SHAPE", details: r.errors },
          { status: 422 },
        );
      }
      break;
    }
    case "pose_motion_presets": {
      const r = validatePoseMotionPresets(content);
      if (!r.ok) {
        const code = r.errors.some((e) => e.includes("missing required `generic`"))
          ? "MISSING_GENERIC"
          : "INVALID_SHAPE";
        return NextResponse.json(
          { error: r.errors.join("; "), code, details: r.errors },
          { status: 422 },
        );
      }
      break;
    }
    case "sfw_denylist": {
      const r = validateSfwDenylist(content);
      if (!r.ok) {
        return NextResponse.json(
          { error: r.errors.join("; "), code: "INVALID_SHAPE", details: r.errors },
          { status: 422 },
        );
      }
      break;
    }
    case "profile_keys": {
      const r = validateProfileKeys(content);
      if (!r.ok) {
        return NextResponse.json(
          { error: r.errors.join("; "), code: "INVALID_SHAPE", details: r.errors },
          { status: 422 },
        );
      }
      break;
    }
  }

  let backupPath: string;
  try {
    backupPath = await backupConfigFile(fileKey);
    await writeConfigFileAtomic(fileKey, content);
  } catch (err) {
    const e = err as Error;
    return NextResponse.json(
      { error: e.message, code: "SAVE_FAILED" },
      { status: 500 },
    );
  }

  return NextResponse.json({
    ok: true,
    restart_required: true,
    backup_path: backupPath,
  });
}
