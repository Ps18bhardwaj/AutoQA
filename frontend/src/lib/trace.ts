import type { Finding, TraceItem } from "./api";

/**
 * Maps one backend SSE/stored event to a renderable trace item. Shared by the
 * live console (streaming) and run replay (reading persisted events), so the
 * timeline looks identical whether you're watching it happen or looking back.
 *
 * Returns null for events handled as state transitions by the caller:
 * `status` (phase label), `approval_required`/`paused` (pending approval),
 * `report` (flips to the report view), `done`.
 */
export function eventToTraceItem(event: string, data: any, ts: number): TraceItem | null {
  switch (event) {
    case "thought":
      return { kind: "thought", text: data.text, ts };
    case "action":
      return { kind: "action", tool: data.tool, args: data.args ?? {}, step: data.step, ts };
    case "observation":
      return {
        kind: "observation",
        tool: data.tool,
        result: data.result,
        ok: !(String(data.result).startsWith("ERROR") || String(data.result).startsWith("ASSERTION FAILED")),
        ts,
      };
    case "screenshot":
      return { kind: "screenshot", step: data.step, url: data.url, pageUrl: data.page_url, title: data.title, ts };
    case "page_check":
      return { kind: "page_check", checkKind: data.kind, pageUrl: data.page_url, count: data.count, preview: data.preview ?? [], ts };
    case "finding":
      return { kind: "finding", finding: data as Finding, ts };
    case "error":
      return { kind: "error", message: data.message, ts };
    default:
      return null;
  }
}
