import type { Block } from "../contracts/generated/project";
import type { RewriteRequest } from "../contracts/generated/rewrite_request";
import type { RewriteResult } from "../contracts/generated/rewrite_result";
import type { RewritePreflightFailure } from "../contracts/generated/rewrite_preflight_failure";
import { validateRewritePreflightFailure, validateRewriteRequest, validateRewriteResult } from "../contracts/validate";
import { completed } from "../facts/draftWorkflow";
import { recentJobIds, scopedFactsForBlock, type EditorState } from "./state";

export type RewriteView = { pending: boolean; error: string | null; completed: number };
const encoder = new TextEncoder();

function hex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function buildRewriteRequest(state: EditorState, block: Block, instruction: string): Promise<RewriteRequest> {
  const project = state.project;
  if (!project || !state.presentation || !state.working || !["profile", "job_prose"].includes(block.kind) ||
      !block.visible || block.state.locked || instruction.length > 2_000 ||
      state.drafts[block.id] !== undefined && state.drafts[block.id] !== block.state.text)
    throw new Error("Выберите доступный блок и примените введённый текст перед запросом.");
  if (block.kind === "job_prose") {
    const jobId = Object.entries(state.presentation.jobProseBlocks).find(([, id]) => id === block.id)?.[0];
    if (!jobId || !recentJobIds(project).has(jobId)) throw new Error("Переписывать можно только недавнюю работу.");
  }
  const facts = scopedFactsForBlock(state, block);
  const [first, ...rest] = facts;
  if (!first) throw new Error("Для этого блока нет связанных фактов.");
  const { dependencyHash, excerpts } = await rewriteDependencies(state, block);
  const request: RewriteRequest = { transportVersion: 1, baseRevision: project.revision,
    blockId: block.id, blockKind: block.kind === "profile" ? "profile" : "job_prose",
    blockRevision: block.revision, dependencyHash,
    currentText: block.state.text, instruction: instruction.trim(), sourceLanguage: state.presentation.sourceLanguage,
    contentPolicyVersion: block.contentPolicyVersion, facts: [first, ...rest],
    requiredFactIds: facts.filter((fact) => fact.importance !== "minor" || fact.origin === "user" ||
      fact.kind === "metric" || fact.kind === "leadership").map((fact) => fact.id),
    excerpts };
  if (!validateRewriteRequest(request) || encoder.encode(JSON.stringify(request)).length > 65_536)
    throw new Error("Контекст блока превышает предел запроса.");
  return request;
}

async function rewriteDependencies(state: EditorState, block: Block): Promise<{
  dependencyHash: string; excerpts: { factId: string; text: string }[]
}> {
  const project = state.project;
  if (!project || !state.working) throw new Error("Проект не открыт.");
  const facts = scopedFactsForBlock(state, block);
  const factIds = new Set(facts.map((fact) => fact.id));
  const corrected = new Map(Object.entries(state.working.sheet.userCorrections ?? {}).map(([sourceId, userId]) => [userId, sourceId]));
  const excerpts = facts.flatMap((fact) => {
    const evidence = corrected.has(fact.id) ? state.working?.sheet.facts.find((item) =>
      item.id === corrected.get(fact.id))?.evidence ?? [] : fact.evidence;
    return evidence.flatMap((ref) => project.sources.flatMap((source) => source.id === ref.sourceId ?
      source.units.filter((unit) => unit.id === (ref.unitId.startsWith("view_") ? ref.unitId :
        `view_${ref.sourceId}_${ref.unitId}`)).map((unit) => ({ factId: fact.id, text: unit.text })) : []));
  });
  const uniqueExcerpts = excerpts.filter((item, index) => excerpts.findIndex((candidate) =>
    candidate.factId === item.factId && candidate.text === item.text) === index);
  const dependencies = JSON.stringify({ blockId: block.id, blockRevision: block.revision,
    facts: facts.map((fact) => [fact.id, fact.revision, fact.value]), excerpts: uniqueExcerpts,
    sourceFingerprint: state.working.sheet.sourceFingerprint });
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(dependencies));
  return { dependencyHash: hex(new Uint8Array(digest)), excerpts: uniqueExcerpts.filter((item) => factIds.has(item.factId)) };
}

export async function currentRewriteDependencyHash(state: EditorState, block: Block): Promise<string> {
  return (await rewriteDependencies(state, block)).dependencyHash;
}

export class RewriteWorkflow {
  private epoch = 0;
  private abort: AbortController | null = null;
  view: RewriteView = { pending: false, error: null, completed: 0 };

  constructor(private readonly onChange: (view: RewriteView) => void,
              private readonly onComplete: (result: RewriteResult, request: RewriteRequest) => void,
              private readonly onBlocked: (result: RewritePreflightFailure, loadId: string) => void,
              private readonly request: typeof fetch = (input, init) => fetch(input, init)) {}

  private publish(view: RewriteView): void { this.view = view; this.onChange(view); }

  cancel(): void {
    this.epoch += 1;
    this.abort?.abort();
    this.abort = null;
    if (this.view.pending) this.publish({ ...this.view, pending: false, error: null });
  }

  async run(state: EditorState, block: Block, instruction: string, isCurrent: () => boolean): Promise<void> {
    this.cancel();
    const epoch = this.epoch;
    const abort = new AbortController();
    this.abort = abort;
    try {
      const payload = await buildRewriteRequest(state, block, instruction);
      if (epoch !== this.epoch || !isCurrent()) return;
      this.publish({ ...this.view, pending: true, error: null });
      const response = await this.request("/v1/facts/rewrite", { method: "POST", credentials: "same-origin",
        cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: abort.signal });
      if (!response.ok) {
        const problem: unknown = await response.text().then((body) =>
          encoder.encode(body).length <= 65_536 ? JSON.parse(body) as unknown : null).catch(() => null);
        if (validateRewritePreflightFailure(problem) && problem.baseRevision === payload.baseRevision &&
            problem.blockId === payload.blockId && problem.blockRevision === payload.blockRevision &&
            problem.dependencyHash === payload.dependencyHash &&
            problem.issues.every((issue) => payload.requiredFactIds.includes(issue.factId))) {
          if (epoch !== this.epoch || !isCurrent()) return;
          this.onBlocked(problem, state.loadId!);
          throw new Error("Блок или все его факты содержат контактные данные. Исправьте текст или факты перед запросом.");
        }
        throw new Error("operation rejected");
      }
      const result: unknown = await completed(response, abort.signal);
      if (epoch !== this.epoch || !isCurrent()) return;
      if (!validateRewriteResult(result) || result.baseRevision !== payload.baseRevision ||
          result.blockId !== payload.blockId || result.blockRevision !== payload.blockRevision ||
          result.dependencyHash !== payload.dependencyHash ||
          !result.factIds.every((id) => payload.facts.some((fact) => fact.id === id)))
        throw new Error("invalid rewrite result");
      this.onComplete(result, payload);
      this.publish({ ...this.view, pending: false, completed: this.view.completed + 1, error: null });
    } catch (error) {
      const known = ["Выберите доступный блок", "Переписывать можно", "Для этого блока нет", "Контекст блока превышает",
        "Блок или все его факты содержат"];
      if (epoch === this.epoch) this.publish({ ...this.view, pending: false,
        error: error instanceof Error && known.some((text) => error.message.startsWith(text)) ? error.message :
          "Не удалось получить предложение. Принятый текст сохранён." });
    } finally { if (this.abort === abort) this.abort = null; }
  }
}
