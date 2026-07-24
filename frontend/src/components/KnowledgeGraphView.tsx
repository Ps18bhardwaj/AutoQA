import React, { useEffect, useState } from "react";
import { Share2, Server, Globe, Bug, FileCode, RefreshCw } from "lucide-react";
import { useStore } from "@/store";

export const KnowledgeGraphView: React.FC = () => {
  const { selectedRunId } = useStore();
  const [graphData, setGraphData] = useState<any>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(false);

  const fetchGraph = () => {
    setLoading(true);
    fetch("http://127.0.0.1:8003/api/v1/knowledge-graph?project_id=default")
      .then((res) => res.json())
      .then((data) => {
        // Enrich graph nodes with active history if available
        fetch("http://127.0.0.1:8003/history?limit=5")
          .then((r) => r.json())
          .then((history) => {
            const dynamicNodes = [...(data.nodes || [])];
            history.forEach((h: any) => {
              dynamicNodes.push({
                id: `run_${h.id.substring(0, 8)}`,
                label: `Run #${h.id.substring(0, 8)}: ${h.scenario.substring(0, 30)}...`,
                type: "run",
                status: h.verdict === "pass" ? "healthy" : "failed",
                metadata: { url: h.url, verdict: h.verdict, findings: h.findings_count },
              });
            });
            setGraphData({ nodes: dynamicNodes, edges: data.edges || [] });
          })
          .catch(() => setGraphData(data));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchGraph();
  }, [selectedRunId]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 glass-panel p-6 rounded-2xl border border-slate-800">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-indigo-400 mb-1">
            <Share2 className="w-3.5 h-3.5" /> RELATIONAL ENTITY GRAPH
          </div>
          <h1 className="text-2xl font-bold text-slate-100">Quality Knowledge Graph</h1>
          <p className="text-sm text-slate-400 mt-1">Interactive network connecting web pages, API endpoints, UI components, identified bugs, and active execution runs.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchGraph}
            className="p-2.5 rounded-xl glass-panel text-slate-400 hover:text-slate-200 border border-slate-800 transition-colors"
            title="Refresh Knowledge Graph"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
          <span className="px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-mono font-semibold">
            {graphData.nodes?.length || 0} Entities Connected
          </span>
        </div>
      </div>

      {/* Interactive Visual Graph Canvas Card */}
      <div className="glass-panel p-6 sm:p-8 rounded-2xl border border-slate-800 space-y-6">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="text-sm font-bold text-slate-200">System Entity Connections & Test Graph</div>
          <div className="flex flex-wrap gap-4 text-xs">
            <span className="flex items-center gap-1.5 text-blue-400"><Globe className="w-3.5 h-3.5" /> Web Pages</span>
            <span className="flex items-center gap-1.5 text-emerald-400"><Server className="w-3.5 h-3.5" /> API Endpoints</span>
            <span className="flex items-center gap-1.5 text-red-400"><Bug className="w-3.5 h-3.5" /> Bugs & Findings</span>
            <span className="flex items-center gap-1.5 text-purple-400"><FileCode className="w-3.5 h-3.5" /> Code Patches</span>
            <span className="flex items-center gap-1.5 text-amber-400"><Share2 className="w-3.5 h-3.5" /> Test Executions</span>
          </div>
        </div>

        {/* Dynamic Nodes Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(graphData.nodes || []).map((node: any) => (
            <div
              key={node.id}
              className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 transition-all space-y-2 group"
            >
              <div className="flex items-center justify-between">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                    node.type === "page"
                      ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                      : node.type === "api"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : node.type === "bug"
                      ? "bg-red-500/10 text-red-400 border border-red-500/20"
                      : node.type === "run"
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                  }`}
                >
                  {node.type}
                </span>
                <span className="text-[11px] text-slate-500 font-mono">{node.status}</span>
              </div>
              <div className="text-sm font-semibold text-slate-200 group-hover:text-indigo-300 transition-colors">{node.label}</div>
              <div className="text-xs font-mono text-slate-500 truncate">{JSON.stringify(node.metadata)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
