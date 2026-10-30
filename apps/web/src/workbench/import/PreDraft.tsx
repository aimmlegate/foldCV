import { useEffect, useState } from "react";
import { preferencesRequest } from "../../api/client";
import type { ConnectionSnapshot } from "../../connection/workflow";
import type { ReasoningEffort } from "../../connection/reasoning";
import type { ImportOptions } from "../../projects/api";
import { Button } from "../ui/Button";
import { chosenEffort, EffortField, RewriteField } from "./ImportChoices";

/** A pre-draft whose import stopped. With an operation the service knows the choices; without one they are asked again,
 * and rewriting stays off until the user turns it on. */
export function PreDraft({ ask, busy, connection, resume }: {
  ask: boolean; busy: boolean; connection: ConnectionSnapshot | null; resume: (options?: ImportOptions) => void;
}) {
  const [rewrite, setRewrite] = useState(false), [effort, setEffort] = useState<ReasoningEffort | null>(null);
  const [importModel, setImportModel] = useState<string | null>(null);
  useEffect(() => {
    if (!ask) return;
    let alive = true;
    // Without the saved model the form falls back to the processing model, as the import itself does.
    void preferencesRequest().then(value => { if (alive) setImportModel(value.selectedImportModel ?? null); }).catch(() => {});
    return () => { alive = false; };
  }, [ask]);
  if (!ask) return <section className="progress-screen"><div className="progress-content">
    <h2>Импорт не завершён</h2><p>Готовые шаги сохранены.</p>
    <button type="button" disabled={busy} onClick={() => resume()}>Продолжить импорт</button>
  </div></section>;
  const model = importModel ?? connection?.selectedModel ?? null;
  const reasoning = model ? connection?.modelReasoning?.[model] : undefined;
  return <section className="new-screen" aria-label="Импорт не завершён"><div className="source-form">
    <h2>Импорт не завершён</h2><p>Настройки импорта не сохранились. Выберите их снова.</p>
    <div className="source-bottom import-options">
      <EffortField effort={effort} reasoning={reasoning} disabled={busy} change={setEffort} />
      <RewriteField rewrite={rewrite} disabled={busy} change={setRewrite} />
      <Button className="import-process-button" variant="primary" busy={busy} busyLabel="Подготовка…"
        onClick={() => resume({ allowTextRewrite: rewrite, effort: chosenEffort(effort, reasoning) })}>Продолжить импорт</Button>
    </div>
  </div></section>;
}
