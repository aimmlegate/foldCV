import { knownErrorMessage } from "../../errors/messages";
import type { Preferences } from "../../contracts/generated/preferences";
import type { RulesSettings } from "../../contracts/generated/rules_settings";
import type { AgentSettings } from "../../contracts/generated/agent_settings";
import type { AgentSettingsRequest } from "../../contracts/generated/agent_settings_request";
import type { SaveRulesRequest } from "../../contracts/generated/save_rules_request";
import type { SaveLimitsPreference } from "../../contracts/generated/save_limits_preference";
import preferencesSchema from "../../../../../contracts/json-schema/preferences.schema.json" with { type: "json" };

/** Defaults and ranges come from the Python preferences contract. */
export const limitRanges = { importMinutes: preferencesSchema.properties.importMinutes, projectMegabytes: preferencesSchema.properties.projectMegabytes };
type Limit = keyof typeof limitRanges;
function limit(preferences: Preferences, key: Limit): string { return String(preferences[key] ?? limitRanges[key].default); }

export type SettingsPart = "reasoning" | "model" | "rewrite" | "import" | "fallback" | "limits" | "assistant" | "rules";
export type SettingsValues = { reasoning: NonNullable<Preferences["rewriteReasoningEffort"]> | null; model: string | null; rewriteModel: string | null; importModel: string | null; fallbackModel: string | null; agentEnabled: boolean; agentModel: string | null; agentEffort: NonNullable<AgentSettings["reasoningEffort"]> | null; markdown: string;
  importMinutes: string; projectMegabytes: string };
export type SettingsApi = {
  preferences: () => Promise<Preferences>; rules: () => Promise<RulesSettings>; assistant: () => Promise<AgentSettings>;
  select: (model: string | null) => Promise<string>;
  selectRewrite: (model: string | null) => Promise<Preferences>;
  selectImport: (model: string | null) => Promise<Preferences>;
  selectFallback: (model: string | null) => Promise<Preferences>;
  saveReasoning: (model: string | null, effort: SettingsValues["reasoning"]) => Promise<Preferences>;
  saveLimits: (value: SaveLimitsPreference) => Promise<Preferences>;
  saveRules: (value: SaveRulesRequest) => Promise<RulesSettings>; saveAssistant: (value: AgentSettingsRequest) => Promise<AgentSettings>;
};
export type SettingsState = {
  preferences: Preferences | null; rules: RulesSettings | null; assistant: AgentSettings | null; draft: SettingsValues;
  loading: boolean; saving: boolean; staleRules: boolean; comparison: boolean; saved: SettingsPart[];
  errors: Partial<Record<SettingsPart, string>>; message: string;
};
function message(error: unknown, part: SettingsPart): string {
  const code = error instanceof Error && "code" in error && typeof error.code === "string" ? error.code : "";
  if (part === "limits" && code === "INVALID_REQUEST") return "Не удалось сохранить лимиты. Укажите целые числа в допустимых пределах.";
  const known = knownErrorMessage(code);
  if (known) return known;
  if (part === "reasoning") return "Не удалось сохранить уровень рассуждений. Проверьте, что модель его поддерживает.";
  if (part === "model" || part === "rewrite" || part === "import" || part === "fallback") return "Не удалось сохранить модель. Проверьте подключение и выберите доступную модель.";
  return "Не удалось сохранить. Правки остались в форме, повторите.";
}

export class SettingsDrafts {
  state: SettingsState = { preferences: null, rules: null, assistant: null,
    draft: { reasoning: null, model: null, rewriteModel: null, importModel: null, fallbackModel: null, agentEnabled: true, agentModel: null, agentEffort: null, markdown: "",
      importMinutes: String(limitRanges.importMinutes.default), projectMegabytes: String(limitRanges.projectMegabytes.default) },
    loading: false, saving: false, staleRules: false, comparison: false, saved: [], errors: {}, message: "" };
  private closed = false;
  private epoch = 0;
  constructor(private readonly api: SettingsApi, private readonly changed: (state: SettingsState) => void) {}
  private publish(patch: Partial<SettingsState>): void {
    if (!this.closed) { this.state = { ...this.state, ...patch }; this.changed(this.state); }
  }
  get ready(): boolean { return !!this.state.preferences && !!this.state.rules && !!this.state.assistant; }
  get dirty(): SettingsPart[] {
    const { preferences, rules, assistant, draft } = this.state, result: SettingsPart[] = [];
    if (preferences && draft.model !== preferences.selectedModel) result.push("model");
    if (preferences && draft.rewriteModel !== (preferences.selectedRewriteModel ?? null)) result.push("rewrite");
    // The level belongs to the model rewriting runs on: the rewrite model, else the processing model.
    if (preferences && (draft.reasoning !== (preferences.rewriteReasoningEffort ?? null) || draft.reasoning !== null
        && (draft.rewriteModel ?? draft.model) !== (preferences.selectedRewriteModel ?? preferences.selectedModel))) result.push("reasoning");
    if (preferences && draft.importModel !== (preferences.selectedImportModel ?? null)) result.push("import");
    if (preferences && draft.fallbackModel !== (preferences.selectedFallbackModel ?? null)) result.push("fallback");
    if (preferences && (draft.importMinutes !== limit(preferences, "importMinutes") || draft.projectMegabytes !== limit(preferences, "projectMegabytes")))
      result.push("limits");
    if (assistant && (draft.agentEnabled !== assistant.enabled || draft.agentModel !== assistant.selectedAgentModel
        || draft.agentEffort !== (assistant.reasoningEffort ?? null))) result.push("assistant");
    if (rules && draft.markdown !== rules.markdown) result.push("rules");
    return result;
  }
  change<K extends keyof SettingsValues>(key: K, value: SettingsValues[K]): void {
    this.publish({ draft: { ...this.state.draft, [key]: value }, message: "" });
  }
  async load(): Promise<void> {
    if (this.state.saving || this.state.loading || this.closed) return;
    const epoch = ++this.epoch; this.publish({ loading: true });
    const [preferences, rules, assistant] = await Promise.allSettled([this.api.preferences(), this.api.rules(), this.api.assistant()]);
    if (this.closed || epoch !== this.epoch) return;
    const draft = { ...this.state.draft }, errors = { ...this.state.errors };
    if (preferences.status === "fulfilled") {
      if (!this.state.preferences) { draft.model = preferences.value.selectedModel;
        draft.rewriteModel = preferences.value.selectedRewriteModel ?? null;
        draft.importModel = preferences.value.selectedImportModel ?? null;
        draft.fallbackModel = preferences.value.selectedFallbackModel ?? null;
        draft.reasoning = preferences.value.rewriteReasoningEffort ?? null;
        draft.importMinutes = limit(preferences.value, "importMinutes"); draft.projectMegabytes = limit(preferences.value, "projectMegabytes");
        this.publish({ preferences: preferences.value }); delete errors.model; }
    } else errors.model = "Не удалось загрузить настройки обработки. Повторите загрузку.";
    if (rules.status === "fulfilled") {
      if (!this.state.rules) { draft.markdown = rules.value.markdown; this.publish({ rules: rules.value }); delete errors.rules; }
    } else errors.rules = "Не удалось загрузить команды. Повторите загрузку.";
    if (assistant.status === "fulfilled") {
      if (!this.state.assistant) { draft.agentEnabled = assistant.value.enabled; draft.agentModel = assistant.value.selectedAgentModel;
        draft.agentEffort = assistant.value.reasoningEffort ?? null;
        this.publish({ assistant: assistant.value }); delete errors.assistant; }
    } else errors.assistant = "Не удалось загрузить настройки помощника. Повторите загрузку.";
    this.publish({ draft, errors, loading: false });
  }
  cancel(): void {
    if (this.state.saving) return;
    const { preferences, rules, assistant, draft } = this.state;
    this.publish({ draft: { reasoning: preferences ? preferences.rewriteReasoningEffort ?? null : draft.reasoning, model: preferences ? preferences.selectedModel : draft.model,
      rewriteModel: preferences ? preferences.selectedRewriteModel ?? null : draft.rewriteModel,
      importModel: preferences ? preferences.selectedImportModel ?? null : draft.importModel,
      fallbackModel: preferences ? preferences.selectedFallbackModel ?? null : draft.fallbackModel,
      importMinutes: preferences ? limit(preferences, "importMinutes") : draft.importMinutes,
      projectMegabytes: preferences ? limit(preferences, "projectMegabytes") : draft.projectMegabytes,
      agentEnabled: assistant?.enabled ?? draft.agentEnabled, agentModel: assistant ? assistant.selectedAgentModel : draft.agentModel,
      agentEffort: assistant ? assistant.reasoningEffort ?? null : draft.agentEffort,
      markdown: rules?.markdown ?? draft.markdown }, errors: this.state.staleRules ? { rules: knownErrorMessage("RULES_STALE") ?? "Обновите правила." } : {},
      saved: [], message: "Правки отменены." });
  }
  /** Adopts preferences saved elsewhere (the rewrite popover); unsaved edits stay. */
  async refreshPreferences(): Promise<void> {
    if (this.state.saving || this.state.loading || this.closed || !this.state.preferences) return;
    const epoch = this.epoch, preferences = await this.api.preferences().catch(() => null);
    if (!preferences || this.closed || epoch !== this.epoch || this.state.saving || this.state.loading) return;
    const dirty = this.dirty, draft = { ...this.state.draft };
    if (!dirty.includes("model")) draft.model = preferences.selectedModel;
    if (!dirty.includes("rewrite")) draft.rewriteModel = preferences.selectedRewriteModel ?? null;
    if (!dirty.includes("reasoning")) draft.reasoning = preferences.rewriteReasoningEffort ?? null;
    if (!dirty.includes("import")) draft.importModel = preferences.selectedImportModel ?? null;
    if (!dirty.includes("fallback")) draft.fallbackModel = preferences.selectedFallbackModel ?? null;
    if (!dirty.includes("limits")) { draft.importMinutes = limit(preferences, "importMinutes"); draft.projectMegabytes = limit(preferences, "projectMegabytes"); }
    this.publish({ preferences, draft });
  }
  async reloadRules(): Promise<void> {
    if (this.state.saving || this.state.loading || this.closed) return;
    const epoch = ++this.epoch; this.publish({ loading: true });
    try {
      const rules = await this.api.rules(); if (this.closed || epoch !== this.epoch) return;
      const errors = { ...this.state.errors }; delete errors.rules;
      this.publish({ rules, errors, staleRules: false, comparison: true,
        message: "Сохранённая версия загружена ниже. Ваш текст остался в форме." });
    } catch { this.publish({ errors: { ...this.state.errors, rules: "Не удалось загрузить команды. Ваш текст остался в форме." } }); }
    finally { if (epoch === this.epoch) this.publish({ loading: false }); }
  }
  async reloadAssistant(): Promise<void> {
    if (this.state.saving || this.state.loading || this.closed) return;
    const epoch = ++this.epoch; this.publish({ loading: true });
    try {
      const assistant = await this.api.assistant(); if (this.closed || epoch !== this.epoch) return;
      const errors = { ...this.state.errors }; delete errors.assistant;
      this.publish({ assistant, errors, message: "Настройки помощника загружены. Ваш выбор остался в форме." });
    } catch { this.publish({ errors: { ...this.state.errors, assistant: "Не удалось загрузить настройки помощника." } }); }
    finally { if (epoch === this.epoch) this.publish({ loading: false }); }
  }
  async save(): Promise<void> {
    if (this.state.saving || this.state.loading || this.closed) return;
    const parts = this.dirty, submitted = { ...this.state.draft }, bases = this.state;
    const errors = { ...this.state.errors }; for (const part of parts) delete errors[part];
    this.publish({ saving: true, errors, saved: [], message: "" });
    for (const part of parts) {
      if (this.closed) break;
      try {
        if (part === "model") {
          const model = await this.api.select(submitted.model);
          if (this.state.preferences) this.publish({ preferences: { ...this.state.preferences, selectedModel: model },
            draft: { ...this.state.draft, model: this.state.draft.model === submitted.model ? model : this.state.draft.model } });
        } else if (part === "rewrite") {
          const preferences = await this.api.selectRewrite(submitted.rewriteModel);
          const model = preferences.selectedRewriteModel ?? null, reasoning = preferences.rewriteReasoningEffort ?? null;
          // Python drops a level the new model lacks; a level not edited here follows that.
          if (this.state.preferences) this.publish({ preferences: { ...this.state.preferences, selectedRewriteModel: model, rewriteReasoningEffort: reasoning },
            draft: { ...this.state.draft, rewriteModel: this.state.draft.rewriteModel === submitted.rewriteModel ? model : this.state.draft.rewriteModel,
              reasoning: parts.includes("reasoning") ? this.state.draft.reasoning : reasoning } });
        } else if (part === "reasoning") {
          const preferences = await this.api.saveReasoning(submitted.rewriteModel ?? submitted.model, submitted.reasoning);
          const reasoning = preferences.rewriteReasoningEffort ?? null;
          if (this.state.preferences) this.publish({ preferences: { ...this.state.preferences, rewriteReasoningEffort: reasoning },
            draft: { ...this.state.draft, reasoning: this.state.draft.reasoning === submitted.reasoning ? reasoning : this.state.draft.reasoning } });
        } else if (part === "import") {
          const preferences = await this.api.selectImport(submitted.importModel);
          const model = preferences.selectedImportModel ?? null;
          if (this.state.preferences) this.publish({ preferences: { ...this.state.preferences, selectedImportModel: model },
            draft: { ...this.state.draft, importModel: this.state.draft.importModel === submitted.importModel ? model : this.state.draft.importModel } });
        } else if (part === "fallback") {
          const preferences = await this.api.selectFallback(submitted.fallbackModel);
          const model = preferences.selectedFallbackModel ?? null;
          if (this.state.preferences) this.publish({ preferences: { ...this.state.preferences, selectedFallbackModel: model },
            draft: { ...this.state.draft, fallbackModel: this.state.draft.fallbackModel === submitted.fallbackModel ? model : this.state.draft.fallbackModel } });
        } else if (part === "limits") {
          // Invalid text goes to Python as is; its rejection is shown on this section.
          const preferences = await this.api.saveLimits({ importMinutes: Number(submitted.importMinutes), projectMegabytes: Number(submitted.projectMegabytes) });
          const minutes = limit(preferences, "importMinutes"), megabytes = limit(preferences, "projectMegabytes");
          if (this.state.preferences) this.publish({ preferences: { ...this.state.preferences, importMinutes: Number(minutes), projectMegabytes: Number(megabytes) },
            draft: { ...this.state.draft,
              importMinutes: this.state.draft.importMinutes === submitted.importMinutes ? minutes : this.state.draft.importMinutes,
              projectMegabytes: this.state.draft.projectMegabytes === submitted.projectMegabytes ? megabytes : this.state.draft.projectMegabytes } });
        } else if (part === "assistant" && bases.assistant) {
          const assistant = await this.api.saveAssistant({ expectedRevision: bases.assistant.revision, enabled: submitted.agentEnabled,
            selectedAgentModel: submitted.agentModel, reasoningEffort: submitted.agentEffort });
          this.publish({ assistant, draft: { ...this.state.draft,
            agentEnabled: this.state.draft.agentEnabled === submitted.agentEnabled ? assistant.enabled : this.state.draft.agentEnabled,
            agentModel: this.state.draft.agentModel === submitted.agentModel ? assistant.selectedAgentModel : this.state.draft.agentModel,
            agentEffort: this.state.draft.agentEffort === submitted.agentEffort ? assistant.reasoningEffort ?? null : this.state.draft.agentEffort } });
        } else if (part === "rules" && bases.rules) {
          if (bases.staleRules) throw Object.assign(new Error("stale"), { code: "RULES_STALE" });
          const rules = await this.api.saveRules({ baseRevision: bases.rules.revision, markdown: submitted.markdown });
          this.publish({ rules, comparison: false, draft: { ...this.state.draft,
            markdown: this.state.draft.markdown === submitted.markdown ? rules.markdown : this.state.draft.markdown } });
        }
        this.publish({ saved: [...this.state.saved, part] });
      } catch (error) {
        this.publish({ errors: { ...this.state.errors, [part]: message(error, part) }, staleRules: this.state.staleRules ||
          part === "rules" && error instanceof Error && "code" in error && error.code === "RULES_STALE" });
      }
    }
    this.publish({ saving: false });
  }
  close(): void { this.closed = true; ++this.epoch; }
}
