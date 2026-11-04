import type { AgentSettings } from "../contracts/generated/agent_settings";
import type { AgentSettingsRequest } from "../contracts/generated/agent_settings_request";
import type { AssistantCapabilitiesV1 } from "../contracts/generated/assistant_capabilities_v1";
import type { AssistantChangeProposalListV1 } from "../contracts/generated/assistant_change_proposal_list_v1";
import type { AssistantChangeProposalV1 } from "../contracts/generated/assistant_change_proposal_v1";
import type { AssistantConversationListV1 } from "../contracts/generated/assistant_conversation_list_v1";
import type { AssistantConversationV1 } from "../contracts/generated/assistant_conversation_v1";
import type { AssistantEventsV1 } from "../contracts/generated/assistant_events_v1";
import type { AssistantMessagesV1 } from "../contracts/generated/assistant_messages_v1";
import type { AssistantRunV1 } from "../contracts/generated/assistant_run_v1";
import { field, optionalText, text } from "../api/fields";
import { sha256Hex } from "../api/hash";
import { ProjectApiFailure, v2Request, type Fetcher } from "../rich/v7-connection";
import { AssistantApi } from "./api";
import type { Port, RunRequest } from "./controller";

/** The template assistant (D141): the resume assistant's runs on its own routes, with no access to resumes. Its
 * proposals are whole YAML texts that the templates screen applies into the editor; replies are parsed by hand. */
export const templatePrefix = "/v2/templates/assistant";
/** The most a run request carries as the editor text (the server's TEMPLATE_TEXT_BYTES); the editor itself takes 2 MiB. */
export const TEMPLATE_TEXT_BYTES = 256 * 1024;
export type TemplateFields = { templateId: string | null; assetsFrom: string | null; text: string; textHash: string; sampleId: string | null };
export type TemplateProposalState = "proposed" | "applied" | "discarded";
export type TemplateProposal = { id: string; conversationId: string; runId: string; templateId: string | null; name: string | null;
  baseHash: string; text: string; summary: string; state: TemplateProposalState };
export type TemplateSample = { sampleId: string; name: string; pages: number | null; unitCount: number };

const states: readonly TemplateProposalState[] = ["proposed", "applied", "discarded"];

export function parseTemplateProposal(value: unknown): TemplateProposal {
  const state = states.find(item => item === field(value, "state"));
  if (!state) throw new ProjectApiFailure("INVALID_RESULT");
  return { id: text(value, "id"), conversationId: text(value, "conversationId"), runId: text(value, "runId"),
    templateId: optionalText(value, "templateId"), name: optionalText(value, "name"), baseHash: text(value, "baseHash"),
    text: text(value, "text"), summary: text(value, "summary"), state };
}
export function parseTemplateProposals(value: unknown): TemplateProposal[] {
  const items = field(value, "items");
  if (!Array.isArray(items)) throw new ProjectApiFailure("INVALID_RESULT");
  return items.map(parseTemplateProposal);
}
export function parseSample(value: unknown): TemplateSample {
  const pages = field(value, "pages"), unitCount = field(value, "unitCount");
  if (pages !== null && !Number.isInteger(pages) || !Number.isInteger(unitCount)) throw new ProjectApiFailure("INVALID_RESULT");
  return { sampleId: text(value, "sampleId"), name: text(value, "name"), pages: pages as number | null, unitCount: unitCount as number };
}

/** Whether the attached sample leaves the composer after a send: it goes with one run only (2026-11-04), so a run
 * that started took it even when a later read failed, and a sample the service no longer keeps must be attached
 * again. `before`: the run shown when Send was pressed. */
export function sampleSpent(before: string | null, after: { run: { id: string } | null; error: string | null }): boolean {
  return after.error === "SAMPLE_NOT_FOUND" || after.run !== null && after.run.id !== before;
}

/** The UTF-8 size of the editor text, what the run limit counts. */
export function textBytes(value: string): number { return new TextEncoder().encode(value).length; }

/** SHA-256 of the UTF-8 text as lower-case hex, the proposal's base hash. */
export function textHash(value: string): Promise<string> { return sha256Hex(new TextEncoder().encode(value)); }

const defaultFetch: Fetcher = (input, init) => fetch(input, init);
const path = (kind: string, id: string, tail = "") => `${templatePrefix}/${kind}/${encodeURIComponent(id)}${tail}`;

export class TemplateAssistantApi implements Port<TemplateFields> {
  readonly projectId = "templates";
  private readonly runs: AssistantApi;
  private readonly sampleNames = new Map<string, string>();
  // Kept for the open screen only: the server stores neither the sample's name on the message nor the run's assets.
  readonly runSamples = new Map<string, string>();
  readonly runAssets = new Map<string, string | null>();
  constructor(private readonly fetcher: Fetcher = defaultFetch) { this.runs = new AssistantApi(this.projectId, fetcher, templatePrefix); }
  settings(): Promise<AgentSettings> { return this.runs.settings(); }
  saveSettings(value: AgentSettingsRequest): Promise<AgentSettings> { return this.runs.saveSettings(value); }
  capabilities(): Promise<AssistantCapabilitiesV1> { return this.runs.capabilities(); }
  conversations(): Promise<AssistantConversationListV1> { return this.runs.conversations(); }
  createConversation(): Promise<AssistantConversationV1> { return this.runs.createConversation(); }
  messages(conversationId: string): Promise<AssistantMessagesV1> { return this.runs.messages(conversationId); }
  events(runId: string, after: number, signal?: AbortSignal): Promise<AssistantEventsV1> { return this.runs.events(runId, after, signal); }
  cancel(runId: string): Promise<AssistantRunV1> { return this.runs.cancel(runId); }
  async submit(conversationId: string, request: RunRequest<TemplateFields>): Promise<AssistantRunV1> {
    const run = await v2Request<AssistantRunV1>(path("conversations", conversationId, "/runs"), "POST", request, this.fetcher);
    this.runAssets.set(run.id, request.assetsFrom);
    const sample = request.sampleId === null ? undefined : this.sampleNames.get(request.sampleId);
    if (sample !== undefined) this.runSamples.set(run.id, sample);
    return run;
  }
  /** The run controller's resume proposals: none here, template proposals have their own list and card. */
  proposals(): Promise<AssistantChangeProposalListV1> { return Promise.resolve({ items: [] }); }
  discard(): Promise<AssistantChangeProposalV1> { return Promise.reject(new ProjectApiFailure("REQUEST_FAILED")); }
  async templateProposals(conversationId: string): Promise<TemplateProposal[]> {
    return parseTemplateProposals(await v2Request<unknown>(path("conversations", conversationId, "/proposals"), "GET", undefined, this.fetcher));
  }
  async decide(proposalId: string, state: "applied" | "discarded"): Promise<TemplateProposal> {
    return parseTemplateProposal(await v2Request<unknown>(path("proposals", proposalId, "/state"), "POST", { state }, this.fetcher));
  }
  /** The extraction worker reads the sample once; the service keeps the summaries of the last three in memory. */
  async uploadSample(file: File): Promise<TemplateSample> {
    const body = new FormData();
    body.append("file", file, file.name);
    const sample = parseSample(await v2Request<unknown>(`${templatePrefix}/samples`, "POST", body, this.fetcher));
    this.sampleNames.set(sample.sampleId, sample.name);
    return sample;
  }
}

/** Where a proposal goes. The shown template must be its target: another one opens first (asking about unsaved
 * edits); a new template opens as an unsaved entry with the text. On the target the editor text is replaced when it
 * still has the hash the run started from, else only after a confirmation. */
export type ApplyStep = { kind: "open"; ask: boolean } | { kind: "replace" } | { kind: "confirm" };
export type ShownTarget = { templateId: string | null; draft: boolean; unsaved: boolean } | null;
/** Whether the editor shows the proposal's target. A new-template proposal refines the unsaved entry when that entry
 * is shown; otherwise it makes one. */
export function onTarget(proposal: Pick<TemplateProposal, "templateId">, shown: ShownTarget): boolean {
  return shown !== null && (proposal.templateId === null ? shown.draft : !shown.draft && shown.templateId === proposal.templateId);
}
export function applyStep(proposal: Pick<TemplateProposal, "templateId" | "baseHash">, shown: ShownTarget, hash: string): ApplyStep {
  if (!onTarget(proposal, shown)) return { kind: "open", ask: shown?.unsaved ?? false };
  return hash === proposal.baseHash ? { kind: "replace" } : { kind: "confirm" };
}

export function proposalTarget(proposal: Pick<TemplateProposal, "templateId" | "name">, names: ReadonlyMap<string, string>): string {
  if (proposal.templateId === null) return `новый шаблон «${proposal.name ?? "Без названия"}»`;
  return names.get(proposal.templateId) ?? proposal.templateId;
}

/** The card: a proposed text can be applied or discarded; one whose base text changed says so and offers «Заменить». */
export type ProposalCard = { heading: string; notice: string | null; apply: boolean; replace: boolean; discard: boolean };
export function proposalCard(proposal: Pick<TemplateProposal, "state">, changed: boolean, busy: boolean): ProposalCard {
  if (proposal.state === "applied") return { heading: "Применено", notice: "Текст перенесён в редактор. Сохраните его там.", apply: false, replace: false, discard: false };
  if (proposal.state === "discarded") return { heading: "Отклонено", notice: null, apply: false, replace: false, discard: false };
  return { heading: "Предложение шаблона", notice: changed ? "Текст изменился после запуска." : null,
    apply: !busy && !changed, replace: !busy && changed, discard: !busy };
}
