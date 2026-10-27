import assert from "node:assert/strict";
import test from "node:test";
import { AgentApiFailure } from "../src/assistant/api";
import { AssistantController, type AssistantEditor, type AssistantView } from "../src/assistant/controller";
import type { AssistantApplyResultV1 } from "../src/contracts/generated/assistant_apply_result_v1";
import { event, fakeApi, message, proposal, run } from "./support/assistant";

const editor = (apply: AssistantEditor["applyProposal"] = () => Promise.reject(new Error("unexpected apply")),
  actionApplied?: AssistantEditor["actionApplied"]): AssistantEditor => ({ applyProposal: apply, ...(actionApplied ? { actionApplied } : {}) });
function until(controller: AssistantController, done: (view: AssistantView) => boolean): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("view never matched")), 2000);
    const check = () => { if (done(controller.view)) { clearTimeout(timer); resolve(); } else setTimeout(check, 5); };
    check();
  });
}

test("a run is followed by one long-poll loop that advances its cursor and ends with the run", async () => {
  const { api, calls, state } = fakeApi([[event(1, "run.state_changed", { state: "running", error: null, savedBatchId: null, outcomeUnknown: false })],
    [event(2, "message.delta", { text: "Про" }), event(3, "message.delta", { text: "верено." })], []]);
  const views: AssistantView[] = [], controller = new AssistantController(api, editor(), view => views.push(view), 1);
  try {
    await controller.init(); controller.draft("Проверь резюме");
    state.messages = [message("user", "Проверь резюме"), message("assistant", "Проверено.")];
    await controller.send();
    await until(controller, view => view.run?.state === "completed");
    assert.deepEqual(calls.events, [0, 1, 3, 3], "each poll starts after the last seen event");
    assert.equal(calls.peakEvents, 1, "never two polls at once");
    assert.ok(views.some(view => view.partial === "Проверено."), "deltas stream into the partial answer");
    await until(controller, view => view.messages.length === 2 && view.partial === "");
    const polls = calls.events.length;
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(calls.events.length, polls, "no poll after the run ended");
    assert.equal(controller.active, false);
  } finally { controller.close(); }
});

test("Stop cancels once and waits for the loop to see the run end", async () => {
  const pending = Array.from({ length: 50 }, (_, index) => [event(index + 1, "activity.updated", { itemId: "summary", kind: "summary", text: "Читаю" })]);
  const { api, calls } = fakeApi(pending);
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Сократи текст"); await controller.send();
    assert.equal(controller.active, true);
    await controller.stop();
    assert.equal(calls.cancel, 1);
    assert.equal(controller.view.run?.state, "cancelled");
    assert.equal(controller.active, false);
  } finally { controller.close(); }
});

test("a lost send reply retries the same request; a refusal drops it", async () => {
  const { api, calls, state } = fakeApi([[]]);
  state.submitFailures = 1;
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    assert.equal(controller.view.pendingSend, true);
    await controller.send();
    assert.equal(calls.submit.length, 2);
    assert.equal(calls.submit[0]?.clientRequestId, calls.submit[1]?.clientRequestId);
    assert.equal(controller.view.pendingSend, false);
    await until(controller, view => view.run?.state === "completed");
    api.submit = () => Promise.reject(new AgentApiFailure("ASSISTANT_RUN_ACTIVE", 409));
    controller.draft("Ещё раз"); await controller.send();
    assert.equal(controller.view.pendingSend, false);
    assert.equal(controller.view.error, "ASSISTANT_RUN_ACTIVE");
  } finally { controller.close(); }
});

test("a reopened drawer restores the conversation, keeps its last messages and follows an unfinished run", async () => {
  const { api, calls, state } = fakeApi([[], []]);
  state.messages = [message("user", "Сократи текст", "run-1")];
  state.runs = [run("running")];
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init();
    assert.equal(controller.view.conversationId, "conversation-1");
    assert.deepEqual(controller.view.messages.map(item => item.text), ["Сократи текст"]);
    await until(controller, view => view.run?.state === "completed");
    assert.ok(calls.events.length >= 1, "the unfinished run is polled again");
    controller.draft("Повтори"); await controller.send();
    assert.equal(calls.submit.length, 1);
  } finally { controller.close(); }
});

test("Apply sends the edits flag, adopts an applied proposal and reports refusals", async () => {
  const { api, state } = fakeApi();
  const draft = proposal();
  state.proposals = [draft];
  const seen: boolean[] = [];
  let reply: () => Promise<AssistantApplyResultV1> = () => Promise.reject(new AgentApiFailure("ASSISTANT_EDITS_OFF", 409));
  const controller = new AssistantController(api, editor((_id, allowEdits) => { seen.push(allowEdits); return reply(); }), () => {}, 1);
  try {
    await controller.init();
    controller.flags({ allowEdits: false, allowWeb: false });
    await controller.applyProposal(draft);
    assert.deepEqual(seen, [false]);
    assert.equal(controller.view.error, "ASSISTANT_EDITS_OFF");
    assert.equal(controller.view.proposals[0]?.state, "draft");

    reply = () => Promise.reject(new AgentApiFailure("ASSISTANT_PROPOSAL_STALE", 409, { targets: ["block-paper-a"] }));
    controller.flags({ allowEdits: true, allowWeb: false });
    await controller.applyProposal(draft);
    assert.equal(controller.view.error, "ASSISTANT_PROPOSAL_STALE");
    assert.deepEqual(controller.view.staleProposals, ["proposal-1"]);

    const applied = { ...draft, state: "applied" as const, appliedRevision: 2 };
    reply = () => { state.proposals = [applied]; return Promise.resolve({ proposal: applied, edit: null, action: null }); };
    await controller.applyProposal(draft);
    assert.equal(controller.view.proposals[0]?.state, "applied");
    assert.equal(controller.view.proposalBusy, null);
  } finally { controller.close(); }
});

test("a project action result goes to the editor, and Discard keeps the document", async () => {
  const { api, calls, state } = fakeApi();
  const rename = proposal({ id: "proposal-2", kind: "action", ops: [{ op: "action", action: "rename", value: "Новое имя", targetId: null }] });
  state.proposals = [rename, proposal()];
  const actions: string[] = [];
  const controller = new AssistantController(api, editor(() => Promise.resolve({ proposal: { ...rename, state: "applied" }, edit: null,
    action: { action: "rename", title: "Новое имя", archived: null, deleted: false } }), action => { actions.push(action.action); return Promise.resolve(); }), () => {}, 1);
  try {
    await controller.init();
    await controller.applyProposal(rename);
    assert.deepEqual(actions, ["rename"]);
    const second = controller.view.proposals.find(item => item.id === "proposal-1");
    assert.ok(second);
    await controller.discardProposal(second);
    assert.deepEqual(calls.discard, ["proposal-1"]);
    assert.equal(controller.view.proposals.find(item => item.id === "proposal-1")?.state, "discarded");
  } finally { controller.close(); }
});

test("export links, sources and proposals arrive through run events", async () => {
  const { api, state } = fakeApi([[event(1, "file.ready", { id: "file-1" }), event(2, "proposal.ready", { id: "proposal-1" })], []]);
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Экспортируй DOCX");
    state.files = [{ id: "file-1", format: "docx", url: "/v2/projects/template-project/assistant/files/file-1", filename: "resume.docx", size: 10 }];
    state.proposals = [proposal()];
    await controller.send();
    await until(controller, view => view.files.length === 1 && view.proposals.length === 1 && view.run?.state === "completed");
    assert.equal(controller.view.files[0]?.url, "/v2/projects/template-project/assistant/files/file-1");
  } finally { controller.close(); }
});

test("an unavailable assistant refuses Send with its reason and makes no run", async () => {
  const { api, calls } = fakeApi();
  api.capabilities = () => Promise.resolve({ ready: false, unavailable: { code: "AGENT_MODEL_REQUIRED", detail: [] }, models: [], webAvailable: true, tools: [] });
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь"); await controller.send();
    assert.equal(controller.view.error, "AGENT_MODEL_REQUIRED");
    assert.equal(calls.submit.length, 0);
    assert.equal(controller.view.pendingSend, false);
  } finally { controller.close(); }
});
