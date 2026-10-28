import type { ReactNode } from "react";
import { Icon } from "../ui/Icon";

export type ToolbarCommand = "undo" | "redo" | "bold" | "italic" | "underline" | "list" | "numbered" | "rewrite" | "facts";
type TextStyle = "p" | "h2" | "h3";
export function Toolbar({ command, textStyle, factsVisible, canUndo, canRedo, selecting, active, style, layoutControls }: {
  command: (value: ToolbarCommand) => void; textStyle: (value: TextStyle) => void;
  factsVisible: boolean; canUndo: boolean; canRedo: boolean; selecting: boolean;
  active: { bold: boolean; italic: boolean; underline: boolean; list: boolean; numbered: boolean }; style: TextStyle;
  layoutControls?: ReactNode;
}) {
  return <div className="editor-toolbar" role="toolbar" aria-label="Форматирование">
    <div className="formatting-tools">
    <div className="tool-group"><button type="button" className="tool" aria-label="Отменить" title="Отменить (⌘Z)" disabled={!canUndo} onMouseDown={event => event.preventDefault()} onClick={() => command("undo")}><Icon name="undo" /></button><button type="button" className="tool" aria-label="Повторить" title="Повторить (⇧⌘Z)" disabled={!canRedo} onMouseDown={event => event.preventDefault()} onClick={() => command("redo")}><Icon name="redo" /></button></div>
    <span className="tool-divider" />
    <select className="toolbar-select" aria-label="Стиль текста" value={style} onChange={event => {
      const value = event.currentTarget.value;
      if (value === "p" || value === "h2" || value === "h3") textStyle(value);
    }}><option value="p">Обычный текст</option><option value="h2">Заголовок</option><option value="h3">Подзаголовок</option></select>
    <div className="tool-group"><button type="button" className="tool" aria-label="Полужирный" title="Полужирный" onMouseDown={event => event.preventDefault()} aria-pressed={active.bold} onClick={() => command("bold")}><b>B</b></button><button type="button" className="tool italic" aria-label="Курсив" title="Курсив" onMouseDown={event => event.preventDefault()} aria-pressed={active.italic} onClick={() => command("italic")}>I</button><button type="button" className="tool underline" aria-label="Подчёркнутый" title="Подчёркнутый" onMouseDown={event => event.preventDefault()} aria-pressed={active.underline} onClick={() => command("underline")}>U</button><button type="button" className="tool" aria-label="Маркированный список" title="Маркированный список" onMouseDown={event => event.preventDefault()} aria-pressed={active.list} onClick={() => command("list")}><Icon name="list" /></button><button type="button" className="tool" aria-label="Нумерованный список" title="Нумерованный список" onMouseDown={event => event.preventDefault()} aria-pressed={active.numbered} onClick={() => command("numbered")}><span aria-hidden="true">1.</span></button></div>
    </div>
    {layoutControls}
    <div className="tool-group panel-tools"><button type="button" className="tool" aria-label="Изменить выделенный текст" title="Изменить выделенный текст" disabled={!selecting} onMouseDown={event => event.preventDefault()} onClick={() => command("rewrite")}><Icon name="spark" /><span>Изменить текст</span></button><button type="button" className="tool" aria-label="Панель фактов" title="Панель фактов" aria-pressed={factsVisible} aria-controls="rich-facts-panel" onClick={() => command("facts")}><Icon name="panel" /><span>Факты</span></button></div>
  </div>;
}
