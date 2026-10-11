import { useState } from "react";
import type { Action, EditorState } from "./state";
import { coverageReview } from "./coverage";
import type { CoverageIssue, CoverageTarget } from "./coverage";
import { control, field } from "./styles";
import type { Facts } from "../contracts/generated/project";

type Props = { state: EditorState; send: (action: Action) => void;
  openSource: (sourceId: string, unitId: string) => void };

const dispositionName: Record<CoverageTarget["disposition"], string> = {
  shown: "Показан", condensed: "Сокращён", archived: "Только в проекте",
  duplicate: "Дубликат", unresolved: "Не решён", excluded: "Исключён",
};

function clipped(value: string, limit = 500): string {
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

function safeSummary(value: string): string {
  const contact = /@|\b(?:https?:\/\/|www\.)|\b[\w.-]+\.(?:com|org|net|io|ru|rs|dev|me|uk|eu)\/\S+|(?<!\w)\+\d{7,15}(?!\w)|\b(?:e-?mail|phone|mobile|tel(?:ephone)?|contact|whatsapp|telegram|телефон|почта|контакт)\s*[:：]|(?<!\w)(?:\+?\d{1,3}[ .-])?(?:\(\d{2,4}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{4}(?!\w)|(?<!\w)(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{2}[ .-]\d{2}(?!\w)|(?<!\w)\d{3}[ .-]\d{4}(?!\w)/i;
  const metadata = /\b(?:age|возраст)\s*[:：,\-]?\s*\d{1,3}\b|\b(?:date of birth|birth\s*date|birthdate|дата рождения|год рождения)\b|\b(?:resume|résumé|cv|резюме)\s*(?:id|#|№|updated|posted|обновлено|размещено)\b|\b(?:job[ -]?board|сайт вакансий|источник резюме)\s*[:：]\s*\S+|\b(?:portfolio|website|web\s*site|personal\s*(?:site|website)|linkedin|github|gitlab|портфолио|личный\s+сайт|сайт)\s*[:：]\s*(?:[\w-]+\.)+[a-z]{2,24}(?!\w)/i;
  const bare = /(?<!\w)\d{10,11}(?!\w)/;
  const context = /\b(?:call|text|reach|contact|phone|mobile|tel|number|whatsapp|telegram|телефон|номер|связь|позвон\w*)\b/i;
  if (contact.test(value) || metadata.test(value) || bare.test(value) &&
      (value.trim() === bare.exec(value)?.[0] || context.test(value))) return "Личные данные — откройте факт для проверки";
  return clipped(value);
}

type MetricValue = Extract<Facts[number], { kind: "metric" }>["value"];
const compareName: Record<MetricValue["comparator"], string> = {
  exact: "ровно", at_least: "не менее", at_most: "не более", approximately: "около", range: "диапазон",
};
const creditName: Record<MetricValue["attribution"], string> = {
  personal: "личный", team: "командный", organization: "организации", unknown: "не указан",
};

function metricSummary(value: MetricValue): string {
  return `${compareName[value.comparator]} ${value.number}${value.upperNumber === null ? "" : `–${value.upperNumber}`} ${value.unit}` +
    ` · вклад: ${creditName[value.attribution]}` +
    `${value.qualifiers.length ? ` · условия: ${clipped(value.qualifiers.join(", "), 160)}` : ""}` +
    `${value.period ? ` · период: ${value.period}` : ""}` +
    `${value.scope ? ` · область: ${value.scope}` : ""}${value.baseline ? ` · было: ${value.baseline}` : ""}` +
    `${value.result ? ` · результат: ${value.result}` : ""}`;
}

function factSummary(fact: Facts[number] | undefined): string {
  if (!fact) return "Факт недоступен";
  if (fact.kind === "text") return safeSummary(fact.value.text);
  if (fact.kind === "technology") return safeSummary(fact.value.display);
  if (fact.kind === "date") return `${fact.value.year}${fact.value.month ? `-${String(fact.value.month).padStart(2, "0")}` : ""}` +
    `${fact.value.day ? `-${String(fact.value.day).padStart(2, "0")}` : ""}`;
  if (fact.kind === "leadership") {
    const team = fact.value.teamSize;
    return safeSummary(`вклад: ${creditName[fact.value.attribution]}${team ?
      ` · команда: ${metricSummary(team)}` : ""}` +
      ` · действие: ${fact.value.action}`);
  }
  return safeSummary(metricSummary(fact.value));
}

function jobLabel(state: EditorState, id: string): string {
  const job = state.project?.employment.find((item) => item.id === id) ??
    state.working?.manual.employment.find((item) => item.id === id) ??
    state.working?.sheet.employment?.find((item) => item.id === id);
  return job ? `${job.employer} · ${job.role}` : "Работа";
}

function blockLabel(state: EditorState, id: string): string {
  const jobId = Object.entries(state.presentation?.jobProseBlocks ?? {}).find(([, blockId]) => blockId === id)?.[0];
  if (jobId) return `Проект: ${jobLabel(state, jobId)}`;
  const kind = state.project?.views.find((item) => item.id === id)?.kind;
  return kind === "profile" ? "О себе" : kind === "education" ? "Образование" :
    kind === "early_career" ? "Ранний опыт" : kind === "skills" ? "Навыки" : "Блок";
}

function unitSummary(state: EditorState, target: CoverageTarget): string {
  const unit = state.working?.sources.find((item) => item.entry.result.sourceId === target.sourceId)
    ?.entry.result.units.find((item) => item.id === target.unitId);
  const overlay = state.working?.sources.find((item) => item.entry.result.sourceId === target.sourceId)
    ?.entry.overlays[`unit:${target.unitId}`];
  return safeSummary(overlay || unit?.text || "Фрагмент исходника недоступен");
}

function IssueList({ title, issues, facts, state, send, openSource, openFact }: {
  title: string; issues: CoverageIssue[]; state: EditorState; send: Props["send"]; openSource: Props["openSource"];
  facts: CoverageTarget[]; openFact: (id: string) => void }) {
  if (!issues.length) return null;
  return <section className="mt-4"><h3 className="font-semibold">{title} · {issues.length}</h3>
    <ul className="mt-2 space-y-2">{issues.map((issue) => <li key={issue.id}
      className="rounded border border-outline bg-surface p-3 text-sm">
      <strong>{issue.message}</strong><p className="mt-1 text-muted">{issue.action}</p>
      {issue.factId && <p className="mt-1" title={issue.factId}>Факт: {factSummary(facts.find((item) =>
        item.id === issue.factId)?.fact)}</p>}
      {issue.sourceId && issue.unitId && <p className="mt-1">Исходник: {unitSummary(state,
        { kind: "unit", id: "", disposition: "unresolved", dependency: "", reason: null,
          sourceId: issue.sourceId, unitId: issue.unitId })}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        {issue.blockId && <><button type="button" className={control} title={issue.blockId}
          onClick={() => send({ type: "select", id: issue.blockId! })}>Открыть блок</button>
          <span>{blockLabel(state, issue.blockId)}</span></>}
        {issue.factId && <button type="button" className={control} title={issue.factId}
          onClick={() => openFact(issue.factId!)}>Открыть факт</button>}
        {issue.jobId && <span title={issue.jobId}>{jobLabel(state, issue.jobId)}</span>}
        {issue.sourceId && issue.unitId && <button type="button" className={control}
          title={issue.unitId} onClick={() => openSource(issue.sourceId!, issue.unitId!)}>Исходник</button>}
        {issue.severity === "warning" && <button type="button" className={control}
          onClick={() => send({ type: "coverageAcknowledge", issueId: issue.id,
            dependency: issue.dependency })}>{issue.acknowledged ? "Снять подтверждение" : "Подтвердить проверку"}</button>}
      </div>
    </li>)}</ul>
  </section>;
}

function DecisionRow({ target, state, send, openSource }: {
  target: CoverageTarget; state: EditorState; send: Props["send"]; openSource: Props["openSource"] }) {
  const [reason, setReason] = useState("");
  const saved = state.working?.coverage?.decisions.find((item) => item.targetKind === target.kind &&
    item.targetId === target.id && item.dependency === target.dependency);
  const canDecide = target.disposition === "unresolved" || target.disposition === "archived" ||
    target.disposition === "excluded" || Boolean(saved);
  return <li id={`coverage-fact-${target.id}`} className="rounded border border-outline bg-surface p-2 text-sm">
    <div className="flex flex-wrap items-center gap-2"><span className="font-medium" title={target.id}>{target.kind === "unit" ?
      `Фрагмент: ${unitSummary(state, target)}` : `Факт: ${factSummary(target.fact)}`}</span>
      <span className="text-muted">{dispositionName[target.disposition]}</span>
      {target.blockId && <button type="button" className={control} title={target.blockId}
        onClick={() => send({ type: "select", id: target.blockId! })}>Открыть блок</button>}
      {target.sourceId && target.unitId && <button type="button" className={control}
        onClick={() => openSource(target.sourceId!, target.unitId!)}>Исходник</button>}
    </div>
    {saved?.reason && <p className="mt-1 text-muted">Причина: {saved.reason}</p>}
    {canDecide && <div className="mt-2 flex flex-wrap gap-2"><label className="min-w-40 flex-1">
      {target.confirmable ? "Причина исключения или проверки" : "Причина исключения"}
      <input className={field} value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
    </label><button type="button" className={control} disabled={!reason.trim()}
      onClick={() => { send({ type: "coverageDecision", targetKind: target.kind, targetId: target.id,
        disposition: "excluded", reason, dependency: target.dependency }); setReason(""); }}>Исключить</button>
      {target.confirmable && <button type="button" className={control} disabled={!reason.trim()}
        onClick={() => { send({ type: "coverageDecision", targetKind: "fact", targetId: target.id,
          disposition: "shown", reason, dependency: target.dependency }); setReason(""); }}>Подтвердить изложение</button>}
      {saved && <button type="button" className={control} onClick={() => send({ type: "coverageClear",
        targetKind: target.kind, targetId: target.id })}>Снять решение</button>}</div>}
  </li>;
}

export function CoveragePanel({ state, send, openSource }: Props) {
  const [jobReasons, setJobReasons] = useState<Record<string, string>>({});
  if (!state.project || !state.working) return null;
  const input = { project: state.project, working: state.working, presentation: state.presentation,
    rewriteIssues: state.rewriteIssueDetails, sourceIntegrity: state.sourceIntegrity };
  const review = coverageReview(input);
  function openFact(id: string) {
    const details = document.getElementById("coverage-facts");
    if (details instanceof HTMLDetailsElement) details.open = true;
    window.requestAnimationFrame(() => document.getElementById(`coverage-fact-${id}`)?.scrollIntoView({ block: "nearest" }));
  }
  const jobs = review.blockers.filter((item) => item.code === "MISSING_JOB" && item.jobId);
  return <div className="mt-4 border-t border-outline pt-4 text-sm">
    <h2 className="font-semibold">Покрытие источника и фактов</h2>
    <p className="mt-1 text-muted">{review.blockers.length} препятствий · {review.warnings.filter((item) =>
      !item.acknowledged).length} предупреждений без отметки. Связи и числа не доказывают точность смысла.</p>
    <IssueList title="Исправить" issues={review.blockers.filter((item) => item.group === "fix")}
      facts={review.facts} state={state} send={send} openSource={openSource} openFact={openFact} />
    {jobs.map((item) => <div key={`decision-${item.id}`} className="mt-2 rounded border border-outline p-2">
      <label>Причина исключения работы {jobLabel(state, item.jobId!)}
        <input className={field} maxLength={500} value={jobReasons[item.jobId!] ?? ""}
          onChange={(event) => setJobReasons({ ...jobReasons, [item.jobId!]: event.target.value })} />
      </label><button type="button" className={`${control} mt-2`} disabled={!jobReasons[item.jobId!]?.trim()}
        onClick={() => send({ type: "coverageDecision", targetKind: "job", targetId: item.jobId!,
          disposition: "excluded", reason: jobReasons[item.jobId!] ?? "", dependency: item.dependency })}>Исключить работу</button>
    </div>)}
    {state.working.coverage?.decisions.filter((item) => item.targetKind === "job" &&
      item.disposition === "excluded").map((item) => <div key={`saved-${item.targetId}`}
        className="mt-2 rounded border border-outline p-2" title={item.targetId}>Работа {jobLabel(state, item.targetId)} исключена: {item.reason}
        <button type="button" className={`${control} ml-2`} onClick={() => send({ type: "coverageClear",
          targetKind: "job", targetId: item.targetId })}>Снять исключение</button></div>)}
    <IssueList title="Принять решение" issues={[...review.blockers, ...review.warnings].filter((item) =>
      item.group === "decide")} facts={review.facts} state={state} send={send} openSource={openSource} openFact={openFact} />
    <IssueList title="Сверить смысл" issues={review.warnings.filter((item) => item.group === "check")}
      facts={review.facts} state={state} send={send} openSource={openSource} openFact={openFact} />
    <details id="coverage-facts" className="mt-4"><summary className="cursor-pointer font-semibold">Факты · {review.facts.length}</summary>
      <ul className="mt-2 space-y-2">{review.facts.map((target) => <DecisionRow key={target.id}
        target={target} state={state} send={send} openSource={openSource} />)}</ul></details>
    <details className="mt-4"><summary className="cursor-pointer font-semibold">Фрагменты исходника · {review.units.length}</summary>
      <ul className="mt-2 space-y-2">{review.units.map((target) => <DecisionRow key={target.id}
        target={target} state={state} send={send} openSource={openSource} />)}</ul></details>
    <p className="mt-4 text-xs text-muted">Проверка документа: {review.status === "ready" ?
      "структурных препятствий нет" : "есть структурные препятствия"}.</p>
  </div>;
}
