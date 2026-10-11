import type { Page } from "@playwright/test";

export async function acknowledgeVisibleWarnings(page: Page): Promise<void> {
  await page.getByRole("tab", { name: "Проверки" }).click();
  const pending = page.getByRole("tabpanel", { name: "Проверки" })
    .getByRole("button", { name: "Подтвердить проверку" });
  while (await pending.count()) await pending.first().click();
}

export async function excludeUnrepresentedFacts(page: Page): Promise<void> {
  await page.getByRole("tab", { name: "Проверки" }).click();
  const facts = page.locator("#coverage-facts");
  await facts.locator("summary").click();
  const unresolved = facts.locator("li").filter({ hasText: "Не решён" });
  while (await unresolved.count()) {
    const row = unresolved.first();
    await row.getByRole("textbox").fill("Selected legacy view omits this separate source fact.");
    await row.getByRole("button", { name: "Исключить" }).click();
  }
}
