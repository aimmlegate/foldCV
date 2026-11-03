import { applyStep, textHash, type TemplateProposal } from "../../assistant/template";
import { shownId, unsaved, type ShownTemplate } from "./studio";

/** "changed": the target's text differs from the run's base, so only a forced replace goes on. */
export type ApplyOutcome = "applied" | "changed" | "cancelled";
/** The templates screen as Apply needs it. */
export type ApplyEditor = {
  current: () => { shown: ShownTemplate | null; text: string };
  /** Asks before unsaved edits of the shown template may be dropped. */
  mayLeave: () => Promise<boolean>;
  /** Shows a saved template and returns its text. */
  open: (templateId: string) => Promise<string>;
  showDraft: (name: string, assetsFrom: string | null, text: string) => void;
  renameDraft: (name: string) => void;
  replace: (text: string) => void;
};

/** Apply never saves: the text goes into the editor of the proposal's target (see `applyStep`). A new template
 * uses the assets of the run's template, else of the shown one. */
export async function applyProposal(proposal: TemplateProposal, force: boolean, runAssets: string | null, editor: ApplyEditor): Promise<ApplyOutcome> {
  const { shown, text } = editor.current();
  const step = applyStep(proposal, shown && { templateId: shownId(shown), draft: shown.kind === "draft", unsaved: unsaved(shown, text) }, await textHash(text));
  if (step.kind === "open") {
    if (step.ask && !await editor.mayLeave()) return "cancelled";
    if (proposal.templateId === null) {
      editor.showDraft(proposal.name ?? "Новый шаблон", runAssets ?? shownId(shown) ?? (shown?.kind === "draft" ? shown.assetsFrom : null), proposal.text);
      return "applied";
    }
    const opened = await editor.open(proposal.templateId);
    if (!force && await textHash(opened) !== proposal.baseHash) return "changed";
  } else if (step.kind === "confirm" && !force) return "changed";
  if (shown?.kind === "draft" && proposal.templateId === null && proposal.name) editor.renameDraft(proposal.name);
  editor.replace(proposal.text);
  return "applied";
}
