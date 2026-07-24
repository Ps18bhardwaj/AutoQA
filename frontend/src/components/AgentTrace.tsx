import { useState } from "react";
import {
  Brain, MousePointerClick, Eye, ScanLine, Bug, AlertTriangle,
  ChevronDown, ChevronUp,
} from "lucide-react";
import type { TraceItem } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SeverityDot } from "./ReportView";

const META: Record<string, { icon: typeof Brain; label: string; color: string }> = {
  thought:     { icon: Brain,              label: "Thought",     color: "text-sky-500" },
  action:      { icon: MousePointerClick,  label: "Action",      color: "text-amber-500" },
  observation: { icon: Eye,                label: "Observation", color: "text-emerald-600" },
  screenshot:  { icon: ScanLine,           label: "Viewport",    color: "text-indigo-500" },
  page_check:  { icon: ScanLine,           label: "Page checks", color: "text-purple-500" },
  finding:     { icon: Bug,                label: "Finding",     color: "text-red-500" },
  error:       { icon: AlertTriangle,      label: "Error",       color: "text-red-500" },
};

const TOOL_COLORS: Record<string, string> = {
  navigate: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  click: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  type_text: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  submit: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  assert_visible: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  assert_text: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
};

function ToolBadge({ tool }: { tool: string }) {
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-xs font-mono font-medium",
      TOOL_COLORS[tool] ?? "bg-muted text-muted-foreground")}>{tool}</span>
  );
}

function ArgsDisplay({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args);
  if (!entries.length) return null;
  return (
    <span className="text-xs text-muted-foreground">
      {entries.map(([k, v], i) => (
        <span key={k}>
          {i > 0 && <span className="mx-1 text-border">·</span>}
          <span className="font-medium text-foreground/70">{k}=</span>
          <span className="font-mono">{String(v).slice(0, 80)}{String(v).length > 80 ? "…" : ""}</span>
        </span>
      ))}
    </span>
  );
}

const OBS_PREVIEW = 240;

function CollapsibleObs({ result, ok }: { result: string; ok?: boolean }) {
  const [open, setOpen] = useState(false);
  const bad = ok === false || result.startsWith("ERROR") || result.startsWith("ASSERTION FAILED");
  const preview = result.slice(0, OBS_PREVIEW);
  const hasMore = result.length > OBS_PREVIEW;
  return (
    <div className={cn("rounded-md p-2 text-xs",
      bad ? "border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400"
          : "border border-border bg-muted/40 text-muted-foreground")}>
      <pre className="whitespace-pre-wrap font-mono leading-relaxed">
        {open ? result : preview}{!open && hasMore && <span className="opacity-50">…</span>}
      </pre>
      {hasMore && (
        <button onClick={() => setOpen((o) => !o)}
          className="mt-1 flex items-center gap-1 text-[10px] text-sky-600 hover:underline dark:text-sky-400">
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {open ? "Show less" : "Show all"}
        </button>
      )}
    </div>
  );
}

function Body({ item }: { item: TraceItem }) {
  switch (item.kind) {
    case "thought":
      return <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{item.text}</p>;
    case "action":
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <ToolBadge tool={item.tool} />
          <ArgsDisplay args={item.args} />
        </div>
      );
    case "observation":
      return <CollapsibleObs result={item.result} ok={item.ok} />;
    case "screenshot":
      return <p className="truncate text-xs text-muted-foreground">{item.title || item.pageUrl}</p>;
    case "page_check":
      return (
        <p className="text-xs text-muted-foreground">
          {item.count} issue{item.count === 1 ? "" : "s"} found
          {item.preview.length > 0 && <>: {item.preview.slice(0, 3).join("; ")}</>}
        </p>
      );
    case "finding":
      return (
        <div className="flex items-start gap-1.5 text-sm">
          <SeverityDot severity={item.finding.severity} />
          <div>
            <span className="font-medium">{item.finding.title}</span>
            <span className="ml-1.5 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
              {item.finding.category}
            </span>
          </div>
        </div>
      );
    case "error":
      return <p className="text-sm text-red-600 dark:text-red-400">{item.message}</p>;
    default:
      return null;
  }
}

export function AgentTrace({ items }: { items: TraceItem[] }) {
  // Screenshots are shown live in the viewport panel, not the timeline.
  const visible = items.filter((i) => i.kind !== "status" && i.kind !== "screenshot");
  return (
    <ol className="space-y-3">
      {visible.map((item, i) => {
        const meta = META[item.kind] ?? META.thought;
        const Icon = meta.icon;
        return (
          <li key={i} className="flex gap-3">
            <div className="flex flex-col items-center">
              <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", meta.color)} />
              {i < visible.length - 1 && <div className="mt-1 w-px flex-1 bg-border" />}
            </div>
            <div className={cn("min-w-0 flex-1 rounded-lg border border-border px-3 py-2",
              item.kind === "error" && "border-red-200 bg-red-50/40 dark:border-red-800 dark:bg-red-950/20",
              item.kind === "finding" && "border-red-200/60 bg-red-50/20 dark:border-red-900/40")}>
              <p className={cn("mb-1 text-xs font-semibold", meta.color)}>{meta.label}</p>
              <Body item={item} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
