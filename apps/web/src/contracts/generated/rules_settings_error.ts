export type Code =
  | "RULES_PRESETS_REQUIRED"
  | "RULES_STALE"
  | "RULES_TOO_LARGE"
  | "RULES_INVALID_TEXT"
  | "RULES_LOAD_FAILED"
  | "RULES_SAVE_FAILED"
  | "RULES_UNSAFE_STORAGE";
export type Retryable = false;
export type Stage = "rules";
export type Requiredheadings = ("## Preset: shorten" | "## Preset: clarify")[];

export interface RulesSettingsError {
  error: RulesErrorPayload;
  requiredHeadings: Requiredheadings;
}
export interface RulesErrorPayload {
  code: Code;
  retryable: Retryable;
  stage: Stage;
}
