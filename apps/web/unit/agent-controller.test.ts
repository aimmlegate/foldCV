import assert from "node:assert/strict";
import test from "node:test";
import { AgentApiFailure } from "../src/assistant/api";
import { AssistantController, lostLink, type AssistantEditor, type AssistantView } from "../src/assistant/controller";
import { canSend, shownFailure } from "../src/assistant/presentation";
import type { AssistantApplyResultV1 } from "../src/contracts/generated/assistant_apply_result_v1";
import { event, fakeApi, message, proposal, run, settings } from "./support/assistant";

const editor = (apply: AssistantEditor["applyProposal"] = () => Promise.reject(new Error("unexpected apply")),
  actionApplied?: AssistantEditor["actionApplied"]): AssistantEditor => ({ applyProposal: apply, ...(actionApplied ? { actionApplied } : {}) });
function until(controller: AssistantController, done: (view: AssistantView) => boolean): Promise<void> {
  return new Promise((resolve, reject) => {
    // The check stops at the deadline too: a timer left running would keep a failing file from ending.
    const deadline = Date.now() + 2000;
    const check = () => {
      if (done(controller.view)) resolve();
      else if (Date.now() > deadline) reject(new Error("view never matched"));
      else setTimeout(check, 5);
    };
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

test("failed polls are retried while the panel shows the reconnect, and the run is still followed to its end", async () => {
  const { api } = fakeApi([[event(1, "run.state_changed", { state: "running", error: null, savedBatchId: null, outcomeUnknown: false })], []]);
  const events = api.events;
  let failures = 5;
  api.events = (runId, after, signal) => failures-- > 0 ? Promise.reject(new TypeError("fetch failed")) : events(runId, after, signal);
  const views: AssistantView[] = [], controller = new AssistantController(api, editor(), view => views.push(view), 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await until(controller, view => view.run?.state === "completed");
    assert.ok(views.some(view => view.loading === "Восстанавливаем связь с помощником"));
    assert.equal(controller.view.loading, null);
    assert.equal(controller.view.error, null);
  } finally { controller.close(); }
});

test("a run that stays unreachable is reported after the bounded retries, and Stop follows it again to its end", async () => {
  const { api } = fakeApi([[]]);
  const events = api.events;
  let down = true, attempts = 0;
  api.events = (runId, after, signal) => { attempts++; return down ? Promise.reject(new TypeError("fetch failed")) : events(runId, after, signal); };
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await until(controller, view => view.error === "SERVICE_UNAVAILABLE");
    assert.equal(controller.view.loading, "Нет связи с помощником");
    const given = attempts;
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(attempts, given, "no poll after giving up");
    down = false;
    await controller.stop();
    assert.equal(controller.view.run?.state, "cancelled");
    assert.equal(controller.view.loading, null);
    assert.equal(controller.active, false);
  } finally { controller.close(); }
});

test("Stop after a lost follow reads the results of a run that already ended and frees the panel", async () => {
  const { api, state } = fakeApi([[]]);
  api.events = () => Promise.reject(new TypeError("fetch failed"));
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await until(controller, view => view.loading === lostLink);
    state.messages = [message("user", "Проверь резюме"), message("assistant", "Готово.")];
    state.proposals = [proposal()];
    api.cancel = () => Promise.resolve(run("completed"));
    await controller.stop();
    assert.equal(controller.view.loading, null);
    assert.equal(controller.view.error, null);
    assert.equal(controller.view.messages.length, 2, "the final answer is read");
    assert.equal(controller.view.proposals.length, 1, "the proposals are read");
    controller.draft("Ещё");
    assert.equal(canSend(controller.view), true);
  } finally { controller.close(); }
});

test("Stop on a lost send reply repeats the same request and cancels the run the server started", async () => {
  const { api, calls, state } = fakeApi([[]]);
  state.submitFailures = 1;
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    assert.equal(controller.view.pendingSend, true);
    await controller.stop();
    assert.equal(calls.submit.length, 2);
    assert.equal(calls.submit[0]?.clientRequestId, calls.submit[1]?.clientRequestId);
    assert.equal(calls.cancel, 1);
    assert.equal(controller.view.run?.state, "cancelled");
    assert.equal(controller.view.pendingSend, false);
    assert.equal(controller.active, false);
  } finally { controller.close(); }
});

test("Stop reports a repeat that fails and keeps the send, while a refusal means nothing started", async () => {
  const { api, calls, state } = fakeApi([[]]);
  state.submitFailures = 2;
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await assert.rejects(controller.stop());
    assert.equal(controller.view.pendingSend, true);
    assert.equal(calls.cancel, 0);
    api.submit = () => Promise.reject(new AgentApiFailure("ASSISTANT_RUN_ACTIVE", 409));
    await controller.stop();
    assert.equal(controller.view.pendingSend, false);
    assert.equal(controller.view.error, "ASSISTANT_RUN_ACTIVE");
    assert.equal(calls.cancel, 0);
  } finally { controller.close(); }
});

test("a pending send keeps its conversation: new and other conversations are refused until it is settled", async () => {
  const { api, state } = fakeApi([[]]);
  state.submitFailures = 1;
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await assert.rejects(controller.newConversation(), (error: unknown) => error instanceof AgentApiFailure && error.code === "AGENT_BUSY");
    await assert.rejects(controller.select("conversation-2"), (error: unknown) => error instanceof AgentApiFailure && error.code === "AGENT_BUSY");
    assert.equal(controller.view.conversationId, "conversation-1");
    assert.equal(controller.view.draft, "Проверь резюме");
  } finally { controller.close(); }
});

test("a late message read changes neither a finished run nor newer messages", async () => {
  const { api, state } = fakeApi([[event(1, "file.ready", { id: "file-1" })], []]);
  const messages = api.messages;
  let reads = 0, release = () => {};
  const held = new Promise<void>(resolve => { release = resolve; });
  // Reads one and two are the opening and the send; the third starts on file.ready and answers after the final read.
  api.messages = async id => {
    const reply = await messages(id);
    if (++reads === 3) { await held; return reply; }
    if (reads === 4) return { ...reply, messages: [...reply.messages, message("assistant", "Готово.")] };
    return reply;
  };
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await until(controller, view => view.run?.state === "completed" && view.messages.length === 2 && view.partial === "");
    release();
    await new Promise(resolve => setTimeout(resolve, 5));
    assert.equal(controller.view.run?.state, "completed");
    assert.equal(controller.active, false);
    assert.equal(controller.view.messages.length, 2);
  } finally { controller.close(); }
});

test("a read sent before the run ended cannot reopen it even when it is the last to answer", async () => {
  const { api, state } = fakeApi([[]]);
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await until(controller, view => view.run?.state === "completed");
    state.runs = [run("running")];
    await controller.resource("sources", "absent");
    assert.equal(controller.view.run?.state, "completed");
  } finally { controller.close(); }
});

test("a slow stop says the run is still stopping, and the notice ends with the run", async () => {
  const { api, state } = fakeApi([[]]);
  const events = api.events;
  let ended = false;
  api.events = async (runId, after, signal) => {
    const reply = await events(runId, after, signal);
    return ended ? reply : { ...reply, run: run("cancelling") };
  };
  const controller = new AssistantController(api, editor(), () => {}, 1, 1);
  try {
    await controller.init(); controller.draft("Сократи текст"); await controller.send();
    const failure = await controller.stop().then(() => null, (error: unknown) => error instanceof AgentApiFailure ? error.code : "other");
    assert.equal(failure, "AGENT_STOP_PENDING");
    assert.equal(shownFailure(failure, controller.view.run), "AGENT_STOP_PENDING");
    ended = true; state.cancelled = true;
    await until(controller, view => view.run?.state === "cancelled");
    assert.equal(shownFailure(failure, controller.view.run), null);
  } finally { controller.close(); }
});

test("choosing a model keeps the saved level, and drops it with a notice only when the model lacks it", async () => {
  const { api } = fakeApi();
  const saved: unknown[] = [];
  const stored = { ...settings, reasoningEffort: "high" as const };
  api.settings = () => Promise.resolve(stored);
  api.saveSettings = value => {
    saved.push(value);
    if (value.selectedAgentModel === "limited" && value.reasoningEffort) return Promise.reject(new AgentApiFailure("AGENT_MODEL_INCOMPATIBLE", 409));
    return Promise.resolve({ ...stored, revision: stored.revision + 1, selectedAgentModel: value.selectedAgentModel, reasoningEffort: value.reasoningEffort ?? null });
  };
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init();
    await controller.chooseModel("capable");
    assert.deepEqual([...saved], [{ expectedRevision: 2, enabled: true, selectedAgentModel: "capable", reasoningEffort: "high" }]);
    assert.equal(controller.view.error, null);
    saved.length = 0;
    await controller.chooseModel("limited");
    assert.deepEqual(saved.map(value => (value as { reasoningEffort: unknown }).reasoningEffort), ["high", null]);
    assert.equal(controller.view.error, "AGENT_REASONING_DROPPED");
    // Another refusal of the same save keeps the level and reports itself.
    saved.length = 0;
    api.saveSettings = value => { saved.push(value); return Promise.reject(new AgentApiFailure("AGENT_SETTINGS_CONFLICT", 409)); };
    await controller.chooseModel("capable");
    assert.equal(saved.length, 1);
    assert.equal(controller.view.error, "AGENT_SETTINGS_CONFLICT");
  } finally { controller.close(); }
});

test("a run the service no longer has ends the loop at once", async () => {
  const { api } = fakeApi([[]]);
  let attempts = 0;
  api.events = () => { attempts++; return Promise.reject(new AgentApiFailure("AGENT_NOT_FOUND", 404)); };
  const controller = new AssistantController(api, editor(), () => {}, 1);
  try {
    await controller.init(); controller.draft("Проверь резюме"); await controller.send();
    await until(controller, view => view.error === "AGENT_NOT_FOUND");
    assert.equal(attempts, 1);
    assert.equal(controller.view.loading, null);
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
    assert.equal(controller.view.proposalAction, null);
    assert.equal(controller.view.proposals.find(item => item.id === "proposal-1")?.state, "discarded");
  } finally { controller.close(); }
});

test("the view names the proposal action in progress", async () => {
  const { api, state } = fakeApi();
  state.proposals = [proposal(), proposal({ id: "proposal-2" })];
  const views: AssistantView[] = [];
  const controller = new AssistantController(api, editor(() => Promise.reject(new Error("refused"))), view => views.push(view), 1);
  try {
    await controller.init();
    await controller.applyProposal(proposal());
    assert.ok(views.some(view => view.proposalBusy === "proposal-1" && view.proposalAction === "apply"));
    await controller.discardProposal(proposal({ id: "proposal-2" }));
    assert.ok(views.some(view => view.proposalBusy === "proposal-2" && view.proposalAction === "discard"));
    assert.equal(controller.view.proposalAction, null);
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

test("a quiet capability read replaces a connection refusal without a loading state", async () => {
  const { api } = fakeApi();
  let ready = false;
  api.capabilities = () => Promise.resolve(ready ? { ready: true, unavailable: null, models: [], webAvailable: true, tools: [] }
    : { ready: false, unavailable: { code: "AGENT_CONNECTION_UNAVAILABLE", detail: [] }, models: [], webAvailable: true, tools: [] });
  const views: AssistantView[] = [], controller = new AssistantController(api, editor(), view => views.push(view), 1);
  try {
    await controller.init();
    assert.equal(controller.view.capabilities?.unavailable?.code, "AGENT_CONNECTION_UNAVAILABLE");
    ready = true; views.length = 0;
    await controller.refreshCapabilities();
    assert.equal(controller.view.capabilities?.ready, true);
    assert.ok(views.every(view => !view.loading));
  } finally { controller.close(); }
});
