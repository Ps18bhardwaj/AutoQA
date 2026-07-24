import React from "react";
import { AgentConsole } from "./AgentConsole";
import { Play } from "lucide-react";

export const LiveExecutionCenter: React.FC = () => {
  return (
    <div className="p-6 max-w-[1600px] mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 glass-panel p-6 rounded-2xl border border-slate-800">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-blue-400 mb-1">
            <Play className="w-3.5 h-3.5" /> REAL-TIME BROWSER EXECUTION
          </div>
          <h1 className="text-2xl font-bold text-slate-100">Autonomous Execution Center</h1>
          <p className="text-sm text-slate-400 mt-1">Live Playwright Chromium viewport, ARIA tree inspector, streamed SSE reasoning, and safety approval gate.</p>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-slate-300">
            Engine: <strong className="text-blue-400">Playwright Chromium</strong>
          </span>
          <span className="px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 uppercase font-bold">
            Live Stream
          </span>
        </div>
      </div>

      {/* Embedded Main Agent Console */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800">
        <AgentConsole />
      </div>
    </div>
  );
};
