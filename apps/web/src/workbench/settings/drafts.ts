import type { Preferences } from "../../contracts/generated/preferences";
import type { RulesSettings } from "../../contracts/generated/rules_settings";
import type { AgentSettings } from "../../contracts/generated/agent_settings";
import type { AgentSettingsRequest } from "../../contracts/generated/agent_settings_request";
import type { SaveRulesRequest } from "../../contracts/generated/save_rules_request";

export type SettingsPart = "model" | "analysis" | "assistant" | "rules";
export type SettingsValues = { model: string | null; automatic: boolean; agentEnabled: boolean; agentModel: string | null; markdown: string };
export type SettingsApi = {
  preferences: () => Promise<Preferences>; rules: () => Promise<RulesSettings>; assistant: () => Promise<AgentSettings>;
  select: (model: string | null) => Promise<string>; analysis: (enabled: boolean) => Promise<Preferences>;
  saveRules: (value: SaveRulesRequest) => Promise<RulesSettings>; saveAssistant: (value: AgentSettingsRequest) => Promise<AgentSettings>;
};
export type SettingsState = {
  preferences: Preferences | null; rules: RulesSettings | null; assistant: AgentSettings | null; draft: SettingsValues;
  loading: boolean; saving: boolean; staleRules: boolean; comparison: boolean; saved: SettingsPart[];
  errors: Partial<Record<SettingsPart, string>>; message: string;
};
const rulesErrors: Record<string, string> = {
  RULES_PRESETS_REQUIRED: "Нужны оба заголовка: ## Preset: shorten и ## Preset: clarify с непустыми инструкциями.",
  RULES_STALE: "Правила изменены в другом окне. Загрузите актуальную версию и сравните со своим текстом.",
  RULES_TOO_LARGE: "Правила превышают 32 КБ. Сократите текст.",
  RULES_INVALID_TEXT: "Проверьте текст правил и управляющие символы.",
};
function message(error: unknown, part: SettingsPart): string {
  const code = error instanceof Error && "code" in error && typeof error.code === "string" ? error.code : "";
  if (part === "rules" && rulesErrors[code]) return rulesErrors[code];
  if (code === "AGENT_SETTINGS_CONFLICT") return "Настройки помощника изменились. Загрузите актуальную версию; ваш выбор останется в форме.";
  if (part === "model") return "Не удалось сохранить модель. Проверьте подключение и выберите доступную модель.";
  return "Не удалось сохранить этот раздел. Черновик остался в форме; повторите действие.";
}

export class SettingsDrafts {
  state: SettingsState = { preferences: null, rules: null, assistant: null,
    draft: { model: null, automatic: true, agentEnabled: false, agentModel: null, markdown: "" },
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
    if (preferences && draft.automatic !== preferences.automaticAnalysis) result.push("analysis");
    if (assistant && (draft.agentEnabled !== assistant.enabled || draft.agentModel !== assistant.selectedAgentModel)) result.push("assistant");
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
      if (!this.state.preferences) { draft.model = preferences.value.selectedModel; draft.automatic = preferences.value.automaticAnalysis;
        this.publish({ preferences: preferences.value }); delete errors.model; delete errors.analysis; }
    } else errors.model = "Не удалось загрузить настройки обработки. Повторите загрузку.";
    if (rules.status === "fulfilled") {
      if (!this.state.rules) { draft.markdown = rules.value.markdown; this.publish({ rules: rules.value }); delete errors.rules; }
    } else errors.rules = "Не удалось загрузить правила. Повторите загрузку.";
    if (assistant.status === "fulfilled") {
      if (!this.state.assistant) { draft.agentEnabled = assistant.value.enabled; draft.agentModel = assistant.value.selectedAgentModel;
        this.publish({ assistant: assistant.value }); delete errors.assistant; }
    } else errors.assistant = "Не удалось загрузить настройки помощника. Повторите загрузку.";
    this.publish({ draft, errors, loading: false });
  }
  cancel(): void {
    if (this.state.saving) return;
    const { preferences, rules, assistant, draft } = this.state;
    this.publish({ draft: { model: preferences ? preferences.selectedModel : draft.model, automatic: preferences?.automaticAnalysis ?? draft.automatic,
      agentEnabled: assistant?.enabled ?? draft.agentEnabled, agentModel: assistant ? assistant.selectedAgentModel : draft.agentModel,
      markdown: rules?.markdown ?? draft.markdown }, errors: this.state.staleRules ? { rules: rulesErrors["RULES_STALE"] ?? "Обновите правила." } : {},
      saved: [], message: "Несохранённые изменения отменены." });
  }
  async reloadRules(): Promise<void> {
    if (this.state.saving || this.state.loading || this.closed) return;
    const epoch = ++this.epoch; this.publish({ loading: true });
    try {
      const rules = await this.api.rules(); if (this.closed || epoch !== this.epoch) return;
      const errors = { ...this.state.errors }; delete errors.rules;
      this.publish({ rules, errors, staleRules: false, comparison: true,
        message: "Актуальные правила загружены. Ваш текст сохранён в форме; сравните версии ниже." });
    } catch { this.publish({ errors: { ...this.state.errors, rules: "Не удалось загрузить правила. Ваш текст остался в форме." } }); }
    finally { if (epoch === this.epoch) this.publish({ loading: false }); }
  }
  async reloadAssistant(): Promise<void> {
    if (this.state.saving || this.state.loading || this.closed) return;
    const epoch = ++this.epoch; this.publish({ loading: true });
    try {
      const assistant = await this.api.assistant(); if (this.closed || epoch !== this.epoch) return;
      const errors = { ...this.state.errors }; delete errors.assistant;
      this.publish({ assistant, errors, message: "Настройки помощника обновлены. Ваш выбор остался в форме." });
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
        } else if (part === "analysis") {
          const preferences = await this.api.analysis(submitted.automatic);
          if (this.state.preferences) this.publish({ preferences: { ...this.state.preferences, automaticAnalysis: preferences.automaticAnalysis },
            draft: { ...this.state.draft, automatic: this.state.draft.automatic === submitted.automatic ? preferences.automaticAnalysis : this.state.draft.automatic } });
        } else if (part === "assistant" && bases.assistant) {
          const assistant = await this.api.saveAssistant({ expectedRevision: bases.assistant.revision, enabled: submitted.agentEnabled, selectedAgentModel: submitted.agentModel });
          this.publish({ assistant, draft: { ...this.state.draft,
            agentEnabled: this.state.draft.agentEnabled === submitted.agentEnabled ? assistant.enabled : this.state.draft.agentEnabled,
            agentModel: this.state.draft.agentModel === submitted.agentModel ? assistant.selectedAgentModel : this.state.draft.agentModel } });
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
