import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Bug, Sparkles, LayoutDashboard, Play, FileSearch, GitBranch, Share2, ShieldCheck, Command, Terminal } from "lucide-react";
import { health } from "@/lib/api";
import { useStore } from "@/store";
import { Button } from "@/components/ui/button";
import { RunsMenu } from "./RunsMenu";
import { ThemeToggle } from "./ThemeToggle";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface AppHeaderProps {
  currentView: string;
  onSelectView: (view: string) => void;
  onOpenCommandPalette: () => void;
}

function HealthDot() {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: health,
    refetchInterval: 15_000,
  });

  const down = isError || !data;
  const ok = data?.browser_ok;
  const label = down
    ? "Backend unreachable"
    : ok
      ? `Browser ready · vision: ${data.vision_model ?? "gemini"}`
      : "Chromium not connected";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="flex cursor-default items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900/80 px-2.5 py-1 text-xs text-slate-300 font-mono"
          aria-label={label}
        >
          <span className={cn("h-2 w-2 rounded-full", down ? "bg-red-500" : ok ? "bg-emerald-500" : "bg-amber-500 animate-pulse")} />
          {down ? "Offline" : ok ? "Browser Ready" : "No Browser"}
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

export const AppHeader: React.FC<AppHeaderProps> = ({
  currentView,
  onSelectView,
  onOpenCommandPalette,
}) => {
  const { showDebug, setShowDebug } = useStore();

  const navItems = [
    { id: "landing", label: "Overview", icon: Sparkles },
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "live", label: "Live Execution", icon: Play },
    { id: "rca", label: "Root Cause Studio", icon: FileSearch },
    { id: "coverage", label: "Requirement Coverage", icon: GitBranch },
    { id: "graph", label: "Knowledge Graph", icon: Share2 },
    { id: "release", label: "Release Readiness", icon: ShieldCheck },
  ];

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md px-4 py-2.5 text-slate-200">
      {/* Brand & Nav Tabs */}
      <div className="flex items-center gap-6">
        <button
          onClick={() => onSelectView("landing")}
          className="flex items-center gap-2.5 text-left group"
        >
          <div className="p-1.5 rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-400 group-hover:scale-105 transition-transform">
            <Bug className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-extrabold tracking-tight text-slate-100 flex items-center gap-1.5">
              AutoQA <span className="px-1.5 py-0.2 rounded bg-blue-500/20 text-blue-400 text-[10px] font-mono">ENTERPRISE</span>
            </div>
            <div className="text-[10px] text-slate-400 font-mono">AI Quality Platform</div>
          </div>
        </button>

        <nav className="hidden lg:flex items-center gap-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = currentView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectView(item.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                  active
                    ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                {item.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Right Controls & Health */}
      <div className="flex items-center gap-2">
        <button
          onClick={onOpenCommandPalette}
          className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <Command className="w-3.5 h-3.5 text-slate-400" />
          <span>Search or Cmd+K</span>
        </button>

        <HealthDot />
        <RunsMenu />

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setShowDebug((d) => !d)}
          title="Toggle debug log"
          className={cn(showDebug && "bg-slate-800 text-slate-200")}
        >
          <Terminal className="h-4 w-4" />
        </Button>
        <ThemeToggle />
      </div>
    </header>
  );
};
