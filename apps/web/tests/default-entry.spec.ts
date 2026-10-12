import { expect, test } from "@playwright/test";

test("task A21 Vite default serves the recovery root and keeps the explicit legacy entry", async ({ page }) => {
  await page.goto("/");await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Создать резюме", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Настройки", exact: true })).toBeVisible();
  await page.goto("/legacy.html");await expect(page.getByRole("heading", { name: "Из исходника — в готовое резюме", exact: true })).toBeVisible();
  await expect(page.locator('[data-app="foldcv-next"]')).toHaveCount(0);
});
