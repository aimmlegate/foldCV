import { createRoot } from "react-dom/client";
import { useRef, useState } from "react";
import { FieldEditor, type FieldEditorHandle } from "./FieldEditor";
import type { CapturedSelection, FieldProjection } from "./adapter";
import "./next.css";

const fields: FieldProjection[] = [
  { fieldId: "job:a/context", slotId: "job:a", label: "Контекст первого места", text: "Alpha 😀\n\nContext" },
  { fieldId: "job:a/period:p/startText", slotId: "job:a", label: "Начало работы", text: "2021" },
  { fieldId: "job:a/tasks", slotId: "job:a", label: "Задачи первого места", text: "Task A" },
  { fieldId: "job:b/context", slotId: "job:b", label: "Контекст второго места", text: "Beta text" },
  { fieldId: "job:b/tasks", slotId: "job:b", label: "Задачи второго места", text: "Task B" },
];

function Proof() {
  const adapter = useRef<FieldEditorHandle>(null);
  const [events, setEvents] = useState(0);
  const [slot, setSlot] = useState<string | null>(null);
  const [departures, setDepartures] = useState<string[]>([]);
  const [selection, setSelection] = useState<CapturedSelection | null>(null);
  const [restores, setRestores] = useState(0);
  const step = useRef(0);
  return <main data-app="foldcv-adapter-proof">
    <div className="proof-controls">
      <button onClick={() => setSelection(adapter.current?.capture() ?? null)} onMouseDown={event => event.preventDefault()}>Захватить выделение</button>
      <button onClick={() => { const field = adapter.current?.read()[0]; if (field) adapter.current?.patch([{ fieldId: field.fieldId, capturedText: field.text, text: "Patched 😀\n\nText" }]); }}>Ответ сервера</button>
      <button onClick={() => adapter.current?.patch([{ fieldId: "job:a/context", capturedText: fields[0]?.text ?? "", text: "Stale reply" }])}>Устаревший ответ</button>
      <output data-proof="buffer">{events}</output><output data-proof="slot">{slot}</output>
      <output data-proof="departures">{JSON.stringify(departures)}</output><output data-proof="restores">{restores}</output>
      <output data-proof="selection">{JSON.stringify(selection)}</output>
      <button onClick={() => { document.querySelector('[data-proof="history"]')?.setAttribute("data-enabled", String(adapter.current?.historyEnabled())); }}>Проверить history</button>
      <output data-proof="history" />
    </div>
    <div className="next-document"><FieldEditor ref={adapter} fields={fields} theme="light" callbacks={{
      buffer: () => setEvents(count => count + 1), selection: setSelection, slot: setSlot,
      departure: id => setDepartures(items => [...items, id]),
      restore: id => {
        setRestores(count => count + 1);
        if (id !== "job:a" || step.current >= 2) return;
        const current = adapter.current?.read()[0];
        if (current) adapter.current?.patch([{ fieldId: current.fieldId, capturedText: current.text,
          text: step.current++ === 0 ? fields[0]?.text ?? "" : "Previous 😀" }]);
      },
    }} /></div>
  </main>;
}
const root = document.getElementById("root");
if (!root) throw new Error("Root element is missing");
createRoot(root).render(<Proof />);
