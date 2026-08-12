import { NextResponse } from "next/server";

/**
 * Thin proxy to the verification engine in `email_detection/`.
 *
 * The engine's CORS config already allows localhost:3000, so the browser could
 * call it directly. Going through a route handler instead means the engine's
 * address is a server-side setting rather than something baked into the client
 * bundle, and deploying the UI somewhere other than localhost needs no CORS
 * change on the Python side.
 *
 * Start the engine with:
 *   cd email_detection && uvicorn api.main:app --reload
 */

const ENGINE_URL = (process.env.PHISHERMANAI_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

/**
 * Long enough for a cold screenshot path (~3 s) against a local engine, and for
 * a sleeping free-tier Render instance to wake -- measured at ~50 s.
 *
 * 30 s was not. The first request after ~15 minutes idle aborted mid-boot and
 * surfaced as `engine_unreachable`, which tells the user to go start a server
 * that is in fact already starting.
 */
const TIMEOUT_MS = 90_000;

type Context = { params: Promise<{ path: string[] }> };

function unreachable(detail: string) {
  // 503 rather than 500: the UI distinguishes "engine is not running" from
  // "engine ran and failed", and tells the user how to start it.
  return NextResponse.json(
    {
      detail,
      engine_unreachable: true,
      engine_url: ENGINE_URL,
      hint: "Start it with: cd email_detection && uvicorn api.main:app --reload",
    },
    { status: 503 },
  );
}

async function proxy(request: Request, context: Context): Promise<Response> {
  const { path } = await context.params;
  const search = new URL(request.url).search;
  const target = `${ENGINE_URL}/${path.join("/")}${search}`;

  const init: RequestInit = {
    method: request.method,
    signal: AbortSignal.timeout(TIMEOUT_MS),
    // Forward the body untouched so multipart uploads (.eml, images, PDFs)
    // arrive with their boundaries intact.
    body: request.method === "GET" ? undefined : await request.arrayBuffer(),
    headers: (() => {
      const headers = new Headers();
      const contentType = request.headers.get("content-type");
      if (contentType) headers.set("content-type", contentType);
      return headers;
    })(),
  };

  let response: Response;
  try {
    response = await fetch(target, init);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return unreachable(`Could not reach the verification engine at ${ENGINE_URL}: ${reason}`);
  }

  // Pass the payload through as-is: JSON verdicts and the warning-card PNG
  // both go through this path, so nothing is parsed or re-encoded here.
  const body = await response.arrayBuffer();
  return new Response(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

export async function GET(request: Request, context: Context) {
  return proxy(request, context);
}

export async function POST(request: Request, context: Context) {
  return proxy(request, context);
}
