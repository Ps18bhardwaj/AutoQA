import React from "react";
import { Sparkles, Shield, Cpu, CheckCircle2, ArrowRight, GitPullRequest, Search, Terminal, BarChart2, Layers } from "lucide-react";

interface LandingPageProps {
  onStartTesting: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onStartTesting }) => {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Background Gradients */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[500px] bg-gradient-to-tr from-blue-600/20 via-indigo-500/10 to-purple-600/20 blur-[120px] pointer-events-none" />

      {/* Hero Section */}
      <section className="relative pt-24 pb-20 px-6 max-w-7xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full glass-panel border border-blue-500/30 text-blue-400 text-xs font-semibold uppercase tracking-wider mb-8 animate-pulse">
          <Sparkles className="w-3.5 h-3.5" /> Next-Gen AI Quality Engineering Platform
        </div>

        <h1 className="text-5xl sm:text-7xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 max-w-5xl mx-auto leading-[1.1]">
          Autonomous AI Testing & Quality Intelligence Engine
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-slate-400 max-w-3xl mx-auto leading-relaxed">
          Point AutoQA at any application. Watch vision AI drive Playwright browsers, diagnose failure root causes, self-heal element locators, and output production-ready Git patches.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <button
            onClick={onStartTesting}
            className="px-8 py-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center gap-2 text-base"
          >
            Launch Command Center <ArrowRight className="w-5 h-5" />
          </button>
          <a
            href="http://127.0.0.1:8003/docs"
            target="_blank"
            rel="noreferrer"
            className="px-8 py-4 rounded-xl glass-panel text-slate-300 hover:text-white hover:bg-slate-800/60 font-semibold border border-slate-800 transition-all text-base flex items-center gap-2"
          >
            <Terminal className="w-5 h-5 text-slate-400" /> API Documentation
          </a>
        </div>

        {/* Live Interactive Workflow Visualizer Card */}
        <div className="mt-16 relative rounded-2xl glass-panel border border-slate-800 p-6 sm:p-8 max-w-5xl mx-auto text-left shadow-2xl overflow-hidden group">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4 mb-6">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full bg-red-500" />
              <div className="w-3 h-3 rounded-full bg-yellow-500" />
              <div className="w-3 h-3 rounded-full bg-green-500" />
              <span className="ml-2 text-xs font-mono text-slate-400">AutoQA Enterprise Live Pipeline — Observe ➔ Decide ➔ Act ➔ Verify</span>
            </div>
            <span className="px-2.5 py-1 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono">100% Autonomous</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
              <div className="text-xs font-mono text-blue-400 mb-1">01. OBSERVE</div>
              <div className="text-sm font-semibold text-slate-200">Vision + ARIA Capture</div>
              <div className="text-xs text-slate-400 mt-2">Extracts ARIA tree, 4K screenshots, console & network traces.</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
              <div className="text-xs font-mono text-purple-400 mb-1">02. DECIDE</div>
              <div className="text-sm font-semibold text-slate-200">Gemini Vision Reasoning</div>
              <div className="text-xs text-slate-400 mt-2">Determines precise ARIA action without fragile CSS locators.</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
              <div className="text-xs font-mono text-emerald-400 mb-1">03. ACT & HEAL</div>
              <div className="text-sm font-semibold text-slate-200">Playwright Execution</div>
              <div className="text-xs text-slate-400 mt-2">Dispatches click/type actions with self-healing selector fallback.</div>
            </div>
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
              <div className="text-xs font-mono text-indigo-400 mb-1">04. DIAGNOSE & PATCH</div>
              <div className="text-sm font-semibold text-slate-200">Root Cause Engine</div>
              <div className="text-xs text-slate-400 mt-2">Correlates multi-modal evidence & generates Git patch diffs.</div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Grid */}
      <section className="py-20 px-6 max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-slate-100">Enterprise AI Quality Capabilities</h2>
          <p className="mt-3 text-slate-400 max-w-2xl mx-auto">Built for high-velocity software teams requiring total release confidence.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 rounded-2xl glass-panel border border-slate-800 hover:border-blue-500/40 transition-all group">
            <div className="w-12 h-12 rounded-xl bg-blue-500/10 text-blue-400 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Search className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200">Root Cause Analysis (RCA) Engine</h3>
            <p className="mt-2 text-sm text-slate-400">Deep correlation engine linking DOM errors, console exceptions, network failures, and stack traces into actionable root causes.</p>
          </div>

          <div className="p-6 rounded-2xl glass-panel border border-slate-800 hover:border-emerald-500/40 transition-all group">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <GitPullRequest className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200">AI Patch & Diff Generator</h3>
            <p className="mt-2 text-sm text-slate-400">Automatically creates production-ready Git unified diff patches, PR summaries, and risk assessments for diagnosed bugs.</p>
          </div>

          <div className="p-6 rounded-2xl glass-panel border border-slate-800 hover:border-purple-500/40 transition-all group">
            <div className="w-12 h-12 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Shield className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200">Self-Healing Test Locators</h3>
            <p className="mt-2 text-sm text-slate-400">When selectors shift during deployments, semantic matching and ARIA text similarity recover locators without failing test runs.</p>
          </div>

          <div className="p-6 rounded-2xl glass-panel border border-slate-800 hover:border-amber-500/40 transition-all group">
            <div className="w-12 h-12 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <BarChart2 className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200">Release Readiness Engine</h3>
            <p className="mt-2 text-sm text-slate-400">Holistic Ship/No-Ship scoring combining Quality, Security, Performance, UX, and Accessibility indicators.</p>
          </div>

          <div className="p-6 rounded-2xl glass-panel border border-slate-800 hover:border-pink-500/40 transition-all group">
            <div className="w-12 h-12 rounded-xl bg-pink-500/10 text-pink-400 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Layers className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200">Requirement Coverage AI</h3>
            <p className="mt-2 text-sm text-slate-400">Parses PRDs & User Stories to generate coverage matrices and export executable Playwright test scripts.</p>
          </div>

          <div className="p-6 rounded-2xl glass-panel border border-slate-800 hover:border-indigo-500/40 transition-all group">
            <div className="w-12 h-12 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Cpu className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-slate-200">Quality Knowledge Graph</h3>
            <p className="mt-2 text-sm text-slate-400">Relational graph visualizing links between web pages, API endpoints, components, identified bugs, and active patches.</p>
          </div>
        </div>
      </section>

      {/* Security & Compliance Banner */}
      <section className="py-16 border-t border-b border-slate-800/80 bg-slate-900/40">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-8">
          <div>
            <div className="text-xs font-mono text-blue-400 uppercase tracking-widest mb-1">ENTERPRISE SAFETY RAILS</div>
            <h3 className="text-2xl font-bold text-slate-100">Guarded Execution & Zero Data Spills</h3>
            <p className="text-slate-400 text-sm mt-1 max-w-xl">Domain allowlists, read-only action defaults, form submission human-in-the-loop gates, and credential masking.</p>
          </div>
          <div className="flex flex-wrap gap-4 text-xs font-semibold text-slate-300">
            <span className="px-4 py-2.5 rounded-lg bg-slate-800/80 border border-slate-700 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Human Approval Gate</span>
            <span className="px-4 py-2.5 rounded-lg bg-slate-800/80 border border-slate-700 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Credential Guard</span>
            <span className="px-4 py-2.5 rounded-lg bg-slate-800/80 border border-slate-700 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Allowlist Filtering</span>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 border-t border-slate-900">
        <div>© 2026 AutoQA Platform Inc. All rights reserved.</div>
        <div className="flex gap-6 mt-4 sm:mt-0">
          <a href="http://127.0.0.1:8003/docs" target="_blank" rel="noreferrer" className="hover:text-slate-300">FastAPI Specs</a>
          <a href="http://127.0.0.1:8003/demo" target="_blank" rel="noreferrer" className="hover:text-slate-300">Local Seeded Demo Site</a>
          <a href="http://127.0.0.1:8003/health" target="_blank" rel="noreferrer" className="hover:text-slate-300">System Health</a>
        </div>
      </footer>
    </div>
  );
};
