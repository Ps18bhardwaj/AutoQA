import { Monitor } from "lucide-react";
import { screenshotSrc } from "@/lib/api";

export interface ViewportFrame {
  url: string;
  pageUrl: string;
  title: string;
  step: number;
}

/** The live "agent viewport" — the latest screenshot of what the agent sees,
 * updated each step from the SSE `screenshot` events. This is AutoQA's
 * headline: you watch the agent drive the browser in real time. */
export function AgentViewport({ frame }: { frame: ViewportFrame | null }) {
  return (
    <div className="flex h-full flex-col border-l border-border bg-muted/20">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <Monitor className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">Agent viewport</span>
        {frame && (
          <span className="ml-auto truncate text-xs text-muted-foreground" title={frame.pageUrl}>
            step {frame.step} · {frame.title || frame.pageUrl}
          </span>
        )}
      </div>
      <div className="scroll-thin flex flex-1 items-start justify-center overflow-auto p-4">
        {frame ? (
          <img
            src={screenshotSrc(frame.url)}
            alt={`agent viewport step ${frame.step}`}
            className="max-w-full rounded-md border border-border shadow-sm"
          />
        ) : (
          <div className="mt-16 max-w-xs text-center">
            <Monitor className="mx-auto mb-3 h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              What the agent sees will stream here as it drives the browser.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
