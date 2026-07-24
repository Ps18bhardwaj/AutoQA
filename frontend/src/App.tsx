import { useState } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { useApplyTheme, toggleTheme } from "@/lib/theme";
import { AppHeader } from "./components/AppHeader";
import { CommandPalette } from "./components/CommandPalette";
import { LandingPage } from "./components/LandingPage";
import { Dashboard } from "./components/Dashboard";
import { LiveExecutionCenter } from "./components/LiveExecutionCenter";
import { RootCauseStudio } from "./components/RootCauseStudio";
import { RequirementCoverage } from "./components/RequirementCoverage";
import { KnowledgeGraphView } from "./components/KnowledgeGraphView";
import { ReleaseReadinessView } from "./components/ReleaseReadinessView";

export default function App() {
  useApplyTheme();
  const [currentView, setCurrentView] = useState<string>("landing");
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen w-full flex flex-col bg-slate-950 text-slate-100 font-sans selection:bg-blue-500/30 selection:text-blue-200">
        <AppHeader
          currentView={currentView}
          onSelectView={setCurrentView}
          onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
        />

        <main className="flex-1 min-h-0 overflow-y-auto">
          {currentView === "landing" && (
            <LandingPage onStartTesting={() => setCurrentView("live")} />
          )}

          {currentView === "dashboard" && (
            <Dashboard
              onStartNewRun={() => setCurrentView("live")}
              onOpenRCA={() => setCurrentView("rca")}
              onOpenRelease={() => setCurrentView("release")}
            />
          )}

          {currentView === "live" && <LiveExecutionCenter />}

          {currentView === "rca" && <RootCauseStudio />}

          {currentView === "coverage" && <RequirementCoverage />}

          {currentView === "graph" && <KnowledgeGraphView />}

          {currentView === "release" && <ReleaseReadinessView />}
        </main>

        <CommandPalette
          isOpen={isCommandPaletteOpen}
          onClose={() => setIsCommandPaletteOpen(false)}
          onSelectView={setCurrentView}
          onToggleTheme={toggleTheme}
        />

        <Toaster position="bottom-right" />
      </div>
    </TooltipProvider>
  );
}
