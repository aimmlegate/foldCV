import { expect, test } from "@playwright/test";

const ready = { state: "connected", version: "codex-cli 0.162.0-alpha.2", plan: "plus",
  models: ["gpt-6-luna", "gpt-6-sol"], selectedModel: null,
  quota: { state: "available", usedPercent: 25, resetsAt: 1800000000 },
  metadataReady: true, generationReady: false, experimentalMode: false };

test("experimental readiness follows selection and detach", async ({ page }) => {
  const experimental = { ...ready, version: "codex-cli 0.162.0-alpha.17.2", experimentalMode: true };
  await page.route("**/v1/host/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/detach") ? { ...experimental, state: "detached", models: [],
      selectedModel: null, metadataReady: false, generationReady: false } : path.endsWith("/select") ?
      { ...experimental, selectedModel: "gpt-6-luna", generationReady: true } : experimental;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/legacy.html");
  await page.getByRole("button", { name: "Refresh connection" }).click();
  await expect(page.getByText("Personal CLI experiment: sign in, refresh, and choose a model to enable generation.", { exact: false })).toBeVisible();
  await page.getByLabel("Reported model").selectOption("gpt-6-luna");
  await expect(page.getByText("Personal CLI experiment is ready.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Detach" }).click();
  await expect(page.getByText("Personal CLI experiment: sign in, refresh, and choose a model to enable generation.", { exact: false })).toBeVisible();
});

test("connection checks and selection require clicks; detach keeps editor work", async ({ page }) => {
  let hostCalls = 0;
  let generationCalls = 0;
  await page.route("**/v1/host/**", async (route) => {
    hostCalls += 1;
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/detach") ? { ...ready, state: "detached", models: [], selectedModel: null,
      plan: null, version: null, quota: { state: "unknown", usedPercent: null, resetsAt: null }, metadataReady: false }
      : path.endsWith("/select") ? { ...ready, selectedModel: "gpt-6-luna" } : ready;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  page.on("request", (request) => { if (/\/v1\/(normalize|draft|rewrite)$/.test(request.url())) generationCalls += 1; });
  await page.goto("/legacy.html");
  await expect(page.getByRole("heading", { name: "Codex connection" })).toBeVisible();
  expect(hostCalls).toBe(0);
  await page.getByRole("button", { name: "Загрузить вымышленный пример" }).click();
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await page.getByRole("button", { name: "1. Загрузка" }).click();
  expect(hostCalls).toBe(0);
  await page.getByRole("button", { name: "Refresh connection" }).click();
  await expect(page.getByLabel("Reported model")).toBeVisible();
  await page.getByLabel("Reported model").selectOption("gpt-6-luna");
  await expect(page.getByLabel("Reported model")).toHaveValue("gpt-6-luna");
  await page.getByRole("button", { name: "Detach" }).click();
  await expect(page.getByText("Disconnected from this app. Your CLI sign-in stays in place.")).toBeVisible();
  await page.getByRole("button", { name: "2. Редактор" }).click();
  await expect(page.getByText("Вымышленный пример", { exact: false }).first()).toBeVisible();
  expect(generationCalls).toBe(0);
});

test("distinct setup and quota states remain actionable", async ({ page }) => {
  const responses = [
    { ...ready, state: "cli_missing", models: [], version: null, plan: null, metadataReady: false },
    { ...ready, state: "launcher_unsupported", models: [], version: null, plan: null, metadataReady: false },
    { ...ready, state: "unsupported_version", models: [], plan: null, metadataReady: false },
    { ...ready, state: "login_required", models: [], plan: null, metadataReady: false },
    { ...ready, state: "api_key_mode", models: [], plan: null, metadataReady: false },
    { ...ready, state: "metadata_failed", models: [], plan: null, metadataReady: false },
    { ...ready, state: "quota_exhausted", quota: { state: "exhausted", usedPercent: 100, resetsAt: 1800000000 } },
    { ...ready, state: "unknown_limits", quota: { state: "unknown", usedPercent: null, resetsAt: null } },
  ];
  let index = 0;
  await page.route("**/v1/host/status", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(responses[index++]) });
  });
  await page.goto("/legacy.html");
  for (const expected of ["not found", "needs Node", "not supported", "Sign in with ChatGPT", "using an API key",
    "could not report", "reached plan limit", "plan limits are unavailable"]) {
    await page.getByRole("button", { name: "Refresh connection" }).click();
    await expect(page.getByRole("status")).toContainText(expected);
  }
  await expect(page.getByText("Plan limit: Unknown")).toBeVisible();
});

function latch() {
  let release = () => {};
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  return { waiting, release: () => release() };
}

test("detach during a pending refresh shows cleanup uncertainty and ignores its late result", async ({ page }) => {
  const started = latch();
  const releaseStatus = latch();
  const statusFinished = latch();
  const releaseDetach = latch();
  let detachCalls = 0;
  await page.route("**/v1/host/status", async (route) => {
    started.release();
    await releaseStatus.waiting;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ready) }).catch(() => undefined);
    statusFinished.release();
  });
  await page.route("**/v1/host/detach", async (route) => {
    detachCalls += 1;
    await releaseDetach.waiting;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      ...ready, state: "cleanup_blocked", version: null, plan: null, models: [],
      selectedModel: null, quota: { state: "unknown", usedPercent: null, resetsAt: null },
      metadataReady: false,
    }) });
  });
  await page.goto("/legacy.html");
  await page.getByRole("button", { name: "Refresh connection" }).click();
  await started.waiting;
  await expect(page.getByRole("button", { name: "Refresh connection" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Detach" })).toBeEnabled();
  await page.getByRole("button", { name: "Detach" }).click();
  await expect(page.getByRole("button", { name: "Detach" })).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Stopping this app's CLI operation");
  expect(detachCalls).toBe(1);
  releaseDetach.release();
  await expect(page.getByRole("status")).toContainText("Could not confirm that the CLI operation stopped safely");
  releaseStatus.release();
  await statusFinished.waiting;
  await expect(page.getByRole("status")).toContainText("Could not confirm that the CLI operation stopped safely");
  expect(detachCalls).toBe(1);
});
