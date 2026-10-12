import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/*", async (route) => {
    const host = new URL(route.request().url()).hostname;
    if (host === "127.0.0.1" || host === "localhost") {
      await route.continue();
    } else {
      await route.abort();
    }
  });
});

test("Russian shell keeps generation closed", async ({ page }) => {
  await page.goto("/legacy.html");
  await expect(page.getByRole("heading", { name: "Исходное резюме" })).toBeVisible();
  await expect(page.getByText("Generation is unavailable: this CLI profile has not passed the safety check.")).toBeVisible();
  await expect(page.getByText("Обработка и генерация текста недоступны", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Извлечь вставленный текст" })).toBeDisabled();
  await page.getByLabel("Вставьте текст резюме").fill("Вымышленный инженер");
  await expect(page.getByLabel("Вставьте текст резюме")).toHaveValue("Вымышленный инженер");
});

test("manual theme persists and system theme follows OS changes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/legacy.html");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByLabel("Тема").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.getByLabel("Тема")).toHaveValue("dark");
  await page.getByLabel("Тема").selectOption("system");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("startup secret is exchanged once and removed from the address", async ({ page }) => {
  const payloads: unknown[] = [];
  await page.route("**/v1/session/exchange", async (route) => {
    payloads.push(route.request().postDataJSON() as unknown);
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"sessionReady":true}' });
  });
  await page.goto("/legacy.html#secret=synthetic-secret");
  await expect(page.getByRole("heading", { name: "Исходное резюме" })).toBeVisible();
  await expect(page).toHaveURL("http://127.0.0.1:4173/legacy.html");
  expect(payloads).toEqual([{ secret: "synthetic-secret" }]);
  await page.reload();
  expect(payloads).toHaveLength(1);
});
