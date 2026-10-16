import assert from "node:assert/strict";
import test from "node:test";
import { applicationTabActive, applicationTabLock, claimApplicationTab, type TabLockRequest } from "../src/background/tab";

function locks() {
  let held = false;
  const requests: string[] = [], pending = new Set<Promise<void>>();
  const request: TabLockRequest = async (name, work) => {
    requests.push(name);
    if (held) { await work(false); return; }
    held = true;
    const task = work(true); pending.add(task);
    try { await task; } finally { held = false; pending.delete(task); }
  };
  return { request, requests, released: () => Promise.all([...pending]) };
}

test("one application tab excludes every other tab before mounting actions", async () => {
  const pool = locks(), active = await claimApplicationTab(pool.request); assert.ok(active);
  assert.equal(applicationTabActive(), true);
  assert.equal(await claimApplicationTab(pool.request), null);
  assert.equal(await claimApplicationTab(pool.request), null);
  assert.deepEqual(pool.requests, [applicationTabLock, applicationTabLock, applicationTabLock]);
  active.release(); await pool.released(); assert.equal(applicationTabActive(), false);
});

test("closing the active tab allows a later tab to acquire the same application lock", async () => {
  const pool = locks(), first = await claimApplicationTab(pool.request); assert.ok(first);
  first.release(); first.release(); await pool.released();
  const next = await claimApplicationTab(pool.request); assert.ok(next);
  assert.equal(await claimApplicationTab(pool.request), null);
  next.release(); await pool.released();
});

test("simultaneous tab claims grant exactly one active interface", async () => {
  const pool = locks(), contenders = await Promise.all([claimApplicationTab(pool.request), claimApplicationTab(pool.request)]);
  const granted = contenders.filter(lease => lease !== null);
  assert.equal(granted.length, 1); assert.equal(contenders.filter(lease => lease === null).length, 1);
  const active = granted[0]; assert.ok(active); active.release(); await pool.released();
});

test("an unavailable or failed tab lock never grants application access", async () => {
  await assert.rejects(claimApplicationTab(null), /TAB_LOCK_UNAVAILABLE/u);
  await assert.rejects(claimApplicationTab(() => Promise.reject(new Error("Lock denied"))), /Lock denied/u);
  await assert.rejects(claimApplicationTab(() => { throw new Error("Lock setup failed"); }), /Lock setup failed/u);
});
