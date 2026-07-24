// Typed client for the AutoQA backend. In dev, Vite proxies /api -> :8003
// (and /runs -> :8003 for the streamed screenshots).
const BASE = import.meta.env.VITE_API_BASE ?? "/api";
// Screenshot URLs from the backend are root-relative ("/runs/<id>/step_N.png").
// In dev the Vite proxy handles /runs; in prod set VITE_API_ORIGIN to the
// backend origin so <img> can load them cross-origin.
const API_ORIGIN = import.meta.env.VITE_API_ORIGIN ?? "";

export function screenshotSrc(url: string | undefined | null): string {
  if (!url) return "";
  return `${API_ORIGIN}${url}`;
}

// ---- report/finding shapes (mirror backend app/report.py) -----------------
export type Severity = "critical" | "major" | "minor" | "info";
export type Category = "functional" | "console" | "network" | "broken-link" | "a11y" | "blocked";
export type Verdict = "pass" | "fail" | "blocked";

export interface Evidence {
  screenshot_url: string | null;
  boxed: boolean;
  element: string | null;
}

export interface Finding {
  id: string;
  severity: Severity;
  category: Category;
  title: string;
  expected: string;
  actual: string;
  page_url: string;
  repro_steps: string[];
  evidence: Evidence | null;
}

export interface ActionLogEntry {
  step: number;
  thought: string;
  tool: string;
  args: Record<string, unknown>;
  observation: string;
  page_url: string;
  ok: boolean;
}

export interface Report {
  scenario: string;
  start_url: string;
  verdict: Verdict;
  summary: string;
  findings: Finding[];
  action_log: ActionLogEntry[];
  stats: {
    steps: number;
    actions_ok: number;
    actions_error: number;
    pages_visited: number;
    findings_by_category: Record<string, number>;
    duration_s: number;
  };
}

export interface PendingAction {
  tool: string;
  args: Record<string, unknown>;
  thought?: string;
  step?: number;
  maxSteps?: number;
  pageUrl?: string | null;
  screenshotUrl?: string | null;
  argsHint?: string | null;
  schema?: { properties?: Record<string, any>; required?: string[] } | null;
}

// One agent-trace entry rendered in the timeline.
export type TraceItem =
  | { kind: "thought"; text: string; ts: number }
  | { kind: "action"; tool: string; args: Record<string, unknown>; step?: number; ts: number }
  | { kind: "observation"; tool: string; result: string; ok?: boolean; ts: number }
  | { kind: "screenshot"; step: number; url: string; pageUrl: string; title: string; ts: number }
  | { kind: "page_check"; checkKind: string; pageUrl: string; count: number; preview: string[]; ts: number }
  | { kind: "finding"; finding: Finding; ts: number }
  | { kind: "error"; message: string; ts: number }
  | { kind: "status"; phase: string };

export interface StreamHandlers {
  onEvent: (event: string, data: any) => void;
  onError?: (err: Error) => void;
}

// Shared SSE-over-POST reader (EventSource can't POST a body).
async function readSSE(
  path: string,
  body: unknown,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() ?? "";
      for (const frame of frames) {
        const ev = /event:\s*(.*)/.exec(frame)?.[1]?.trim();
        const dataLine = /data:\s*([\s\S]*)/.exec(frame)?.[1];
        if (!ev || dataLine == null) continue;
        handlers.onEvent(ev, JSON.parse(dataLine));
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") handlers.onError?.(err as Error);
  }
}

export function runQA(
  url: string,
  scenario: string,
  maxSteps: number,
  handlers: StreamHandlers,
  signal?: AbortSignal
) {
  return readSSE("/run", { url, scenario, max_steps: maxSteps }, handlers, signal);
}

export function resumeQA(
  runId: string,
  approved: boolean,
  editedArgs: Record<string, unknown> | null,
  handlers: StreamHandlers,
  signal?: AbortSignal
) {
  return readSSE("/resume", { run_id: runId, approved, edited_args: editedArgs }, handlers, signal);
}

// ---- run history ----------------------------------------------------------
export type RunStatus = "running" | "paused" | "done" | "error" | "stopped";

export interface RunSummary {
  id: string;
  scenario: string;
  url: string;
  status: RunStatus;
  created_at: string;
  elapsed_s: number | null;
  verdict: Verdict | null;
  findings_count: number | null;
}

export interface RunEvent {
  event: string;
  data: any;
  ts: string;
}

export interface RunDetail extends RunSummary {
  events: RunEvent[];
}

export async function listRuns(limit = 50): Promise<RunSummary[]> {
  const res = await fetch(`${BASE}/history?limit=${limit}`);
  if (!res.ok) throw new Error(`history failed (${res.status})`);
  return res.json();
}

export async function getRun(id: string): Promise<RunDetail> {
  const res = await fetch(`${BASE}/history/${id}`);
  if (!res.ok) throw new Error(`run fetch failed (${res.status})`);
  return res.json();
}

export async function deleteRun(id: string): Promise<void> {
  const res = await fetch(`${BASE}/history/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`run delete failed (${res.status})`);
}

export async function health(): Promise<{ browser_ok: boolean; vision_model?: string }> {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}
