/** Theme engine (D140). The palette for a theme, a mode and a contrast is computed here and written to the root as the
 * custom properties every stylesheet uses; `design/future-editor/visual/tokens.css` carries the same names with the
 * FoldCV light values as the first-paint fallback. The resume sheet pins its own light values (themes.css), so a
 * theme never changes the page. */

export type Mode = "light" | "dark";
export type ThemeId = "foldcv" | "graphite" | "ocean" | "ember" | "iris" | "rose";
type Hue = { hue: number; chroma: number };
export type Theme = { id: ThemeId; name: string; tint: Hue; accent: Hue };

/** The neutral surfaces take the tint, the controls the accent; both are OKLCH hue and chroma. */
export const themes: readonly Theme[] = [
  { id: "foldcv", name: "FoldCV", tint: { hue: 125, chroma: 0.03 }, accent: { hue: 131, chroma: 0.055 } },
  { id: "graphite", name: "Графит", tint: { hue: 250, chroma: 0.006 }, accent: { hue: 250, chroma: 0.08 } },
  { id: "ocean", name: "Океан", tint: { hue: 230, chroma: 0.02 }, accent: { hue: 230, chroma: 0.11 } },
  { id: "ember", name: "Янтарь", tint: { hue: 60, chroma: 0.02 }, accent: { hue: 45, chroma: 0.12 } },
  { id: "iris", name: "Ирис", tint: { hue: 300, chroma: 0.02 }, accent: { hue: 295, chroma: 0.12 } },
  { id: "rose", name: "Роза", tint: { hue: 350, chroma: 0.02 }, accent: { hue: 350, chroma: 0.13 } },
];
export const defaultTheme: ThemeId = "foldcv";
export function themeById(id: string | null | undefined): Theme | undefined { return themes.find(theme => theme.id === id); }

const neutralSteps = ["paper", "surface", "nav", "desk", "wash", "wash-strong", "line", "line-strong", "faint", "muted-soft", "muted", "ink"] as const;
const accentSteps = ["accent", "accent-hover", "accent-text"] as const;
const semanticSteps = ["warn", "warn-line", "warn-bg", "danger", "danger-line", "danger-bg", "ok", "ok-bg"] as const;
type NeutralStep = (typeof neutralSteps)[number];
type AccentStep = (typeof accentSteps)[number];
type SemanticStep = (typeof semanticSteps)[number];
export type ColorToken = NeutralStep | AccentStep | SemanticStep | "on-accent";
export type Palette = Record<ColorToken, string> & Record<"shade" | "paper-rgb" | "accent-rgb", string>;
export const colorTokens: readonly ColorToken[] = [...neutralSteps, ...accentSteps, ...semanticSteps, "on-accent"];

type Oklch = { l: number; c: number; h: number };
/** Lightness of every step; the steps keep their order on both sides of the paper, so a mid tone used as a
 * background with paper-colored text still reads in the dark. */
const ramp: Record<Mode, Record<NeutralStep | AccentStep, number>> = {
  light: { paper: 0.997, surface: 0.984, nav: 0.966, desk: 0.952, wash: 0.932, "wash-strong": 0.912, line: 0.896, "line-strong": 0.862,
    faint: 0.76, "muted-soft": 0.665, "accent-text": 0.515, muted: 0.405, ink: 0.245, accent: 0.48, "accent-hover": 0.42 },
  dark: { paper: 0.245, surface: 0.225, nav: 0.21, desk: 0.19, wash: 0.305, "wash-strong": 0.33, line: 0.36, "line-strong": 0.415,
    faint: 0.51, "muted-soft": 0.63, "accent-text": 0.73, muted: 0.80, ink: 0.94, accent: 0.68, "accent-hover": 0.74 },
};
const semantic: Record<Mode, Record<SemanticStep, Oklch>> = {
  light: { warn: { l: 0.46, c: 0.063, h: 76 }, "warn-line": { l: 0.76, c: 0.07, h: 80 }, "warn-bg": { l: 0.96, c: 0.02, h: 85 },
    danger: { l: 0.47, c: 0.10, h: 35 }, "danger-line": { l: 0.885, c: 0.024, h: 50 }, "danger-bg": { l: 0.955, c: 0.015, h: 60 },
    ok: { l: 0.78, c: 0.06, h: 128 }, "ok-bg": { l: 0.915, c: 0.05, h: 128 } },
  dark: { warn: { l: 0.80, c: 0.08, h: 80 }, "warn-line": { l: 0.50, c: 0.07, h: 78 }, "warn-bg": { l: 0.28, c: 0.035, h: 80 },
    danger: { l: 0.80, c: 0.09, h: 35 }, "danger-line": { l: 0.48, c: 0.08, h: 38 }, "danger-bg": { l: 0.27, c: 0.045, h: 35 },
    ok: { l: 0.76, c: 0.08, h: 130 }, "ok-bg": { l: 0.30, c: 0.05, h: 130 } },
};
/** The approved prototype colors: the default theme in the light shows exactly them at 100 % contrast. */
const exact: Partial<Record<ThemeId, Partial<Record<Mode, Partial<Record<ColorToken, string>>>>>> = {
  foldcv: { light: { paper: "#fffefa", surface: "#fafaf5", nav: "#f3f4ec", desk: "#f2f0ea", wash: "#e8eddf", line: "#dfe2d6", muted: "#47513f",
    ink: "#1c2119", accent: "#58684c", "accent-hover": "#47583b", warn: "#725325", "warn-bg": "#f5efe1", danger: "#8b4230", "danger-line": "#e7d5cb",
    "danger-bg": "#f8eee6", ok: "#acbf96", "ok-bg": "#d9eac6" } },
};

export const contrastLimits = { minimum: 50, maximum: 200 } as const;
function isSemantic(token: ColorToken): token is SemanticStep { return (semanticSteps as readonly string[]).includes(token); }
function isAccent(token: ColorToken): token is AccentStep { return (accentSteps as readonly string[]).includes(token); }
/** Near white and near black the tint fades, as in the prototype's own shades; dark surfaces take less of it. */
function neutralChroma(base: number, l: number, mode: Mode): number {
  return base * (mode === "dark" ? 0.6 : 1) * (0.3 + 0.7 * Math.sqrt(Math.max(0, Math.sin(Math.PI * l))));
}


export function palette(id: ThemeId, mode: Mode, contrast = 100): Palette {
  const theme = themeById(id) ?? themes[0], steps = ramp[mode], given = exact[id]?.[mode] ?? {};
  if (!theme) throw new Error("No themes");
  const factor = Math.min(contrastLimits.maximum, Math.max(contrastLimits.minimum, contrast)) / 100;
  const paperGiven = given.paper, paper = paperGiven ? toOklch(paperGiven).l : steps.paper;
  const base = (token: Exclude<ColorToken, "on-accent">): Oklch => {
    const value = given[token];
    if (value) return toOklch(value);
    if (isSemantic(token)) return semantic[mode][token];
    if (isAccent(token)) return { l: steps[token], c: token === "accent-text" ? theme.accent.chroma * 0.9 : theme.accent.chroma, h: theme.accent.hue };
    return { l: steps[token], c: neutralChroma(theme.tint.chroma, steps[token], mode), h: theme.tint.hue };
  };
  // Contrast bends every distance from the paper with a power curve: lines and washes move most, text never
  // reaches black or white, the order of the steps holds and the paper itself stays. The surfaces behind the
  // paper move half as much, so the window never turns mid-gray.
  const scaled = (color: Oklch, surface: boolean): Oklch => {
    const lighter = color.l > paper, available = lighter ? 0.995 - paper : paper - 0.03, given = Math.abs(color.l - paper);
    if (given < 0.002) return color;
    const power = surface ? 1 + (factor - 1) / 2 : factor;
    const distance = available * Math.min(1, given / available) ** (1 / power);
    return { ...color, l: lighter ? paper + distance : paper - distance };
  };
  const surfaces: readonly ColorToken[] = ["surface", "nav", "desk"];
  const result: Partial<Palette> = {};
  for (const token of colorTokens) {
    if (token === "on-accent") continue;
    const value = given[token];
    result[token] = value && factor === 1 ? value : toHex(scaled(base(token), surfaces.includes(token)));
  }
  const paperHex = result.paper ?? "#ffffff", ink = result.ink ?? "#000000", accent = result.accent ?? "#808080";
  result["on-accent"] = contrastRatio(paperHex, accent) >= contrastRatio(ink, accent) ? paperHex : ink;
  result.shade = mode === "light" ? triplet(toHex({ l: 0.38, c: theme.tint.chroma, h: theme.tint.hue })) : "0 0 0";
  result["paper-rgb"] = triplet(paperHex); result["accent-rgb"] = triplet(accent);
  return result as Palette;
}

function clamp(value: number, low: number, high: number): number { return Math.min(high, Math.max(low, value)); }
function linear(channel: number): number { return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4; }
function encoded(channel: number): number { return channel <= 0.0031308 ? channel * 12.92 : 1.055 * channel ** (1 / 2.4) - 0.055; }

function parse(hex: string): [number, number, number] {
  const digits = hex.replace("#", "");
  const full = digits.length === 3 ? digits.split("").map(digit => digit + digit).join("") : digits;
  return [0, 2, 4].map(start => parseInt(full.slice(start, start + 2), 16) / 255) as [number, number, number];
}

export function toOklch(hex: string): Oklch {
  const [r, g, b] = parse(hex).map(linear) as [number, number, number];
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const lightness = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return { l: lightness, c: Math.hypot(a, bb), h: ((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360 };
}

function toLinearRgb({ l, c, h }: Oklch): [number, number, number] {
  const a = c * Math.cos((h * Math.PI) / 180), b = c * Math.sin((h * Math.PI) / 180);
  const l1 = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m1 = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s1 = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l1 - 3.3077115913 * m1 + 0.2309699292 * s1,
    -1.2684380046 * l1 + 2.6097574011 * m1 - 0.3413193965 * s1,
    -0.0041960863 * l1 - 0.7034186147 * m1 + 1.707614701 * s1];
}

function inGamut(rgb: [number, number, number]): boolean { return rgb.every(channel => channel >= -0.0005 && channel <= 1.0005); }

/** Chroma shrinks until the color fits sRGB; lightness and hue stay. */
export function toHex(color: Oklch): string {
  let rgb = toLinearRgb(color);
  if (!inGamut(rgb)) {
    let low = 0, high = color.c;
    for (let step = 0; step < 14; step += 1) {
      const middle = (low + high) / 2, candidate = toLinearRgb({ ...color, c: middle });
      if (inGamut(candidate)) { low = middle; rgb = candidate; } else high = middle;
    }
    if (!inGamut(rgb)) rgb = toLinearRgb({ ...color, c: 0 });
  }
  return "#" + rgb.map(channel => Math.round(clamp(encoded(clamp(channel, 0, 1)), 0, 1) * 255).toString(16).padStart(2, "0")).join("");
}

function triplet(hex: string): string { return parse(hex).map(channel => String(Math.round(channel * 255))).join(" "); }

function luminance(hex: string): number {
  const [r, g, b] = parse(hex).map(linear) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2 contrast ratio between two hex colors. */
export function contrastRatio(first: string, second: string): number {
  const a = luminance(first), b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
