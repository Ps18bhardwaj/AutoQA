import React, { useEffect, useState } from "react";
import { Search, Command, LayoutDashboard, Play, FileSearch, GitBranch, Share2, ShieldCheck, Moon, Sparkles } from "lucide-react";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectView: (view: string) => void;
  onToggleTheme: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onSelectView,
  onToggleTheme,
}) => {
  const [query, setQuery] = useState("");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) onClose();
      }
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const actions = [
    { id: "landing", label: "Product Overview & Landing Page", icon: Sparkles, category: "Navigation" },
    { id: "dashboard", label: "Command Center Dashboard", icon: LayoutDashboard, category: "Navigation" },
    { id: "live", label: "Live Execution Center", icon: Play, category: "Navigation" },
    { id: "rca", label: "Root Cause & Patch Studio", icon: FileSearch, category: "AI Quality" },
    { id: "coverage", label: "Requirement Coverage & Test Gen", icon: GitBranch, category: "AI Quality" },
    { id: "graph", label: "Quality Knowledge Graph", icon: Share2, category: "AI Quality" },
    { id: "release", label: "Release Readiness & Build Compare", icon: ShieldCheck, category: "AI Quality" },
    { id: "theme", label: "Toggle Dark/Light Mode", icon: Moon, category: "Settings" },
  ];

  const filtered = actions.filter((a) =>
    a.label.toLowerCase().includes(query.toLowerCase()) || a.category.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl overflow-hidden rounded-2xl glass-panel border border-slate-700/50 bg-slate-900/90 text-slate-100 shadow-2xl">
        <div className="flex items-center px-4 border-b border-slate-800">
          <Search className="w-5 h-5 text-slate-400 mr-3" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or search platform features..."
            className="w-full py-4 text-slate-100 bg-transparent outline-none placeholder:text-slate-500 text-sm font-medium"
            autoFocus
          />
          <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-[10px] font-semibold text-slate-400 bg-slate-800 rounded border border-slate-700">
            <Command className="w-3 h-3" /> ESC
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-400">No matching command found.</div>
          ) : (
            filtered.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    if (item.id === "theme") {
                      onToggleTheme();
                    } else {
                      onSelectView(item.id);
                    }
                    onClose();
                  }}
                  className="w-full flex items-center justify-between px-3 py-2.5 my-1 rounded-xl text-left text-sm text-slate-200 hover:bg-blue-600/20 hover:text-blue-400 transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-slate-800/80 group-hover:bg-blue-500/20 group-hover:text-blue-400 text-slate-400 transition-colors">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="font-medium">{item.label}</div>
                      <div className="text-xs text-slate-500">{item.category}</div>
                    </div>
                  </div>
                  <span className="text-xs text-slate-500 group-hover:text-blue-400">Jump to →</span>
                </button>
              );
            })
          )}
        </div>

        <div className="px-4 py-2.5 border-t border-slate-800/80 bg-slate-950/40 text-[11px] text-slate-500 flex items-center justify-between">
          <span>AutoQA Command Palette</span>
          <span>Press <kbd className="px-1 bg-slate-800 rounded text-slate-400">⌘K</kbd> anytime</span>
        </div>
      </div>
    </div>
  );
};
