import { Moon, Sun } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type MouseEvent } from "react";

type Theme = "light" | "dark";

// public/theme-init.js sets data-theme before paint with the same rules; keep the two in step.
const THEME_KEY = "theme";
const THEME_COLOR: Record<Theme, string> = { light: "#faf9f5", dark: "#262624" };
const systemQuery = window.matchMedia("(prefers-color-scheme: dark)");
const systemTheme = (): Theme => (systemQuery.matches ? "dark" : "light");

function storedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function currentTheme(): Theme {
  const value = document.documentElement.dataset.theme;
  return value === "light" || value === "dark" ? value : systemTheme();
}

/** Apply a theme; an override pins both theme-color tags to it, following the system restores their own colours. */
function applyTheme(theme: Theme, override: boolean): void {
  const root = document.documentElement;
  // Swap colours in one frame: without this, controls with a colour transition fade after the page does.
  root.classList.add("theme-switching");
  root.dataset.theme = theme;
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("theme-switching")));
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    const own: Theme = meta.media.includes("dark") ? "dark" : "light";
    meta.content = THEME_COLOR[override ? theme : own];
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const [spin, setSpin] = useState(false);
  // An override made on this page view, kept even when storage is blocked and the stored key cannot say so.
  const pageOverride = useRef(false);

  useEffect(() => {
    const follow = () => {
      if (pageOverride.current || storedTheme() !== null) return;
      const next = systemTheme();
      applyTheme(next, false);
      setTheme(next);
    };
    systemQuery.addEventListener("change", follow);
    return () => systemQuery.removeEventListener("change", follow);
  }, []);

  const toggle = (e: MouseEvent<HTMLButtonElement>) => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    const override = next !== systemTheme();
    pageOverride.current = override;
    try {
      if (override) window.localStorage.setItem(THEME_KEY, next);
      else window.localStorage.removeItem(THEME_KEY);
    } catch {
      // Blocked storage: the switch still holds for this page view.
    }
    applyTheme(next, override);
    setTheme(next);
    // Only pointer clicks animate; keyboard activation (detail 0) switches without motion.
    setSpin(e.detail > 0);
  };

  const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  return (
    <button
      type="button"
      className={`btn w-10 flex-none p-0${spin ? " theme-spin" : ""}`}
      aria-label={label}
      title={label}
      onClick={toggle}
      onAnimationEnd={() => setSpin(false)}
    >
      {theme === "dark" ? <Sun key="sun" size={20} aria-hidden="true" /> : <Moon key="moon" size={20} aria-hidden="true" />}
    </button>
  );
}
