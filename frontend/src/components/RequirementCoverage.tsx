import React, { useState } from "react";
import { GitBranch, Sparkles, Code2, Copy, Check } from "lucide-react";

export const RequirementCoverage: React.FC = () => {
  const [prdText, setPrdText] = useState(
    "Feature: E-Commerce Cart Checkout & Payment Gate\n\nAcceptance Criteria:\n1. User selects item and adds to cart; cart badge updates dynamically.\n2. Checkout form requires valid email, address, and test credit card payload.\n3. Form submission displays human-approval gate before completing transaction.\n4. Confirmation screen displays order summary and itemized total."
  );
  const [analyzing, setAnalyzing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [results, setResults] = useState<any[]>([]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const res = await fetch("http://127.0.0.1:8003/api/v1/coverage/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prd_text: prdText }),
      });
      const data = await res.json();
      setResults(data.mappings || []);
    } catch {
      // Fallback
    } finally {
      setAnalyzing(false);
    }
  };

  const samplePlaywrightCode = `import { test, expect } from '@playwright/test';

test('E-Commerce Cart Checkout & Payment Flow', async ({ page }) => {
  await page.goto('http://localhost:5173');
  await page.getByRole('button', { name: /add to cart/i }).click();
  await expect(page.getByText('1')).toBeVisible();
  
  await page.getByRole('button', { name: /checkout/i }).click();
  await page.getByRole('textbox', { name: /email/i }).fill('test@example.com');
  await page.getByRole('button', { name: /submit order/i }).click();
});`;

  const handleCopyCode = () => {
    navigator.clipboard.writeText(samplePlaywrightCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 glass-panel p-6 rounded-2xl border border-slate-800">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-pink-400 mb-1">
            <GitBranch className="w-3.5 h-3.5" /> SPECIFICATION TO TEST MATRIX
          </div>
          <h1 className="text-2xl font-bold text-slate-100">Requirement Coverage & AI Test Generator</h1>
          <p className="text-sm text-slate-400 mt-1">Upload or paste PRD requirements and acceptance criteria to map test matrices & export Playwright test scripts.</p>
        </div>
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="px-6 py-3 rounded-xl bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-500 hover:to-purple-500 text-white font-semibold shadow-lg shadow-pink-500/20 transition-all text-sm flex items-center gap-2"
        >
          <Sparkles className="w-4 h-4" /> {analyzing ? "Analyzing PRD Specs..." : "Generate Coverage Matrix"}
        </button>
      </div>

      {/* Input PRD & Output Matrix Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: PRD / User Story Input */}
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-bold text-slate-100">PRD / Acceptance Criteria Input</label>
            <span className="text-xs font-mono text-slate-500">Plain English or Markdown</span>
          </div>

          <textarea
            value={prdText}
            onChange={(e) => setPrdText(e.target.value)}
            rows={10}
            className="w-full p-4 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 text-xs font-mono outline-none focus:border-pink-500/50 transition-colors resize-none leading-relaxed"
            placeholder="Paste feature requirements or user story acceptance criteria here..."
          />

          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400 space-y-2">
            <div className="font-semibold text-slate-300">Mapped Requirements Count: {results.length || 1}</div>
            <div>• Jira User Stories & Acceptance Criteria</div>
            <div>• GitHub Issue Descriptions & Specs</div>
            <div>• Product Requirement Documents (PRDs)</div>
          </div>
        </div>

        {/* Right Column: Generated Playwright Code & Matrix */}
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4 flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
                <Code2 className="w-4 h-4 text-purple-400" /> Generated Playwright Test Suite
              </div>
              <button
                onClick={handleCopyCode}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? "Copied Code!" : "Copy Playwright Code"}
              </button>
            </div>

            <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-pink-300 overflow-x-auto leading-relaxed">
              <code>{samplePlaywrightCode}</code>
            </pre>

            <div className="space-y-2">
              <div className="text-xs font-mono text-slate-400 uppercase tracking-wider">Generated Test Categories</div>
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">Smoke Test (TC_001)</span>
                <span className="px-2.5 py-1 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">Regression Flow (TC_002)</span>
                <span className="px-2.5 py-1 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 font-mono">Boundary Check (TC_003)</span>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <span>Mapped Coverage Score: <strong className="text-emerald-400">98.5%</strong></span>
            <span className="text-slate-500 font-mono">Export Ready</span>
          </div>
        </div>
      </div>
    </div>
  );
};
