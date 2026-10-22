import assert from "node:assert/strict";
import test from "node:test";
import { SessionHistory, type HistoryEffectContext, type CellChange } from "../src/rich/history";

function server(effect: (changes: readonly CellChange[], context: HistoryEffectContext) => void = () => {}) {
  return new SessionHistory("opening", new Map([["body", "A"]]), effect, () => true, "opening", "server");
}

test("server-retained visible-equal actions remain navigable without a fake cell", () => {
  const contexts: HistoryEffectContext[] = [];
  const history = server((_changes, context) => contexts.push(context));
  const id = history.commit("typing", []);
  assert.ok(id);
  assert.equal(history.acknowledgeServerAction(id, 0, true), "retained");
  assert.equal(history.length, 1);
  assert.deepEqual(history.retainedValues(), ["A"]);
  assert.equal(history.undo(), false);
  assert.equal(history.redo(), false);
  for (const direction of ["undo", "redo"] as const) {
    const reservation = history.reserveNavigation(direction, `navigation-${direction}`);
    assert.ok(reservation);
    assert.ok(history.publishNavigation(reservation, direction, []));
  }
  assert.equal(history.position, 1);
  assert.deepEqual(contexts.map(value => value.actionToken), [0, 2, 4]);
  assert.equal(history.read("body"), "A");
});

test("net-empty typing waits for the exact server disposition and preserves newer typing", () => {
  const history = server();
  const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }], "group");
  assert.ok(id);
  assert.equal(history.commit("typing", [{ key: "body", before: "B", after: "A" }], "group"), id);
  assert.equal(history.length, 1);
  assert.equal(history.acknowledgeServerAction(id, 0, false), "pending");
  assert.equal(history.length, 1);
  assert.equal(history.discardPending(id), false);
  assert.equal(history.acknowledgeServerAction(id, 1, false), "removed");
  assert.equal(history.length, 0);
  assert.equal(history.position, 0);
  assert.equal(history.read("body"), "A");
});

test("retained net-empty typing keeps its original action for server Undo", () => {
  const history = server();
  const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }], "group");
  assert.ok(id);
  history.commit("typing", [{ key: "body", before: "B", after: "A" }], "group");
  assert.equal(history.acknowledgeServerAction(id, 1, true), "retained");
  assert.equal(history.actionFor("undo"), id);
  assert.deepEqual(history.navigation("undo")?.changes, []);
});

test("attached reconciliation returning original UI waits for the exact server disposition", () => {
  for (const retained of [false, true]) {
    const history = server();
    const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }]);
    assert.ok(id);
    const capture = history.capture(id, ["body"]);
    assert.ok(capture);
    assert.equal(history.attach(capture, [{ key: "body", before: "B", after: "A" }]), "applied");
    assert.equal(history.length, 1);
    assert.deepEqual(history.navigation("undo")?.changes, []);
    assert.equal(history.acknowledgeServerAction(id, 0, false), "pending");
    assert.equal(history.acknowledgeServerAction(id, 1, retained), retained ? "retained" : "removed");
    assert.equal(history.position, retained ? 1 : 0);
    assert.equal(history.length, retained ? 1 : 0);
    assert.equal(history.read("body"), "A");
  }
});

test("navigation invalidates captured action authority before awaiting any response", () => {
  const history = server();
  const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }]);
  assert.ok(id);
  const capture = history.capture(id, ["body"]);
  assert.ok(capture && history.current(capture));
  const reservation = history.reserveNavigation("undo", "navigation");
  assert.ok(reservation);
  assert.equal(history.current(capture), false);
  assert.equal(history.acknowledgeServerAction(id, 0, true), "stale");
  history.discard(reservation);
  assert.equal(history.current(capture), false);
  assert.equal(history.position, 1);
});

test("server navigation requires its specific reservation and new typing cannot coalesce into replay", () => {
  const history = server();
  const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }], "same-group");
  assert.ok(id);
  const ordinary = history.reserve("ordinary");
  assert.ok(ordinary);
  assert.equal(history.publishNavigation(ordinary, "undo", [{ key: "body", before: "B", after: "A" }]), false);
  history.discard(ordinary);
  for (const direction of ["undo", "redo"] as const) {
    const navigation = history.navigation(direction);
    const reservation = history.reserveNavigation(direction, direction);
    assert.ok(reservation && navigation);
    assert.equal(history.publish(reservation, []), false);
    assert.equal(history.adoptExisting(reservation, []), false);
    assert.ok(history.publishNavigation(reservation, direction, navigation.changes));
  }
  const retyped = history.commit("typing", [{ key: "body", before: "B", after: "A" }], "same-group");
  assert.ok(retyped && retyped !== id);
  assert.equal(history.length, 2);
});

test("server disposition cannot discard a nonempty projection or accept a foreign token", () => {
  const history = server();
  const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }]);
  assert.ok(id);
  for (const token of [-1, 1, Number.NaN, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(history.acknowledgeServerAction(id, token, false), "stale");
  }
  assert.equal(history.acknowledgeServerAction(id, 0, false), "stale");
  assert.equal(history.length, 1);
  assert.equal(history.read("body"), "B");
});

test("prepared server actions may have zero UI changes in both publication paths", () => {
  for (const method of ["publish", "adoptExisting"] as const) {
    const history = server();
    const reservation = history.reserve("authority-edit");
    assert.ok(reservation && history[method](reservation, []));
    assert.equal(history.acknowledgeServerAction("authority-edit", 0, true), "retained");
    assert.equal(history.length, 1);
    assert.equal(history.discardPending("authority-edit"), false);
  }
});

test("removing an older server-confirmed empty action preserves later authored changes", () => {
  const history = server();
  const empty = history.commit("structure", []);
  const later = history.commit("typing", [{ key: "body", before: "A", after: "B" }]);
  assert.ok(empty && later);
  assert.equal(history.acknowledgeServerAction(empty, 0, false), "removed");
  assert.equal(history.length, 1);
  assert.equal(history.position, 1);
  assert.equal(history.actionFor("undo"), later);
  assert.equal(history.read("body"), "B");
});

test("failed prepared publication leaves the cursor intact for committed recovery", () => {
  let fail = false;
  const history = server((_changes, context) => { if (fail && context.mode === "prepared") throw new Error("client publication failed"); });
  const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }]);
  assert.ok(id);
  const navigation = history.navigation("undo"), reservation = history.reserveNavigation("undo", "navigation");
  assert.ok(navigation && reservation);
  fail = true;
  assert.throws(() => history.publishNavigation(reservation, "undo", navigation.changes), /client publication failed/);
  assert.equal(history.position, 1);
  assert.equal(history.read("body"), "B");
  assert.ok(history.reserved(reservation));
  history.close();
  assert.equal(history.reserveNavigation("undo", "new-command"), null);
});

test("default local history keeps its existing no-op and local navigation behavior", () => {
  const history = new SessionHistory("local", new Map([["body", "A"]]));
  assert.equal(history.commit("typing", []), null);
  const id = history.commit("typing", [{ key: "body", before: "A", after: "B" }], "group");
  assert.ok(id);
  assert.equal(history.commit("typing", [{ key: "body", before: "B", after: "A" }], "group"), null);
  assert.equal(history.length, 0);
  history.commit("typing", [{ key: "body", before: "A", after: "C" }]);
  assert.ok(history.undo() && history.redo());
  assert.equal(history.read("body"), "C");
});
