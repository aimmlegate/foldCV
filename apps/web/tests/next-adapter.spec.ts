import { expect, test, type Page } from "@playwright/test";

async function select(page: Page, startField: string, start: number, endField = startField, end = start) {
  await page.evaluate(({ startField, start, endField, end }) => {
    const a = document.querySelector(`[data-field-content="${startField}"]`);
    const b = document.querySelector(`[data-field-content="${endField}"]`);
    const root = document.querySelector<HTMLElement>('[contenteditable="true"]');
    if (!a || !b || !root) throw new Error("Proof fields are missing");
    const first = document.createTreeWalker(a, NodeFilter.SHOW_TEXT).nextNode();
    const last = document.createTreeWalker(b, NodeFilter.SHOW_TEXT).nextNode();
    if (!first || !last) throw new Error("Proof text is missing");
    root.focus(); window.getSelection()?.setBaseAndExtent(first, start, last, end);
    document.dispatchEvent(new Event("selectionchange"));
  }, { startField, start, endField, end });
}

test.beforeEach(async ({ page }) => {
  await page.goto("/adapter-proof.html");
  await expect(page.locator('[data-field-content="job:b/tasks"]')).toHaveText("Task B");
});

test("one editor captures both jobs and dates with UTF-16 emoji and newline spans", async ({ page }) => {
  await expect(page.locator('[contenteditable="true"]')).toHaveCount(1);
  await select(page, "job:a/context", 6, "job:b/context", 4);
  const expected = { direction: "forward", spans: [
    { fieldId: "job:a/context", range: { start: 6, end: 17 }, capturedText: "😀\n\nContext" },
    { fieldId: "job:a/period:p/startText", range: { start: 0, end: 4 }, capturedText: "2021" },
    { fieldId: "job:a/tasks", range: { start: 0, end: 6 }, capturedText: "Task A" },
    { fieldId: "job:b/context", range: { start: 0, end: 4 }, capturedText: "Beta" },
  ] };
  await expect(page.locator('[data-proof="selection"]')).toHaveText(JSON.stringify(expected));
  await select(page, "job:b/context", 4, "job:a/context", 7);
  await expect(page.locator('[data-proof="selection"]')).toHaveText(JSON.stringify({ ...expected, direction: "backward" }));
});

test("disabled native history routes unfinished buffer and consumed pointer to slot restore", async ({ page }) => {
  await select(page, "job:a/context", 17);
  await page.keyboard.type("x");
  await expect(page.locator('[data-field-content="job:a/context"]')).toHaveText("Alpha 😀\n\nContextx");
  await page.keyboard.press("Control+z");
  await expect(page.locator('[data-field-content="job:a/context"]')).toHaveText("Alpha 😀\n\nContext");
  await page.keyboard.press("Meta+z");
  await expect(page.locator('[data-field-content="job:a/context"]')).toHaveText("Previous 😀");
  await page.keyboard.press("Meta+z");
  await page.keyboard.press("Meta+Shift+z");
  await page.keyboard.press("Control+y");
  await expect(page.locator('[data-field-content="job:a/context"]')).toHaveText("Previous 😀");
  await expect(page.locator('[data-proof="restores"]')).toHaveText("3");
  await expect(page.locator('[data-proof="buffer"]')).toHaveText("1");
  await page.getByRole("button", { name: "Проверить history" }).click();
  await expect(page.locator('[data-proof="history"]')).toHaveAttribute("data-enabled", "false");
});

test("IME emits only completed text and captures no active composition", async ({ page }) => {
  await select(page, "job:a/tasks", 6);
  await page.evaluate(() => {
    const root = document.querySelector('[contenteditable="true"]');
    const field = document.querySelector('[data-field-content="job:a/tasks"]');
    if (!root || !field) throw new Error("Proof editor is missing");
    const text = document.createTreeWalker(field, NodeFilter.SHOW_TEXT).nextNode();
    if (!text) throw new Error("Proof text is missing");
    root.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true }));
    text.textContent = "Task A入力";
    root.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertCompositionText", data: "入力", isComposing: true }));
  });
  await expect(page.locator('[data-proof="selection"]')).toHaveText("null");
  await expect(page.locator('[data-proof="buffer"]')).toHaveText("0");
  await page.getByRole("button", { name: "Ответ сервера", exact: true }).evaluate(button => button.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  await expect(page.locator('[data-field-content="job:a/context"]')).toHaveText("Alpha 😀\n\nContext");
  await page.evaluate(() => {
    const root = document.querySelector('[contenteditable="true"]');
    root?.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "入力" }));
    root?.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: "入力" }));
  });
  await expect(page.locator('[data-proof="buffer"]')).toHaveText("1");
  await expect(page.locator('[data-field-content="job:a/tasks"]')).toHaveText("Task A入力");
});

test("owned date popover keeps one job session and leaving for another job completes it", async ({ page }) => {
  await select(page, "job:a/period:p/startText", 4);
  await expect(page.locator('[data-proof="slot"]')).toHaveText("job:a");
  await page.getByRole("button", { name: "Дата: Начало работы" }).click();
  await expect(page.getByRole("button", { name: "Вернуться к тексту" })).toBeFocused();
  await expect(page.locator('[data-proof="slot"]')).toHaveText("job:a");
  await expect(page.locator('[data-proof="departures"]')).toHaveText("[]");
  await page.keyboard.press("Escape");
  await select(page, "job:b/context", 2);
  await expect(page.locator('[data-proof="slot"]')).toHaveText("job:b");
  await expect(page.locator('[data-proof="departures"]')).toHaveText('["job:a"]');
});

test("backend field patch keeps other-field cursor and produces no edit echo", async ({ page }) => {
  await page.locator('[contenteditable="true"]').evaluate(editor => editor.setAttribute("data-proof-instance", "original"));
  await select(page, "job:b/context", 2);
  await page.getByRole("button", { name: "Ответ сервера" }).click();
  await expect(page.locator('[data-field-content="job:a/context"]')).toHaveText("Patched 😀\n\nText");
  await expect(page.locator('[data-proof="buffer"]')).toHaveText("0");
  await expect(page.locator('[contenteditable="true"]')).toHaveAttribute("data-proof-instance", "original");
  const caret = await page.evaluate(() => {
    const selection = window.getSelection();
    return { offset: selection?.anchorOffset,
      field: selection?.anchorNode?.parentElement?.closest("[data-field-content]")?.getAttribute("data-field-content") };
  });
  expect(caret).toEqual({ offset: 2, field: "job:b/context" });
  await select(page, "job:a/context", 16);
  await page.keyboard.press("Enter");
  await page.keyboard.type("🙂");
  await expect(page.locator('[data-field-content="job:a/context"]')).toHaveText("Patched 😀\n\nText\n🙂");
  expect(await page.locator('[data-field-content="job:a/context"]').textContent()).toBe("Patched 😀\n\nText\n🙂");
  await expect(page.locator(".next-field[data-field-id]")).toHaveCount(5);
});

test("stale backend text cannot replace a newer local buffer", async ({ page }) => {
  await select(page, "job:a/context", 17);
  await page.keyboard.type("x");
  await page.getByRole("button", { name: "Устаревший ответ" }).click();
  expect(await page.locator('[data-field-content="job:a/context"]').textContent()).toBe("Alpha 😀\n\nContextx");
  await expect(page.locator('[data-proof="buffer"]')).toHaveText("1");
});
