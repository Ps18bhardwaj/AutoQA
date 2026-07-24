import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark" | "system";

interface AppState {
  theme: Theme;
  setTheme: (t: Theme) => void;

  showDebug: boolean;
  setShowDebug: (v: boolean | ((prev: boolean) => boolean)) => void;

  viewingRunId: string | null;
  setViewingRunId: (id: string | null) => void;

  selectedRunId: string | null;
  setSelectedRunId: (id: string | null) => void;

  latestReport: any | null;
  setLatestReport: (report: any | null) => void;
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      theme: "system",
      setTheme: (t) => set({ theme: t }),

      showDebug: false,
      setShowDebug: (v) =>
        set((s) => ({ showDebug: typeof v === "function" ? v(s.showDebug) : v })),

      viewingRunId: null,
      setViewingRunId: (id) => set({ viewingRunId: id }),

      selectedRunId: null,
      setSelectedRunId: (id) => set({ selectedRunId: id }),

      latestReport: null,
      setLatestReport: (report) => set({ latestReport: report }),
    }),
    {
      name: "autoqa-app",
      version: 2,
      partialize: (s) => ({ theme: s.theme, showDebug: s.showDebug }),
    }
  )
);
