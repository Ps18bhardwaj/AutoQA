import { CheckCircle2, XCircle, ShieldOff, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import type { Report, Severity, Verdict } from "@/lib/api";
import { screenshotSrc } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "bg-red-600",
  major: "bg-orange-500",
  minor: "bg-amber-500",
  info: "bg-slate-400",
};

export function SeverityDot({ severity }: { severity: Severity }) {
  return <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", SEVERITY_COLOR[severity])} />;
}

const VERDICT_META: Record<Verdict, { icon: typeof CheckCircle2; label: string; cls: string }> = {
  pass: { icon: CheckCircle2, label: "PASS", cls: "text-emerald-600 border-emerald-500/40 bg-emerald-50/60 dark:bg-emerald-950/20" },
  fail: { icon: XCircle, label: "FAIL", cls: "text-red-600 border-red-500/40 bg-red-50/60 dark:bg-red-950/20" },
  blocked: { icon: ShieldOff, label: "BLOCKED", cls: "text-amber-600 border-amber-500/40 bg-amber-50/60 dark:bg-amber-950/20" },
};

function FindingCard({ f }: { f: Report["findings"][number] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border">
      <button onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-2 px-3 py-2 text-left">
        <SeverityDot severity={f.severity} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{f.title}</p>
          <p className="text-xs text-muted-foreground">
            <span className="rounded bg-muted px-1 py-0.5">{f.category}</span>
            <span className="ml-1.5">{f.severity}</span>
          </p>
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-3 py-2 text-xs">
          <p><span className="font-semibold text-muted-foreground">Expected:</span> {f.expected}</p>
          <p><span className="font-semibold text-muted-foreground">Actual:</span> {f.actual}</p>
          {f.repro_steps.length > 0 && (
            <div>
              <p className="font-semibold text-muted-foreground">Steps to reproduce:</p>
              <ol className="ml-4 list-decimal text-muted-foreground">
                {f.repro_steps.map((s, i) => <li key={i}>{s}</li>)}
              </ol>
            </div>
          )}
          {f.evidence?.screenshot_url && (
            <div>
              <p className="mb-1 font-semibold text-muted-foreground">
                Evidence{f.evidence.boxed && " (failing element boxed)"}:
              </p>
              <img src={screenshotSrc(f.evidence.screenshot_url)} alt="evidence"
                className="max-h-64 rounded border border-border" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ReportView({ report }: { report: Report }) {
  const v = VERDICT_META[report.verdict];
  const Icon = v.icon;
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className={cn("flex items-center gap-3 rounded-lg border px-4 py-3", v.cls)}>
        <Icon className="h-7 w-7 shrink-0" />
        <div className="min-w-0">
          <p className="text-lg font-bold">{v.label}</p>
          <p className="text-sm opacity-90">{report.summary}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        <Badge variant="outline">{report.stats.steps} steps</Badge>
        <Badge variant="outline">{report.stats.actions_ok} ok / {report.stats.actions_error} errored</Badge>
        <Badge variant="outline">{report.stats.pages_visited} pages</Badge>
        <Badge variant="outline">{report.stats.duration_s}s</Badge>
        {Object.entries(report.stats.findings_by_category).map(([c, n]) => (
          <Badge key={c} variant="secondary">{c}: {n}</Badge>
        ))}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">
          Findings {report.findings.length > 0 && `(${report.findings.length})`}
        </h3>
        {report.findings.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-sm text-muted-foreground">
            No issues found — clean bill of health.
          </p>
        ) : (
          <div className="space-y-2">
            {report.findings.map((f) => <FindingCard key={f.id} f={f} />)}
          </div>
        )}
      </div>

      <details className="rounded-lg border border-border">
        <summary className="cursor-pointer px-3 py-2 text-sm font-semibold">
          Action log ({report.action_log.length})
        </summary>
        <ol className="space-y-1 border-t border-border px-3 py-2 text-xs">
          {report.action_log.map((a, i) => (
            <li key={i} className={cn("font-mono", !a.ok && "text-red-600 dark:text-red-400")}>
              {a.step}. {a.tool}({Object.entries(a.args).map(([k, val]) => `${k}=${String(val).slice(0, 30)}`).join(", ")})
              {" → "}{a.observation.slice(0, 80)}
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}
