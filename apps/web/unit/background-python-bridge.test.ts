import assert from "node:assert/strict";
import test from "node:test";
import { PythonBridge } from "./support/python-bridge";
import { backgroundReply } from "../src/background/api";
import { documentSteps, type RichBlock } from "../src/rich/save-queue";
import type { RichMutation } from "../src/contracts/generated/rich_mutation";
import type { WriterProofV1 } from "../src/contracts/generated/background_writer_proof_v1";
import { containsSubmitted } from "../src/background/wire";
import { deferred, harness } from "./support/background-writer";
import { attachWriter, retainResume } from "../src/background/connection";
import { semantic } from "../src/rich/fact-cells";
import { applicationTabActive, claimApplicationTab, type TabLease } from "../src/background/tab";

function block(items: RichBlock[], id: string): RichBlock | undefined {
  for (const item of items) { if (item.id === id) return item; const child = block(item.children, id); if (child) return child; }
  return undefined;
}

async function opened(bridge: PythonBridge, project: string) {
  const api = bridge.writer(project), initial = await api.bootstrap(), credential = "synthetic_browser_writer_credential_0123456789";
  const view = await api.open({ schemaVersion: 1, sessionId: "browser-bridge-session", incarnation: "browser-bridge-connection", credential,
    canonicalRevision: initial.response.workspace.projectRevision, canonicalSha256: initial.workspaceSha256, actionCursor: 0 });
  const proof: WriterProofV1 = { schemaVersion: 1, lineage: view.writer.lineage, epoch: view.writer.epoch,
    sessionId: view.writer.sessionId, incarnation: view.writer.incarnation, credential };
  return { api, view, proof };
}

async function pendingJob(bridge: PythonBridge, ready: { project: string; conversation: string }, view: Awaited<ReturnType<typeof opened>>["view"], requestId: string) {
  const jobs = bridge.jobs(ready.project), registry = await jobs.projectJobs(), project = view.response.workspace.project;
  assert.ok(project);
  const accepted = await jobs.submit({ schemaVersion: 1, lineage: registry.lineage, requestEpoch: registry.requestEpoch,
    request: { clientRequestId: requestId, conversationId: ready.conversation, message: "Apply one scripted edit", allowEdits: true, allowWeb: false,
      scope: { kind: "resume" }, settingsRevision: 2, projectRevision: view.response.workspace.projectRevision,
      documentRevision: view.response.workspace.documentRevision, factsRevision: project.facts.revision } });
  const result = await bridge.call({ kind: "wait_job", job: accepted.id });
  assert.ok(typeof result === "object" && result !== null && "job" in result);
  const job = await backgroundReply("background_snapshot_v1", result.job);
  assert.equal(job.execution, "completed"); assert.equal(job.publication, "waiting_for_sync");
  return { job, binding: await jobs.proposal(job.id), jobs };
}

test("the Node writer API validates real Python HTTP saves, exact byte replay and clean detach", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start();
  let passed = false; t.after(() => bridge.close(!passed));
  try {
    const { api, view, proof } = await opened(bridge, ready.project), project = view.response.workspace.project;
    assert.ok(project);
    const document = structuredClone(project.document), quote = block(document.regions.flatMap(region => region.blocks), "quote");
    assert.ok(quote && Array.isArray(quote.content)); const text = quote.content[0]; assert.ok(text && "text" in text);
    text.text = "Real cross-layer manual input";
    const [first, ...rest] = documentSteps(project.document, document); assert.ok(first);
    const mutation: RichMutation = { schemaVersion: 1, projectId: ready.project, clientMutationId: crypto.randomUUID(),
      actionId: "cross-layer-input", kind: "typing", capture: { sessionId: proof.sessionId, actionId: "cross-layer-input", actionToken: 0, dependencies: [] },
      steps: [first, ...rest] };
    const request = { schemaVersion: 1 as const, proof, canonicalRevision: view.response.workspace.projectRevision,
      canonicalSha256: view.workspaceSha256, actionCursor: 1, touches: [{ cursor: 1, mutation }], mutation };
    const saved = await api.save(request); assert.ok(saved.mutationWire);
    assert.ok(containsSubmitted(mutation, JSON.parse(saved.mutationWire) as unknown));
    assert.equal(saved.response.workspace.projectRevision, view.response.workspace.projectRevision + 1);
    const replay = await api.save(request);
    assert.ok(replay.replayed); assert.equal(replay.workspaceSha256, saved.workspaceSha256);
    assert.equal(replay.response.workspace.mutationReplay.length, 1);
    const detached = await api.detach({ schemaVersion: 1, proof, canonicalRevision: saved.response.workspace.projectRevision,
      canonicalSha256: saved.workspaceSha256, actionCursor: 1, touches: [] });
    assert.equal(detached.writer.status, "clean_detached");
    const stats = await bridge.call({ kind: "stats" }); assert.ok(typeof stats === "object" && stats !== null && "syntheticStarts" in stats);
    assert.equal(stats.syntheticStarts, 0);
    passed = true;
  } finally { await bridge.close(!passed); }
});

for (const heartbeat of [true, false]) {
  test(`independent real sync metadata preserves local input and clean detach ${heartbeat ? "after heartbeat" : "before heartbeat"}`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    try {
      await bridge.http(`/v1/rich/projects/${ready.project}/completion`, "POST", {
        capture: { sessionId: proof.sessionId, actionId: "metadata-only", actionToken: 0, dependencies: [] },
        blockIds: [], movedIds: [], removedFields: [], removedRecordIds: [], interpret: false });
      const updated = await api.read(proof);
      assert.notEqual(updated.workspaceSha256, view.workspaceSha256);
      assert.deepEqual(updated.response.workspace.project?.document, view.response.workspace.project?.document);
      assert.deepEqual(updated.response.workspace.project?.facts, view.response.workspace.project?.facts);
      if (heartbeat) {
        await h.writer.heartbeat(); assert.equal(h.writer.mode, "normal");
        assert.equal(h.queue.baseline.workspace.syncRecords.length, updated.response.workspace.syncRecords.length);
        assert.ok(h.type("Local input survives independent metadata")); await h.queue.flush();
      }
      await h.writer.navigate(); assert.equal(h.writer.mode, "detached");
      const final = await api.read(proof);
      assert.equal(final.writer.status, "clean_detached");
      assert.equal(final.response.workspace.mutationReplay.length, heartbeat ? 1 : 0);
      assert.deepEqual(final.response.workspace.syncRecords, updated.response.workspace.syncRecords);
      assert.deepEqual(h.errors, []); passed = true;
    } finally { h.close(); await bridge.close(!passed); }
  });
}

for (const heldReply of ["save", "heartbeat"] as const) {
  test(`a real ${heldReply} reply racing a heartbeat cannot regress the acknowledged writer`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    const held = await bridge.hold(`${heldReply}_response`, "http");
    try {
      const heartbeat = heldReply === "heartbeat" ? h.writer.heartbeat() : null;
      if (heartbeat) await held.reached;
      assert.ok(h.type("Input while a real reply is held"));
      const saving = h.queue.flush(); void saving.catch(() => {});
      if (heldReply === "save") {
        await held.reached; await h.writer.heartbeat();
        assert.equal(h.queue.baseline.workspace.projectRevision, view.response.workspace.projectRevision);
      } else await saving;
      assert.equal(h.writer.mode, "normal");
      await held.release(); await saving; await heartbeat;
      assert.equal(h.writer.mode, "normal");
      assert.equal(h.queue.baseline.workspace.projectRevision, view.response.workspace.projectRevision + 1);
      const canonical = await api.read(proof);
      assert.equal(h.writer.view.workspaceSha256, canonical.workspaceSha256);
      assert.deepEqual(h.errors, []); passed = true;
    } finally { await held.release(); h.close(); await bridge.close(!passed); }
  });
}

test("a real clean autosave and heartbeat reopen without a recovery draft", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  sessionStorage.clear();
  const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
  try {
    assert.ok(h.type("Clean input must reopen automatically")); await h.queue.flush();
    assert.equal(await h.localDraft(), null); await h.writer.heartbeat();
    await api.suspend(proof); h.close();
    const next = await attachWriter(ready.project, api, h.connection.repository);
    assert.ok(next?.proof); assert.equal(next.local, null); assert.equal(next.view.writer.status, "attached");
    const resumed = harness({ attached: next });
    try { assert.equal(resumed.writer.mode, "normal"); } finally { resumed.close(); }
    passed = true;
  } finally { h.close(); await bridge.close(!passed); }
});

for (const seconds of [15, 16]) {
test(`a clean mounted writer resumes ${seconds === 15 ? "at" : "after"} real lease expiry and keeps session history`, { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
  try {
    assert.ok(h.type("Acknowledged input before lease expiry")); await h.queue.flush();
    assert.equal(await h.localDraft(), null); await bridge.call({ kind: "advance", seconds });
    await h.writer.heartbeat(); assert.equal(h.writer.mode, "normal"); assert.equal(h.locked(), false);
    assert.equal(h.writer.proof.epoch, proof.epoch); assert.notEqual(h.writer.proof.incarnation, proof.incarnation);
    assert.equal(h.writer.cursor, 1); assert.equal(h.history.length, 1);
    await assert.rejects(api.read(proof), error => error instanceof Error && error.message === "WRITER_UNKNOWN");
    assert.ok(h.history.undo()); await h.queue.flush(); assert.equal(h.writer.mode, "normal");
    assert.deepEqual(semantic((await api.read(h.writer.proof)).response.workspace.project?.document), semantic(view.response.workspace.project?.document));
    assert.ok(h.history.redo()); await h.queue.flush(); assert.equal(h.writer.mode, "normal");
    assert.equal(await h.localDraft(), null); assert.deepEqual(h.errors, []); passed = true;
  } finally { h.close(); await bridge.close(!passed); }
});
}

test("a timed out real lease resume cannot adopt over retained input", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
  const held = await bridge.hold("open_response", "http"), finished = deferred<void>(), open = api.open.bind(api);
  api.open = async request => { try { return await open(request); } finally { finished.resolve(); } };
  try {
    await bridge.call({ kind: "advance", seconds: 15 });
    const heartbeat = h.writer.heartbeat(); await held.reached;
    h.expire(); await heartbeat; assert.equal(h.writer.mode, "recovering");
    assert.ok(h.type("Input after the clean resume deadline"));
    await held.release(); await finished.promise; await h.settle();
    assert.equal(h.writer.mode, "recovering"); assert.equal(h.writer.proof.incarnation, proof.incarnation);
    const local = await h.localDraft(); assert.ok(local);
    assert.deepEqual(semantic(local.payload.document), semantic(h.snapshot().document));
    const resolved = await h.writer.resolveDraft("draft"); assert.equal(resolved.durability, "durable");
    assert.deepEqual(semantic(resolved.workspace.project?.document), semantic(h.snapshot().document));
    assert.equal(await h.localDraft(), null); passed = true;
  } finally { await held.release(); h.close(); await bridge.close(!passed); }
});

for (const revoked of [false, true]) {
  for (const choice of ["saved", "draft"] as const) {
    test(`explicit ${choice} choice recovers a real ${revoked ? "revoked" : "expired"} writer without reload`, { timeout: 60000 }, async t => {
      const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
      const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
      try {
        assert.ok(h.type("Retained input after authority loss"));
        if (revoked) await api.abandon({ schemaVersion: 1, sessionId: "replacement-session", incarnation: "replacement-connection",
          credential: "synthetic_replacement_credential_0123456789", canonicalRevision: view.response.workspace.projectRevision,
          canonicalSha256: view.workspaceSha256, discardDrafts: [] });
        else await bridge.call({ kind: "advance", seconds: 15 });
        await h.writer.heartbeat(); assert.equal(h.writer.mode, "recovering");
        const local = await h.localDraft(); assert.ok(local);
        const resolved = await h.writer.resolveDraft(choice); assert.equal(resolved.durability, "durable");
        assert.deepEqual(semantic(resolved.workspace.project?.document), semantic(choice === "draft" ? local.payload.document : view.response.workspace.project?.document));
        assert.ok(h.writer.proof.epoch > proof.epoch); assert.equal(await h.localDraft(), null);
        await assert.rejects(api.checkpoint({ schemaVersion: 1, proof, id: local.record.id, sequence: local.record.sequence + 1,
          actionCursor: local.record.cursor, baseRevision: local.record.baseRevision, baseSha256: local.record.baseSha256,
          payload: local.payload }), error => error instanceof Error && error.message === "WRITER_UNKNOWN");
        assert.deepEqual((await api.bootstrap()).response.workspace, resolved.workspace); passed = true;
      } finally { h.close(); await bridge.close(!passed); }
    });
  }
}

for (const dirty of [false, true]) {
  test(`the sole active tab resumes ${dirty ? "a dirty outbox" : "clean input"} when its unload notification is lost`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    sessionStorage.clear();
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    try {
      assert.ok(h.type("Input before the sole tab reloads"));
      if (dirty) {
        api.save = () => Promise.reject(new TypeError("Synthetic request lost before dispatch"));
        await assert.rejects(h.queue.flush(), /Synthetic request lost/u); await h.writer.checkpoint();
      } else await h.queue.flush();
      const local = await h.localDraft();
      h.close();
      const currentApi = bridge.writer(ready.project), next = await attachWriter(ready.project, currentApi, h.connection.repository, () => true);
      assert.ok(next?.proof); assert.notEqual(next.proof.incarnation, proof.incarnation);
      if (dirty) {
        assert.ok(local && next.local); assert.equal(local.payload.outbox.length, 1);
        assert.equal(next.view.writer.status, "recovering");
        assert.deepEqual(next.local.payload, local.payload);
        assert.equal(next.local.record.sequence, local.record.sequence);
        assert.equal(next.view.response.workspace.mutationReplay.length, 0);
      } else {
        assert.equal(next.local, null); assert.equal(next.view.writer.status, "attached");
        assert.deepEqual(next.view.response.workspace.project?.document, h.queue.baseline.workspace.project?.document);
      }
      await assert.rejects(currentApi.read(proof), error => error instanceof Error && error.message === "WRITER_UNKNOWN");
      passed = true;
    } finally { h.close(); await bridge.close(!passed); }
  });
}

test("the sole tab cannot revoke a writer with an invalid resume credential", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  sessionStorage.clear();
  const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
  try {
    assert.ok(h.type("Input protected by the original credential")); await h.queue.flush();
    retainResume(ready.project, { ...proof, credential: "synthetic_invalid_resume_credential_0123456789" }, h.writer.view, h.writer.cursor, 0);
    h.close();
    const next = await attachWriter(ready.project, api, h.connection.repository, () => true);
    assert.ok(next); assert.equal(next.proof, null); assert.equal(next.error, "WRITER_READ_ONLY");
    const current = await api.read(proof); assert.equal(current.writer.incarnation, proof.incarnation);
    assert.equal(current.workspaceSha256, h.writer.view.workspaceSha256); passed = true;
  } finally { h.close(); await bridge.close(!passed); }
});

for (const dirty of [false, true]) {
  test(`a fresh sole tab uses the shared ${dirty ? "dirty" : "clean"} resume marker without sessionStorage`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    sessionStorage.clear(); localStorage.clear();
    const request = async (_name: string, work: (available: boolean) => Promise<void>) => { await work(true); };
    const first = await claimApplicationTab(request); assert.ok(first);
    let second: TabLease | null = null;
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    try {
      assert.ok(h.type("Input before changing the active browser tab"));
      if (dirty) await h.writer.checkpoint(); else await h.queue.flush();
      const local = await h.localDraft();
      assert.ok(localStorage.getItem(`foldcv-writer:${ready.project}`));
      h.close(); first.release(); sessionStorage.clear();
      second = await claimApplicationTab(request); assert.ok(second);
      first.release(); assert.equal(applicationTabActive(), true);
      const next = await attachWriter(ready.project, api, h.connection.repository, applicationTabActive);
      assert.ok(next?.proof); assert.notEqual(next.proof.incarnation, proof.incarnation);
      if (dirty) {
        assert.ok(local && next.local); assert.equal(next.view.writer.status, "recovering");
        assert.deepEqual(next.local.payload, local.payload); assert.equal(next.view.response.workspace.mutationReplay.length, 0);
      } else {
        assert.equal(next.local, null); assert.equal(next.view.writer.status, "attached");
        assert.deepEqual(next.view.response.workspace, h.queue.baseline.workspace);
      }
      passed = true;
    } finally { first.release(); second?.release(); sessionStorage.clear(); localStorage.clear(); h.close(); await bridge.close(!passed); }
  });
}

for (const stage of ["before", "after"] as const) {
  test(`a lost application tab lock stops writer attachment ${stage} bootstrap`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    sessionStorage.clear();
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    let owned = stage === "after", reads = 0;
    const bootstrap = api.bootstrap.bind(api);
    api.bootstrap = async () => { reads++; const result = await bootstrap(); owned = false; return result; };
    try {
      await assert.rejects(attachWriter(ready.project, api, h.connection.repository, () => owned), /TAB_LOCK_REQUIRED/u);
      assert.equal(reads, stage === "before" ? 0 : 1);
      assert.equal((await api.read(proof)).writer.incarnation, proof.incarnation); passed = true;
    } finally { h.close(); await bridge.close(!passed); }
  });
}

for (const headless of [false, true]) {
  test(`a real clean detach reopens a new writer epoch ${headless ? "after headless publication" : "after acknowledged input"}`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    sessionStorage.clear();
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    let gate: Awaited<ReturnType<PythonBridge["hold"]>> | null = null;
    try {
      assert.ok(h.type("Input acknowledged before clean detach")); await h.queue.flush();
      const pending = headless ? await pendingJob(bridge, ready, h.writer.view, "clean-headless-handoff") : null;
      if (pending) gate = await bridge.hold("receipt_stored");
      await h.writer.navigate(); assert.equal(h.writer.mode, "detached");
      await gate?.reached; await gate?.release();
      h.close();
      const next = await attachWriter(ready.project, api, h.connection.repository);
      assert.ok(next?.proof); assert.equal(next.local, null); assert.equal(next.view.writer.status, "attached");
      assert.equal(next.proof.epoch, proof.epoch + 1); assert.equal(next.view.writer.acknowledgedCursor, 0);
      const resumed = harness({ attached: next });
      try {
        assert.equal(resumed.writer.mode, "normal");
        if (pending) {
          const saved = await pending.jobs.read(pending.job.id); assert.ok(saved.receipt?.durable);
          await resumed.writer.adoptHeadless(saved); assert.equal(resumed.history.length, 1);
          assert.equal(resumed.counts.notices, 1); assert.ok(await resumed.writer.history("undo"));
          const canonical = await api.read(next.proof);
          assert.equal(canonical.response.workspace.mutationReplay.length, 3);
        }
      } finally { resumed.close(); }
      passed = true;
    } finally { await gate?.release(); h.close(); await bridge.close(!passed); }
  });
}

test("a foreign cursor cannot claim the previous writer's clean acknowledged handoff", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
  try {
    assert.ok(h.type("The old writer's acknowledged input")); await h.queue.flush(); await h.writer.navigate();
    const current = await api.bootstrap();
    const foreign = await api.open({ schemaVersion: 1, sessionId: "foreign-session", incarnation: "foreign-connection",
      credential: "synthetic_foreign_writer_credential_0123456789", previousEpoch: proof.epoch, previousIncarnation: proof.incarnation,
      canonicalRevision: current.response.workspace.projectRevision, canonicalSha256: current.workspaceSha256,
      actionCursor: current.writer.acknowledgedCursor, draftSequence: 0 });
    assert.equal(foreign.writer.status, "recovering"); passed = true;
  } finally { h.close(); await bridge.close(!passed); }
});

test("a real capacity-one Job releases its synthetic child before Node publishes and adopts its exact compiler result", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start();
  let passed = false; t.after(() => bridge.close(!passed));
  try {
    const { api, view, proof } = await opened(bridge, ready.project), jobs = bridge.jobs(ready.project), project = await jobs.projectJobs();
    assert.ok(view.response.workspace.project);
    const held = await bridge.hold("scripted_model_ready", "job");
    const job = await jobs.submit({ schemaVersion: 1, lineage: project.lineage, requestEpoch: project.requestEpoch,
      request: { clientRequestId: "cross-layer-job", conversationId: ready.conversation, message: "Apply one scripted edit", allowEdits: true, allowWeb: false,
        scope: { kind: "resume" }, settingsRevision: 2, projectRevision: view.response.workspace.projectRevision,
        documentRevision: view.response.workspace.documentRevision, factsRevision: view.response.workspace.project.facts.revision } });
    await held.reached;
    assert.equal((await jobs.read(job.id)).execution, "running");
    assert.equal((await api.heartbeat(proof)).workspaceSha256, view.workspaceSha256);
    await held.release();
    const finished: unknown = await bridge.call({ kind: "wait_job", job: job.id });
    assert.ok(typeof finished === "object" && finished !== null && "job" in finished && "apply" in finished);
    const pending = await backgroundReply("background_snapshot_v1", finished.job);
    assert.equal(pending.execution, "completed"); assert.equal(pending.publication, "waiting_for_sync");
    assert.ok(typeof finished.apply === "object" && finished.apply !== null && "disposition" in finished.apply);
    assert.equal(finished.apply.disposition, "waiting_for_sync");
    const stats = await bridge.call({ kind: "stats" });
    assert.ok(typeof stats === "object" && stats !== null && "activeSlots" in stats && "admissionHeld" in stats && "syntheticStarts" in stats);
    assert.equal(stats.activeSlots, 0); assert.equal(stats.admissionHeld, false); assert.equal(stats.syntheticStarts, 1);
    const binding = await jobs.proposal(job.id), header = { schemaVersion: 1 as const, proof,
      canonicalRevision: view.response.workspace.projectRevision, canonicalSha256: view.workspaceSha256, actionCursor: 0, touches: [] };
    const barrier = await api.barrier({ ...header, generation: view.writer.barrierGeneration + 1, touchGeneration: view.writer.touchGeneration,
      token: "synthetic_bridge_barrier_token_0123456789" });
    const published = await api.publish({ schemaVersion: 1, proof, generation: barrier.generation, token: barrier.token,
      jobId: job.id, proposalSha256: binding.payloadSha256 });
    assert.equal(published.job.publication, "saved"); assert.ok(published.job.receipt?.durable);
    const owner = published.view.inverses?.find(item => item.jobId === job.id); assert.ok(owner);
    const adoption = { ...header, canonicalRevision: published.view.response.workspace.projectRevision, canonicalSha256: published.view.workspaceSha256,
      jobId: job.id, proposalId: binding.id, transferId: owner.transferId };
    const offer = await api.offer(adoption); assert.equal(offer.saved.workspace.projectRevision, published.job.receipt.projectRevision);
    assert.equal((await api.begin(adoption)).owner, "transferring"); assert.equal((await api.acknowledge(adoption)).owner, "session");
    assert.equal((await jobs.legacy(job.id)).run.state, "completed");
    passed = true;
  } finally { await bridge.close(!passed); }
});

test("NB-W05:v01 navigation waits for a real manual save ACK without accepting input past its protected boundary", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
  const held = await bridge.hold("before_receipt_stored");
  try {
    assert.ok(h.type("Real save delayed at its receipt"));
    const saving = h.queue.flush(); await held.reached;
    const navigation = h.writer.navigate(); await h.settle();
    const buffer = new Map(h.mounted); assert.ok(h.locked());
    assert.equal(h.type("Blocked past the final save"), null); assert.deepEqual(h.mounted, buffer);
    await held.release(); await saving; await navigation;
    assert.equal(h.writer.mode, "detached"); assert.equal(h.queue.baseline.workspace.mutationReplay.length, 1);
    const canonical = await api.read(proof); assert.equal(canonical.writer.status, "clean_detached");
    const document = canonical.response.workspace.project?.document; assert.ok(document);
    const quote = block(document.regions.flatMap(region => region.blocks), "quote");
    assert.ok(quote && Array.isArray(quote.content)); assert.equal(quote.content[0]?.type === "text" ? quote.content[0].text : null, "Real save delayed at its receipt");
    assert.equal(h.counts.notices, 0); passed = true;
  } finally { await held.release().catch(() => {}); h.close(); await bridge.close(!passed); }
});

for (const later of [true, false]) {
  test(`NB-W02:v${later ? "01" : "02"} real saved receipt outlives a lost HTTP reply and ${later ? "preserves later input" : "recovers once"}`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    const held = await bridge.hold("publish_response", "http");
    try {
      const { job, binding, jobs } = await pendingJob(bridge, ready, view, `lost-reply-${String(later)}`);
      const task = h.writer.publish(job, binding); await held.reached;
      const won = await jobs.read(job.id); assert.equal(won.publication, "saved"); assert.ok(won.receipt?.durable);
      h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
      if (later) assert.ok(h.type("Input typed after the real commit timeout"));
      await h.writer.checkpoint(); const local = await h.localDraft(); assert.ok(local);
      const buffer = new Map(h.mounted);
      await held.release(); await h.settle();
      assert.deepEqual(h.mounted, buffer); assert.equal(h.counts.notices, 0);
      await h.writer.recoverPublication(won);
      if (later) {
        assert.equal(h.writer.mode, "recovering"); assert.deepEqual(h.mounted, buffer); assert.equal(h.counts.notices, 0);
        const draft = await h.localDraft(); assert.ok(draft); assert.equal(draft.record.cursor, 1);
        assert.equal(h.history.length, 1);
      } else {
        assert.equal(h.writer.mode, "normal"); assert.equal(h.counts.notices, 1); assert.equal(h.history.length, 1);
        await h.writer.recoverPublication(won); await h.writer.adoptHeadless(won); assert.equal(h.counts.notices, 1);
      }
      const stats = await bridge.call({ kind: "stats" });
      assert.ok(typeof stats === "object" && stats !== null && "syntheticStarts" in stats && "activeSlots" in stats && "state" in stats);
      assert.equal(stats.syntheticStarts, 1); assert.equal(stats.activeSlots, 0);
      const canonical = await api.read(proof); assert.equal(canonical.response.workspace.mutationReplay.length, 1);
      assert.equal(canonical.response.workspace.projectRevision, view.response.workspace.projectRevision + 1);
      if (!later) assert.equal(canonical.drafts.length, 0);
      passed = true;
    } finally { await held.release(); h.close(); await bridge.close(!passed); }
  });
}

for (const committed of [true, false]) {
  test(`NB-W08:v${committed ? "01" : "02"} dirty reload retains an exact ${committed ? "committed" : "uncommitted"} outbox without restamping it`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    sessionStorage.clear();
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    const held = committed ? await bridge.hold("save_response", "http") : null;
    let next: ReturnType<typeof harness> | null = null;
    try {
      assert.ok(h.type("Input retained across an actual writer reload"));
      if (!committed) h.api.save = () => Promise.reject(new Error("Synthetic request lost before delivery"));
      const saving = h.queue.flush(); void saving.catch(() => {});
      if (held) await held.reached; else await assert.rejects(saving, /Synthetic request lost/u);
      await h.writer.checkpoint(); const local = await h.localDraft(); assert.ok(local);
      const ids = local.payload.outbox.map(item => item.clientMutationId); assert.equal(ids.length, 1);
      await api.suspend(proof); h.close();
      const attached = await attachWriter(ready.project, bridge.writer(ready.project), h.connection.repository);
      assert.ok(attached?.proof && attached.local);
      assert.notEqual(attached.proof.incarnation, proof.incarnation); assert.equal(attached.proof.epoch, proof.epoch);
      assert.deepEqual(attached.local.payload.outbox.map(item => item.clientMutationId), ids);
      next = harness({ attached }); assert.equal(next.writer.mode, "recovering");
      assert.deepEqual(semantic(next.snapshot().document), semantic(local.payload.document));
      await held?.release(); if (held) await assert.rejects(saving, /WRITER_STALE_CALLBACK/u);
      const resolved = await next.writer.resolveDraft(committed ? "saved" : "draft");
      assert.equal(resolved.workspace.mutationReplay.length, 1);
      if (committed) assert.equal(resolved.workspace.mutationReplay[0]?.clientMutationId, ids[0]);
      else assert.notEqual(resolved.workspace.mutationReplay[0]?.clientMutationId, ids[0]);
      assert.equal(await h.localDraft(), null);
      assert.equal((await bridge.jobs(ready.project).projectJobs()).jobs.length, 0);
      passed = true;
    } finally { await held?.release(); next?.close(); h.close(); await bridge.close(!passed); }
  });
}

for (const late of [false, true]) {
  test(`NB-W08:v${late ? "04" : "03"} explicit abandonment exits a lost tab and ${late ? "rejects its late checkpoint" : "keeps selected local input"}`, { timeout: 60000 }, async t => {
    const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
    sessionStorage.clear();
    const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
    let next: ReturnType<typeof harness> | null = null;
    try {
      assert.ok(h.type("Selected input from a lost tab")); await h.writer.checkpoint();
      const local = await h.localDraft(); assert.ok(local);
      sessionStorage.clear();
      const attached = await attachWriter(ready.project, bridge.writer(ready.project), h.connection.repository);
      assert.ok(attached?.local); assert.equal(attached.proof, null); assert.equal(attached.error, "WRITER_READ_ONLY");
      next = harness({ attached }); assert.equal(next.writer.mode, "read_only");
      const resolved = await next.writer.resolveDraft("draft");
      assert.equal(resolved.workspace.mutationReplay.length, 1);
      assert.ok(next.connection.proof); assert.ok(next.connection.proof.epoch > proof.epoch);
      if (late) {
        await assert.rejects(api.checkpoint({ schemaVersion: 1, proof, id: local.record.id, sequence: local.record.sequence + 1,
          actionCursor: local.record.cursor, baseRevision: local.record.baseRevision, baseSha256: local.record.baseSha256,
          payload: local.payload }), error => error instanceof Error && error.message === "WRITER_UNKNOWN");
        assert.deepEqual((await bridge.writer(ready.project).bootstrap()).response.workspace, resolved.workspace);
      }
      assert.equal(await h.localDraft(), null); passed = true;
    } finally { next?.close(); h.close(); await bridge.close(!passed); }
  });
}

test("capacity-one API controls with a blocked model and a full background queue", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  const held = await bridge.hold("scripted_model_ready", "job"), queued: { project: string; id: string }[] = [];
  let editor: ReturnType<typeof harness> | null = null;
  try {
    const a = await opened(bridge, ready.project), clone = await bridge.call({ kind: "clone" });
    assert.ok(typeof clone === "object" && clone !== null && "project" in clone && typeof clone.project === "string");
    const b = await opened(bridge, clone.project); editor = harness({ initialView: b.view, proof: b.proof, transport: b.api });
    async function submit(project: string, conversation: string, id: string) {
      const api = bridge.writer(project), view = await api.bootstrap(), jobs = bridge.jobs(project), registry = await jobs.projectJobs();
      assert.ok(view.response.workspace.project);
      return jobs.submit({ schemaVersion: 1, lineage: registry.lineage, requestEpoch: registry.requestEpoch,
        request: { clientRequestId: id, conversationId: conversation, message: "Hold the synthetic model", allowEdits: false, allowWeb: false,
          scope: { kind: "resume" }, settingsRevision: 2, projectRevision: view.response.workspace.projectRevision,
          documentRevision: view.response.workspace.documentRevision, factsRevision: view.response.workspace.project.facts.revision } });
    }
    const active = await submit(ready.project, ready.conversation, "blocked-active"); await held.reached;
    const projects = [{ project: ready.project, conversation: ready.conversation }];
    for (let index = 0; index < 5; index++) {
      const row = await bridge.call({ kind: "clone" });
      assert.ok(typeof row === "object" && row !== null && "project" in row && typeof row.project === "string"
        && "conversation" in row && typeof row.conversation === "string");
      projects.push({ project: row.project, conversation: row.conversation });
    }
    for (let index = 0; index < 16; index++) {
      const owner = projects[Math.floor(index / 3)]; assert.ok(owner);
      const accepted = await submit(owner.project, owner.conversation, `full-queue-${String(index)}`);
      assert.equal(accepted.execution, "queued"); queued.push({ project: owner.project, id: accepted.id });
    }
    const last = projects.at(-1); assert.ok(last);
    await assert.rejects(submit(last.project, last.conversation, "overflow"), /JOB_QUEUE_FULL/u);
    await t.test("NB-Q09:v01 manual save on another project completes while inference remains held", async () => {
      assert.ok(editor); assert.ok(editor.type("Project B saves without an inference slot")); await editor.queue.flush();
      assert.equal(editor.queue.baseline.workspace.mutationReplay.length, 1);
    });
    await t.test("NB-Q09:v04 read API completes while inference remains held", async () => {
      assert.equal((await b.api.read(b.proof)).response.workspace.mutationReplay.length, 1);
      assert.equal((await bridge.jobs(ready.project).read(active.id)).execution, "running");
    });
    await t.test("NB-Q09:v06 host status API completes without opening another runtime", async () => {
      const status = await bridge.http("/v1/host/status", "POST", {}); assert.ok(status);
      const stats = await bridge.call({ kind: "stats" });
      assert.ok(typeof stats === "object" && stats !== null && "syntheticStarts" in stats && "activeSlots" in stats && "admissionHeld" in stats);
      assert.equal(stats.syntheticStarts, 1); assert.equal(stats.activeSlots, 1); assert.equal(stats.admissionHeld, true);
    });
    await t.test("NB-Q09:v07 cancel API removes queued work without waiting for the held model", async () => {
      const last = queued.pop(); assert.ok(last);
      const cancelled = await bridge.jobs(last.project).cancel(last.id); assert.equal(cancelled.execution, "cancelled");
    });
    assert.equal((await a.api.heartbeat(a.proof)).writer.status, "attached"); passed = true;
  } finally {
    for (const row of queued) await bridge.jobs(row.project).cancel(row.id);
    await held.release(); editor?.close(); await bridge.close(!passed);
  }
});

test("NB-H01:v04 a lost durable history ACK recovers one inverse owner and one mounted action", { timeout: 60000 }, async t => {
  const { bridge, ready } = await PythonBridge.start(); let passed = false; t.after(() => bridge.close(!passed));
  const { api, view, proof } = await opened(bridge, ready.project), h = harness({ initialView: view, proof, transport: api });
  const held = await bridge.hold("ack_response", "http");
  try {
    const { job, binding, jobs } = await pendingJob(bridge, ready, view, "lost-history-ack");
    const task = h.writer.publish(job, binding); await held.reached;
    const committed = await jobs.read(job.id); assert.ok(committed.receipt?.durable);
    const owned = await api.read(proof); assert.equal(owned.inverses?.filter(item => item.owner === "session").length, 1);
    h.expire(); await assert.rejects(task, /WRITER_BARRIER_TIMEOUT/u);
    assert.equal(h.counts.notices, 0); assert.equal(h.history.length, 0);
    await h.writer.checkpoint(); await held.release(); await h.settle();
    await h.writer.recoverPublication(committed); await h.writer.adoptHeadless(committed);
    assert.equal(h.writer.mode, "normal"); assert.equal(h.history.length, 1); assert.equal(h.counts.notices, 1);
    const final = await api.read(proof);
    assert.equal(final.inverses?.length, 1); assert.equal(final.inverses?.[0]?.owner, "session");
    assert.equal(final.response.workspace.mutationReplay.length, 1);
    const stats = await bridge.call({ kind: "stats" }); assert.ok(typeof stats === "object" && stats !== null && "syntheticStarts" in stats);
    assert.equal(stats.syntheticStarts, 1); passed = true;
  } finally { await held.release(); h.close(); await bridge.close(!passed); }
});
