import { create } from "zustand";

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem("scm-theme", theme);
}

function initialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const stored = localStorage.getItem("scm-theme");
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: "light",
  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    applyTheme(next);
    set({ theme: next });
  },
  setTheme: (t) => {
    applyTheme(t);
    set({ theme: t });
  },
}));

export function hydrateTheme() {
  const t = initialTheme();
  applyTheme(t);
  useThemeStore.setState({ theme: t });
}
