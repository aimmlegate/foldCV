export type Automaticanalysis = boolean;
/**
 * @maxItems 2
 */
export type Enabledproviders =
  [] | ["codex_cli" | "claude_cli"] | ["codex_cli" | "claude_cli", "codex_cli" | "claude_cli"];
export type Importminutes = number;
export type Projectmegabytes = number;
export type Rewritereasoningeffort =
  ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Schemaversion = 1;
export type Selectedfallbackmodel = string | null;
export type Selectedimportmodel = string | null;
export type Selectedmodel = string | null;
export type Selectedrewritemodel = string | null;
export type Theme = "light" | "dark" | "system";

export interface Preferences {
  automaticAnalysis: Automaticanalysis;
  enabledProviders?: Enabledproviders;
  importMinutes?: Importminutes;
  projectMegabytes?: Projectmegabytes;
  rewriteReasoningEffort?: Rewritereasoningeffort;
  schemaVersion: Schemaversion;
  selectedFallbackModel?: Selectedfallbackmodel;
  selectedImportModel?: Selectedimportmodel;
  selectedModel: Selectedmodel;
  selectedRewriteModel?: Selectedrewritemodel;
  theme: Theme;
}
