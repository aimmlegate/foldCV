import type { Action, EditorState } from "./state";
import { asOfValue, jobFieldValue, structuredKey, subprojectFieldValue } from "./state";
import { control, field } from "./styles";

type Send = (action: Action) => void;

function EditField({ draftKey, label, value, state, send, apply }: {
  draftKey: string; label: string; value: string; state: EditorState; send: Send; apply: (value: string) => Action;
}) {
  const current = state.structuredDrafts[draftKey] ?? value;
  return <div><label htmlFor={draftKey} className="mb-1 block text-sm">{label}</label>
    <input id={draftKey} className={field} value={current}
      onChange={(event) => send({ type: "structuredDraft", key: draftKey, text: event.target.value })} />
    {state.errors[draftKey] && <p role="alert" className="text-sm text-danger">{state.errors[draftKey]}</p>}
    <div className="mt-1 flex gap-2"><button type="button" className={control} onClick={() => send(apply(current))}>Применить</button>
      <button type="button" className={control} onClick={() => send({ type: "structuredCancel", key: draftKey })}>Отменить</button></div>
  </div>;
}

export function StructuredFields({ state, send }: { state: EditorState; send: Send }) {
  const presentation = state.presentation;
  if (!state.working || !presentation) return null;
  const jobId = Object.entries(presentation.jobProseBlocks).find(([, blockId]) => blockId === state.selectedId)?.[0];
  const job = state.project?.employment.find((item) => item.id === jobId);
  return <>
    <div className="mb-5 grid gap-3 rounded border border-outline p-3 sm:grid-cols-2">
      <EditField draftKey="languages" label="Языки через запятую" value={(presentation.languages ?? []).join(", ")}
        state={state} send={send} apply={(value) => ({ type: "languages", value })} />
      <EditField draftKey="asOf" label="Дата наблюдения YYYY-MM-DD" value={asOfValue(state)}
        state={state} send={send} apply={(value) => ({ type: "asOf", value })} />
    </div>
    {job && <div className="mb-5 rounded border border-outline p-3">
      <h2 className="mb-2 font-semibold">Данные работы</h2>
      <p className="mb-2 text-xs text-muted">Исправления структуры сохраняются отдельно от исходного листа фактов. После изменения проверьте связанный текст.</p>
      <div className="grid gap-3 sm:grid-cols-2">{(["employer", "role", "start", "end"] as const).map((fieldName) =>
        <EditField key={fieldName} draftKey={structuredKey("job", job.id, fieldName)}
          label={fieldName === "employer" ? "Работодатель" : fieldName === "role" ? "Роль" : fieldName === "start" ? "Начало YYYY-MM-DD" : "Окончание YYYY-MM-DD"}
          value={jobFieldValue(state, job.id, fieldName)} state={state} send={send}
          apply={(value) => ({ type: "jobField", id: job.id, field: fieldName, value })} />)}</div>
      {job.subprojects.map((sub) => <div key={sub.id} className="mt-3 border-t border-outline pt-3">
        <h3 className="mb-2 text-sm font-semibold">Подпроект: {sub.name}</h3>
        <div className="grid gap-3 sm:grid-cols-3">{(["name", "start", "end"] as const).map((fieldName) =>
          <EditField key={fieldName} draftKey={structuredKey("subproject", sub.id, fieldName)}
            label={fieldName === "name" ? "Название" : fieldName === "start" ? "Начало YYYY-MM-DD" : "Окончание YYYY-MM-DD"}
            value={subprojectFieldValue(state, job.id, sub.id, fieldName)} state={state} send={send}
            apply={(value) => ({ type: "subprojectField", jobId: job.id, id: sub.id, field: fieldName, value })} />)}</div>
      </div>)}
    </div>}
  </>;
}
