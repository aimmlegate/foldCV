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
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Исходное резюме" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Генерация недоступна");
  await expect(page.getByRole("button", { name: "Обработать текст" })).toBeDisabled();
  await page.getByLabel("Вставьте текст резюме").fill("Вымышленный инженер");
  await expect(page.getByLabel("Вставьте текст резюме")).toHaveValue("Вымышленный инженер");
});

test("manual theme persists and system theme follows OS changes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
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
