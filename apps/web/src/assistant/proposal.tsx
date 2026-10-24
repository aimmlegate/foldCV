import type { AssistantContinuationOptionsV1 } from "../contracts/generated/assistant_continuation_options_v1";
import { useEffect, useRef } from "react";
import type { AssistantProposalV1 } from "../contracts/generated/assistant_proposal_v1";
import type { AssistantProposalRequestV1 } from "../contracts/generated/assistant_proposal_request_v1";
import type { AssistantTaskCatalogV1 } from "../contracts/generated/assistant_task_catalog_v1";
import type { AssistantReviewV1 } from "../contracts/generated/assistant_review_v1";
import type { AssistantCapabilityReviewV1 } from "../contracts/generated/assistant_capability_review_v1";

export const proposalKey = (value: AssistantProposalV1): string => `${value.id}:${String(value.version)}:${value.contentSha256}`;
export const proposalRequest = (value: AssistantProposalV1): AssistantProposalRequestV1 => ({ schemaVersion: 1,
  protocolVersion: 1, proposalId: value.id, version: value.version, contentSha256: value.contentSha256 });

const states = { building: "Подготовка варианта", ready: "Вариант готов к просмотру", incomplete: "Черновик не завершён",
  invalid: "Вариант недоступен", cancelled: "Подготовка остановлена", applying: "Сохраняем принятый вариант", applied: "Вариант сохранён",
  stale: "Вариант устарел", discarded: "Вариант отклонён", expired: "Срок хранения истёк",
  failed_before_commit: "Вариант не сохранён", outcome_unknown: "Проверяем результат сохранения" };
const effects = { wording: "Текст", structure: "Структура", fact: "Факты и поддержка", format: "Оформление" };
export function proposalControls(value: AssistantProposalV1, catalog: AssistantTaskCatalogV1 | null | undefined,
  busy: boolean, invalidated: boolean, allowEdits: boolean, stage?: AssistantReviewV1["apply"]): { apply: boolean; discard: boolean; reason: string | null } {
  const task = catalog?.tasks.find(item => item.id === value.taskId);
  const readiness = stage ?? task?.apply;
  const available = catalog?.protocolEnabled === true && readiness?.state === "available" && allowEdits;
  const applicable = value.state === "ready" || value.state === "failed_before_commit" && stage?.state === "available";
  return { apply: !busy && !invalidated && applicable && available,
    discard: !busy && ["ready", "incomplete", "stale", "failed_before_commit"].includes(value.state),
    reason: invalidated && ["ready", "failed_before_commit"].includes(value.state) ? "После открытия варианта документ изменился. Подготовьте новый вариант; текущие правки сохранены."
      : !["ready", "failed_before_commit"].includes(value.state) ? null : !allowEdits ? "Разрешите правки, затем отдельно нажмите «Применить»."
      : !available ? [readiness?.reason, readiness?.remedy].filter(Boolean).join(" ") || "Применение сейчас недоступно." : null };
}

export function ProposalPreview({ value, catalog, busy, invalidated, allowEdits, stage, action, continuation, continueDraft, apply, discard }: {
  value: AssistantProposalV1; catalog: AssistantTaskCatalogV1 | null | undefined; busy: boolean; invalidated: boolean; allowEdits: boolean;
  apply: () => void; discard: () => void;
  stage?: AssistantReviewV1["apply"] | undefined;
  action?: AssistantCapabilityReviewV1["action"];
  continuation?: AssistantContinuationOptionsV1["options"][number] | undefined;
  continueDraft?: () => void;
}) {
  const task = catalog?.tasks.find(item => item.id === value.taskId), controls = proposalControls(value, catalog, busy, invalidated, allowEdits, stage);
  const button = useRef<HTMLButtonElement>(null), heading = useRef<HTMLHeadingElement>(null);
  const wasBusy = useRef(busy), restoreFocus = useRef(false), focusHeading = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy && restoreFocus.current) {
      (focusHeading.current || button.current?.disabled ? heading.current : button.current)?.focus();
      focusHeading.current = false;
      restoreFocus.current = false;
    }
    wasBusy.current = busy;
  }, [busy]);
  const changed = value.coverage.filter(unit => unit.state === "changed").length;
  const unresolved = value.coverage.filter(unit => !unit.read || unit.state === "unresolved").length;
  return <article className="chat-proposal" aria-label={`Вариант ${String(value.version)}: ${task?.label ?? "Изменения"}`}>
    <h3 ref={heading} tabIndex={-1}>{states[value.state]} · версия {value.version}</h3>
    <p>{task?.label ?? "Подготовленные изменения"}</p>
    {value.reason && <p>{value.reason}</p>}
    {action && <><p>Проект: «{action.targetLabel}» ({action.targetId}).</p><p>{action.consequence}</p>
      {action.imagePreviewUrl && <img className="max-h-48 max-w-full object-contain" src={action.imagePreviewUrl} alt="Изображение в предлагаемом действии" />}</>}
    <p className="chat-proposal-coverage">Охват: {value.coverage.length}. Изменено: {changed}. Не завершено: {unresolved}.</p>
    {!["applied", "applying", "outcome_unknown"].includes(value.state) && <p>Документ пока не изменён этим вариантом.</p>}
    {["applying", "outcome_unknown"].includes(value.state) && <p>Проверяем исходное сохранение. Повторное применение недоступно.</p>}
    {value.changes.map((change, index) => <details key={change.unitId} open className="chat-proposal-change">
      <summary>{effects[change.effect]} · {index + 1}</summary>
      <div className="chat-proposal-comparison"><div><h4>Сейчас</h4><pre>{change.before || "Нет"}</pre></div>
        <div><h4>После применения</h4><pre>{change.after || "Нет"}</pre></div></div>
    </details>)}
    {unresolved > 0 && <details><summary>Что осталось проверить</summary><ul>{value.coverage.filter(unit => !unit.read || unit.state === "unresolved")
      .map(unit => <li key={unit.unitId}>{unit.reason}</li>)}</ul></details>}
    {value.taskId === "undo" || value.taskId === "redo" ? <p>Навигация по показанному действию. Новая запись в истории не создаётся.</p>
      : task?.reversibility === "shared_undo" && <p>После сохранения — одна отмена в истории редактора.</p>}
    {continuation && <p>Осталось операций: {continuation.operationsRemaining}. Версий: {continuation.versionsRemaining}.
      Новый шаг: до {continuation.toolCalls} вызовов, до {continuation.toolBytes} байт на сообщение. Документ не меняется.</p>}
    {continuation && continuation.availability.state !== "available" && <p role="status">
      {[continuation.availability.reason, continuation.availability.remedy].filter(Boolean).join(" ")}</p>}
    {controls.reason && <p role="status">{controls.reason}</p>}
    <div className="chat-proposal-actions">{continuation && <button type="button" className="text-button"
      disabled={busy || invalidated || continuation.availability.state !== "available" || !continueDraft}
      onClick={event => { restoreFocus.current = event.detail === 0; focusHeading.current = true; continueDraft?.(); }}>Продолжить черновик</button>}<button ref={button} type="button" className="primary" disabled={!controls.apply}
      onClick={event => { restoreFocus.current = event.detail === 0; apply(); }}>Применить</button>
      <button type="button" className="text-button" disabled={!controls.discard} onClick={discard}>Отклонить</button></div>
  </article>;
}
