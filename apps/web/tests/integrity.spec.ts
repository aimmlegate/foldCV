import { expect, test } from "@playwright/test";

type Result = { bytes: number; sources: number; valid: boolean; proofMs: number;
  samplesMs: number[]; candidate32SamplesMs: number[]; sameLengthMutationRejected: boolean; copyAccepted: boolean };

test("32 MiB browser source integrity rejects an in-place same-length change", async ({ page }) => {
  await page.goto("/bench/integrity.html");
  const output = page.locator("#result");
  await expect(output).not.toHaveText("running", { timeout: 30_000 });
  const result = JSON.parse(await output.textContent() ?? "null") as Result;
  expect(result.bytes).toBe(32 * 1024 * 1024);
  expect(result.sources).toBe(6);
  expect(result.valid).toBe(true);
  expect(result.sameLengthMutationRejected).toBe(true);
  expect(result.copyAccepted).toBe(true);
  expect(result.samplesMs).toHaveLength(9);
  expect(result.candidate32SamplesMs).toHaveLength(9);
  console.log(`browser source integrity: ${JSON.stringify(result)}`);
});
