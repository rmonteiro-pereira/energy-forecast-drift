/**
 * Read the palette back out of CSS, rather than keeping a second copy in TS.
 *
 * ECharts needs literal colour strings, so something has to bridge the gap
 * between `styles.css` and the chart options. Duplicating the hex values in
 * TypeScript is the obvious way and the wrong one: the two copies drift, and
 * dark mode silently keeps the light palette. Instead the tokens are read from
 * the computed style of `:root` at render time, and re-read whenever the theme
 * changes — so `styles.css` stays the single source of truth.
 */

import { useEffect, useState } from "react";

export const TOKEN_NAMES = [
  "surface-1",
  "page",
  "text-primary",
  "text-secondary",
  "text-muted",
  "grid",
  "axis",
  "series-1",
  "series-2",
  "series-3",
  "status-good",
  "status-warning",
  "status-serious",
  "status-critical",
] as const;

export type TokenName = (typeof TOKEN_NAMES)[number];
export type Tokens = Record<TokenName, string>;

export type ThemeChoice = "system" | "light" | "dark";

function readTokens(): Tokens {
  const style = getComputedStyle(document.documentElement);
  const tokens = {} as Tokens;
  for (const name of TOKEN_NAMES) {
    tokens[name] = style.getPropertyValue(`--${name}`).trim();
  }
  return tokens;
}

/** The current palette, re-read on OS theme change and on the local toggle. */
export function useThemeTokens(choice: ThemeChoice): Tokens {
  const [tokens, setTokens] = useState<Tokens>(readTokens);

  useEffect(() => {
    const root = document.documentElement;
    if (choice === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", choice);

    // The attribute change has to land in the computed style before it is read.
    const frame = requestAnimationFrame(() => setTokens(readTokens()));

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setTokens(readTokens());
    media.addEventListener("change", onChange);

    return () => {
      cancelAnimationFrame(frame);
      media.removeEventListener("change", onChange);
    };
  }, [choice]);

  return tokens;
}

/** True when the rendered surface is the dark one — ECharts needs to know. */
export function isDark(tokens: Tokens): boolean {
  return tokens["surface-1"].toLowerCase() !== "#fcfcfb";
}
