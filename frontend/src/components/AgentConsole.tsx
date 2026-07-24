import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, RotateCcw, Square } from "lucide-react";
import { toast } from "sonner";
import {
  runQA, resumeQA, getRun,
  type PendingAction, type Report, type StreamHandlers, type TraceItem,
} from "@/lib/api";
import { eventToTraceItem } from "@/lib/trace";
import { useStore } from "@/store";
import { Button } from "@/components/ui/button";
import { AgentTrace } from "./AgentTrace";
import { AgentViewport, type ViewportFrame } from "./AgentViewport";
import { ApprovalModal } from "./ApprovalModal";
import { ReportView } from "./ReportView";
import { ScenarioForm, type ScenarioValues } from "./ScenarioForm";

type RunState = "idle" | "running" | "awaiting" | "done";

export function AgentConsole() {
  const qc = useQueryClient();
  const [trace, setTrace] = useState<TraceItem[]>([]);
  const [state, setState] = useState<RunState>("idle");
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [phase, setPhase] = useState("");
  const [frame, setFrame] = useState<ViewportFrame | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [stepInfo, setStepInfo] = useState<{ step: number; max: number } | null>(null);

  const showDebug = useStore((s) => s.showDebug);
  const [debugLog, setDebugLog] = useState<string[]>([]);
  const runIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastRunRef = useRef<ScenarioValues | null>(null);

  const viewingRunId = useStore((s) => s.viewingRunId);
  const setViewingRunId = useStore((s) => s.setViewingRunId);
  const { data: viewedRun, isLoading: viewedLoading } = useQuery({
    queryKey: ["run", viewingRunId],
    queryFn: () => getRun(viewingRunId!),
    enabled: !!viewingRunId,
  });
  const replay = useMemo(() => {
    if (!viewedRun) return { trace: [] as TraceItem[], report: null as Report | null, frame: null as ViewportFrame | null };
    const items: TraceItem[] = [];
    let rep: Report | null = null;
    let frm: ViewportFrame | null = null;
    for (const e of viewedRun.events) {
      const ts = new Date(e.ts).getTime();
      if (e.event === "report") rep = e.data as Report;
      if (e.event === "screenshot") frm = { url: e.data.url, pageUrl: e.data.page_url, title: e.data.title, step: e.data.step };
      const item = eventToTraceItem(e.event, e.data, ts);
      if (item) items.push(item);
    }
    return { trace: items, report: rep, frame: frm };
  }, [viewedRun]);

  const push = (item: TraceItem) => setTrace((t) => [...t, item]);
  const log = (m: string) => setDebugLog((l) => [...l.slice(-199), `${new Date().toLocaleTimeString()} ${m}`]);

  const handlers: StreamHandlers = {
    onEvent: (event, data) => {
      const ts = Date.now();
      log(`← ${event} ${JSON.stringify(data).slice(0, 120)}`);
      const item = eventToTraceItem(event, data, ts);
      if (item) push(item);
      switch (event) {
        case "status":
          if (data.run_id) runIdRef.current = data.run_id;
          setPhase(data.phase ?? "");
          break;
        case "screenshot":
          setFrame({ url: data.url, pageUrl: data.page_url, title: data.title, step: data.step });
          setStepInfo((si) => ({ step: data.step, max: si?.max ?? 12 }));
          break;
        case "action":
          if (data.step !== undefined) setStepInfo((si) => ({ step: data.step, max: si?.max ?? 12 }));
          break;
        case "approval_required":
          setPending({
            tool: data.tool, args: data.args ?? {}, thought: data.thought,
            step: data.step, maxSteps: data.max_steps, pageUrl: data.page_url,
            screenshotUrl: data.screenshot_url, argsHint: data.args_hint, schema: data.schema,
          });
          break;
        case "paused":
          runIdRef.current = data.run_id;
          setState("awaiting");
          setPhase("Waiting for your approval…");
          qc.invalidateQueries({ queryKey: ["runs"] });
          break;
        case "report":
          setReport(data as Report);
          break;
        case "done":
          setState("done");
          setPhase("");
          qc.invalidateQueries({ queryKey: ["runs"] });
          break;
        case "error":
          setState("done");
          setPhase("");
          toast.error(data.message);
          qc.invalidateQueries({ queryKey: ["runs"] });
          break;
      }
    },
    onError: (err) => {
      push({ kind: "error", message: err.message, ts: Date.now() });
      toast.error(err.message);
      setState("done");
      setPhase("");
    },
  };

  async function start(values: ScenarioValues) {
    setViewingRunId(null);
    lastRunRef.current = values;
    setTrace([]); setDebugLog([]); setPending(null); setReport(null); setFrame(null);
    runIdRef.current = null;
    setState("running");
    setPhase("Starting…");
    setStepInfo({ step: 0, max: values.maxSteps });
    abortRef.current = new AbortController();
    log(`→ /run url=${values.url}`);
    await runQA(values.url, values.scenario, values.maxSteps, handlers, abortRef.current.signal);
  }

  async function decide(approved: boolean, editedArgs: Record<string, unknown> | null) {
    setPending(null);
    setState("running");
    setPhase("Resuming…");
    const rid = runIdRef.current;
    if (!rid) return;
    toast(approved ? "Submission approved — resuming" : "Submission rejected");
    abortRef.current = new AbortController();
    await resumeQA(rid, approved, editedArgs, handlers, abortRef.current.signal);
  }

  const busy = state === "running";

  // ---- replay view ----
  if (viewingRunId) {
    return (
      <main className="flex h-full min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-6 py-2.5">
          <Button variant="ghost" size="sm" onClick={() => setViewingRunId(null)}>
            <ArrowLeft className="h-3.5 w-3.5" /> Back to live console
          </Button>
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            Past run: <span className="text-foreground">{viewedRun?.scenario}</span>
          </span>
          {viewedRun && (
            <Button size="sm" variant="outline"
              onClick={() => start({ url: viewedRun.url, scenario: viewedRun.scenario, maxSteps: 12 })}>
              <RotateCcw className="h-3.5 w-3.5" /> Re-run
            </Button>
          )}
        </div>
        <div className="flex min-h-0 flex-1">
          <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
            {viewedLoading ? (
              <p className="mt-12 text-center text-sm text-muted-foreground">Loading run…</p>
            ) : replay.report ? (
              <ReportView report={replay.report} />
            ) : (
              <AgentTrace items={replay.trace} />
            )}
          </div>
          <div className="hidden w-[42%] lg:block">
            <AgentViewport frame={replay.frame} />
          </div>
        </div>
      </main>
    );
  }

  // ---- idle: scenario form ----
  if (state === "idle") {
    return (
      <main className="flex h-full min-w-0 flex-1 flex-col overflow-y-auto">
        <ScenarioForm onRun={start} />
      </main>
    );
  }

  // ---- done: report ----
  if (state === "done" && report) {
    return (
      <main className="flex h-full min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-6 py-2.5">
          <span className="text-sm font-medium">Report</span>
          <Button className="ml-auto" size="sm" variant="outline"
            onClick={() => { setState("idle"); setReport(null); setTrace([]); setFrame(null); }}>
            <RotateCcw className="h-3.5 w-3.5" /> New test
          </Button>
        </div>
        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          <ReportView report={report} />
        </div>
      </main>
    );
  }

  // ---- running / awaiting: viewport + trace ----
  return (
    <main className="flex h-full min-w-0 flex-1 flex-col">
      {showDebug && (
        <div className="max-h-32 overflow-y-auto border-b border-border bg-black/90 px-3 py-2">
          {debugLog.map((l, i) => (
            <p key={i} className="font-mono text-[10px] text-green-300/80">{l}</p>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2 border-b border-border px-6 py-2 text-xs text-muted-foreground">
        <span className="truncate">{lastRunRef.current?.scenario}</span>
        {busy ? (
          <Button className="ml-auto" variant="outline" size="sm" onClick={() => abortRef.current?.abort()}>
            <Square className="h-3.5 w-3.5" /> Stop
          </Button>
        ) : (
          // The run finished without a report (stopped or errored) — offer a way
          // back to the form instead of stranding the user on the trace.
          <Button className="ml-auto" variant="outline" size="sm"
            onClick={() => { setState("idle"); setReport(null); setTrace([]); setFrame(null); }}>
            <RotateCcw className="h-3.5 w-3.5" /> New test
          </Button>
        )}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          <AgentTrace items={trace} />
        </div>
        <div className="hidden w-[42%] lg:block">
          <AgentViewport frame={frame} />
        </div>
      </div>

      {busy && phase && (
        <div className="border-t border-border bg-muted/30">
          {stepInfo && (
            <div className="h-0.5 w-full bg-border">
              <div className="h-full bg-primary transition-[width]"
                style={{ width: `${Math.min(100, (stepInfo.step / stepInfo.max) * 100)}%` }} />
            </div>
          )}
          <div className="flex items-center gap-2 px-6 py-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{phase}</span>
            {stepInfo && (
              <span className="ml-1 text-xs text-muted-foreground/60">
                (step {stepInfo.step}/{stepInfo.max})
              </span>
            )}
          </div>
        </div>
      )}

      {pending && state === "awaiting" && <ApprovalModal action={pending} onDecision={decide} />}
    </main>
  );
}
