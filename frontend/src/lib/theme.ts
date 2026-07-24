import { useEffect } from "react";
import { useStore, type Theme } from "@/store";

function apply(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function toggleTheme() {
  const current = useStore.getState().theme;
  const next: Theme = current === "dark" ? "light" : "dark";
  useStore.getState().setTheme(next);
  apply(next);
}

export function useApplyTheme() {
  const theme = useStore((s) => s.theme);

  useEffect(() => {
    apply(theme);
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);
}
