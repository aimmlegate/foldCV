import type { Block } from "../contracts/generated/project";
import type { Action, EditorState } from "./state";
import type { RewriteView } from "./rewriteWorkflow";
import { control, field, primary } from "./styles";

export function RewriteControls({ state, block, view, ready, instruction, onInstruction, onRequest, onCancel,
  unapplied, send }: {
  state: EditorState; block: Block; view: RewriteView; ready: boolean; instruction: string;
  onInstruction: (value: string) => void; onRequest: () => void; onCancel: () => void;
  unapplied: boolean; send: (action: Action) => void;
}) {
  if (!state.working || !["profile", "job_prose"].includes(block.kind)) return null;
  const proposal = state.rewriteProposal?.result.blockId === block.id ? state.rewriteProposal : null;
  return <div className="mb-5 rounded border border-outline p-3">
    <label htmlFor="rewrite-instruction" className="mb-1 block text-sm font-semibold">Уточнение для предложения</label>
    <input id="rewrite-instruction" className={field} maxLength={2000} value={instruction}
      onChange={(event) => onInstruction(event.target.value)} />
    <div className="mt-2 flex gap-2"><button type="button" className={primary}
      disabled={!ready || view.pending || block.state.locked || unapplied} onClick={onRequest}>Предложить новую формулировку</button>
      {view.pending && <button type="button" className={control} onClick={onCancel}>Отменить запрос</button>}</div>
    {!ready && <p className="mt-1 text-xs text-muted">Предложения станут доступны после безопасного подключения генерации.</p>}
    {view.error && <p role="alert" className="mt-2 text-sm text-danger">{view.error}</p>}
    {state.rewriteIssues[block.id]?.map((issue, index) =>
      <p key={index} role="alert" className="mt-2 text-sm text-danger">{issue}</p>)}
    {proposal && <div className="mt-3 space-y-2 border-t border-outline pt-3">
      <p className="text-sm font-semibold">До</p><p className="whitespace-pre-wrap text-sm">{proposal.before}</p>
      <p className="text-sm font-semibold">После</p><p className="whitespace-pre-wrap text-sm">{proposal.result.replacementText}</p>
      {proposal.result.issues.map((issue, index) => <p key={index} role="alert" className="text-sm text-danger">{issue.factId}: {issue.message}</p>)}
      <div className="flex gap-2"><button type="button" className={primary} onClick={() => send({ type: "rewriteApply", id: block.id })}>Применить предложение</button>
        <button type="button" className={control} onClick={() => send({ type: "rewriteDiscard" })}>Отклонить предложение</button></div>
    </div>}
  </div>;
}
