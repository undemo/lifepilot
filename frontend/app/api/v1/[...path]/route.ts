import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8010";
const PROXY_TIMEOUT_MS = 120_000;
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade"
]);

type RouteContext = {
  params: {
    path?: string[];
  };
};

async function proxyApiRequest(request: Request, context: RouteContext) {
  const targetUrl = buildTargetUrl(request.url, context.params.path || []);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers: forwardHeaders(request.headers),
      body: hasRequestBody(request.method) ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: controller.signal
    });

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: forwardHeaders(response.headers)
    });
  } catch {
    const traceId = request.headers.get("x-trace-id");
    return NextResponse.json(
      {
        success: false,
        trace_id: traceId,
        data: null,
        error: {
          code: "INTERNAL_ERROR",
          message: "backend proxy request failed.",
          user_message: "系统暂时不可用，请稍后重试。",
          recoverable: true,
          details: {}
        }
      },
      {
        status: 504,
        headers: traceId ? { "X-Trace-Id": traceId } : undefined
      }
    );
  } finally {
    clearTimeout(timeout);
  }
}

function buildTargetUrl(sourceUrl: string, pathSegments: string[]) {
  const source = new URL(sourceUrl);
  const encodedPath = pathSegments.map((segment) => encodeURIComponent(segment)).join("/");
  const target = new URL(`/api/v1/${encodedPath}`, BACKEND_ORIGIN);
  target.search = source.search;
  return target;
}

function forwardHeaders(headers: Headers) {
  const forwarded = new Headers(headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    forwarded.delete(header);
  }
  return forwarded;
}

function hasRequestBody(method: string) {
  return method !== "GET" && method !== "HEAD";
}

export const GET = proxyApiRequest;
export const POST = proxyApiRequest;
export const PATCH = proxyApiRequest;
export const DELETE = proxyApiRequest;
