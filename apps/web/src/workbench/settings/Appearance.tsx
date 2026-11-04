import { useMemo, type CSSProperties } from "react";
import { Icon } from "../ui/Icon";
import { palette, themes, type Palette, type ThemeId } from "./themes";
import { contrastRange, glassRange, schemes, textSizes, type Appearance, type PaneOrder, type Scheme, type TextSize } from "./interface";
import { SettingsGroup, SettingsRow } from "./Rows";

const schemeNames: Record<Scheme, string> = { system: "Как в системе", light: "Светлое", dark: "Тёмное" };
const sizeNames: Record<TextSize, string> = { normal: "Обычный", large: "Крупный", "x-large": "Очень крупный" };

/** A small window drawn from a palette: sidebar, chip, text lines, a floating card and the composer. */
function Preview({ colors, half }: { colors: Palette; half?: boolean }) {
  const style = { "--p-desk": colors.desk, "--p-paper": colors.paper, "--p-nav": colors.nav, "--p-line": colors["line-strong"],
    "--p-wash": colors.wash, "--p-accent": colors.accent, "--p-warn": colors.warn, "--p-danger": colors.danger, "--p-ok": colors.ok,
    "--p-faint": colors.faint } as CSSProperties;
  return <span className={half ? "preview-window preview-half" : "preview-window"} style={style}>
    <span className="preview-side"><i /><i /><i /></span>
    <span className="preview-main"><i className="preview-chip" /><i className="preview-text" /><i className="preview-text short" />
      <span className="preview-card"><i /><i /><i /></span>
      <span className="preview-composer"><i /></span></span>
  </span>;
}

/** An orb from the paper to the accent, so every theme shows its hue at a glance. */
function swatch(colors: Palette, dark: boolean): CSSProperties {
  const tint = (share: number) => `color-mix(in oklab, ${colors.accent} ${String(share)}%, ${colors.paper})`;
  return { background: dark
    ? `radial-gradient(circle at 34% 30%, ${colors["line-strong"]} 0%, ${tint(18)} 48%, ${tint(70)} 100%)`
    : `radial-gradient(circle at 34% 30%, ${colors.paper} 0%, ${tint(30)} 50%, ${tint(75)} 100%)` };
}

const Sun = () => <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" /></svg>;
const Moon = () => <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /></svg>;

function SliderRow({ id, label, description, value, range, change }: { id: string; label: string; description: string; value: number;
  range: { minimum: number; maximum: number; step: number; initial: number }; change: (value: number) => void }) {
  return <SettingsRow label={label} hint={description} htmlFor={id}>
    {value !== range.initial && <button type="button" className="icon slider-reset" aria-label={`${label}: вернуть ${String(range.initial)} %`} onClick={() => change(range.initial)}><Icon name="undo" /></button>}
    <div className="slider-control"><output htmlFor={id}>{value}%</output>
      <input id={id} type="range" min={range.minimum} max={range.maximum} step={range.step} value={value}
        onChange={event => change(Number(event.currentTarget.value))} /></div>
  </SettingsRow>;
}

/** Settings → Оформление (D140, D147): scheme, a theme for each side, then one group with contrast, glass, the text
 * size and the pane order. Every change saves at once and shows at once; the resume page is not touched. */
export function AppearanceSettings({ value, change, paneOrder, changePaneOrder }: { value: Appearance; change: (value: Appearance) => void;
  paneOrder: PaneOrder; changePaneOrder: (order: PaneOrder) => void }) {
  const light = useMemo(() => palette(value.lightTheme, "light", value.contrast), [value.lightTheme, value.contrast]);
  const dark = useMemo(() => palette(value.darkTheme, "dark", value.contrast), [value.darkTheme, value.contrast]);
  const pick = (id: ThemeId, side: "light" | "dark" | "both") => change({ ...value, lightTheme: side === "dark" ? value.lightTheme : id, darkTheme: side === "light" ? value.darkTheme : id });
  return <>
    <div className="scheme-cards" role="radiogroup" aria-label="Схема">
      {schemes.map(scheme => <button key={scheme} type="button" role="radio" aria-checked={value.scheme === scheme} className="scheme-card"
        onClick={() => change({ ...value, scheme })}>
        <span className="scheme-preview" aria-hidden="true">
          {scheme !== "dark" && <Preview colors={light} />}
          {scheme !== "light" && <Preview colors={dark} half={scheme === "system"} />}
        </span>
        <span className="scheme-name">{schemeNames[scheme]}</span>
      </button>)}
    </div>
    <h3 className="settings-subtitle">Темы</h3>
    <p className="settings-lead">Круг слева — светлый вариант, справа — тёмный; название выбирает тему для обоих.</p>
    <div className="theme-cards">
      {themes.map(theme => {
        const lightColors = palette(theme.id, "light", value.contrast), darkColors = palette(theme.id, "dark", value.contrast);
        const lightOn = value.lightTheme === theme.id, darkOn = value.darkTheme === theme.id;
        return <div key={theme.id} className="theme-card" data-selected={lightOn || darkOn ? "true" : undefined}>
          <div className="theme-swatches">
            <button type="button" className="theme-swatch" aria-pressed={lightOn} aria-label={`${theme.name}, светлый вариант`} style={swatch(lightColors, false)}
              onClick={() => pick(theme.id, "light")}>{lightOn && <span className="theme-badge"><Sun /></span>}</button>
            <button type="button" className="theme-swatch" aria-pressed={darkOn} aria-label={`${theme.name}, тёмный вариант`} style={swatch(darkColors, true)}
              onClick={() => pick(theme.id, "dark")}>{darkOn && <span className="theme-badge"><Moon /></span>}</button>
          </div>
          <button type="button" className="theme-name" onClick={() => pick(theme.id, "both")}>{theme.name}</button>
        </div>;
      })}
    </div>
    <SettingsGroup title="Интерфейс">
      <SliderRow id="interface-contrast" label="Контраст" description="Сила цветов и линий во всём интерфейсе." value={value.contrast} range={contrastRange}
        change={contrast => change({ ...value, contrast })} />
      <SliderRow id="interface-glass" label="Плотность панелей" description="Чем выше, тем меньше просвечивают меню, окна и подсказки." value={value.glass} range={glassRange}
        change={glass => change({ ...value, glass })} />
      <SettingsRow label="Размер текста" hint="Меню, панели и подсказки; масштаб резюме — в панели редактора.">
        {/* Native radios: the arrow keys move the choice as in any radio group. */}
        <div className="segmented" role="radiogroup" aria-label="Размер текста">
          {textSizes.map(size => <label key={size}><input type="radio" name="interface-text-size" value={size} checked={value.textSize === size}
            onChange={() => change({ ...value, textSize: size })} /><span>{sizeNames[size]}</span></label>)}
        </div></SettingsRow>
      <SettingsRow label="Порядок панелей при сравнении" htmlFor="workspace-pane-order">
        <select id="workspace-pane-order" value={paneOrder} onChange={event => changePaneOrder(event.currentTarget.value === "original-first" ? "original-first" : "layout-first")}>
          <option value="layout-first">Макет слева, оригинал справа</option>
          <option value="original-first">Оригинал слева, макет справа</option>
        </select></SettingsRow>
    </SettingsGroup>
    <p className="settings-lead">Всё окно увеличивают ⌘ + и ⌘ − (Ctrl на Windows).</p>
  </>;
}
