const { expect, test } = require("./fixtures");
const { medicationDialog, scheduleRow, uniqueName } = require("./helpers");

async function expectNoHorizontalOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
}

async function expectDialogInsideViewport(page, dialog) {
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  const viewport = page.viewportSize();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);

  const [cancelBox, saveBox] = await Promise.all([
    dialog.getByRole("button", { name: "取消" }).boundingBox(),
    dialog.getByRole("button", { name: "保存用药" }).boundingBox(),
  ]);
  expect(cancelBox).not.toBeNull();
  expect(saveBox).not.toBeNull();
  const overlap = !(
    cancelBox.x + cancelBox.width <= saveBox.x ||
    saveBox.x + saveBox.width <= cancelBox.x ||
    cancelBox.y + cancelBox.height <= saveBox.y ||
    saveBox.y + saveBox.height <= cancelBox.y
  );
  expect(overlap).toBeFalsy();
}

const viewports = [
  { width: 320, height: 760 },
  { width: 390, height: 844 },
  { width: 1280, height: 900 },
];

for (const viewport of viewports) {
  test(`${viewport.width}px 下三视图与用药编辑器无溢出或控制台错误`, async ({
    page,
    medicationApi,
  }) => {
    const nameMarker = uniqueName(`响应式${viewport.width}`);
    const longName = `${"长".repeat(80 - Array.from(nameMarker).length)}${nameMarker}`;
    expect(Array.from(longName)).toHaveLength(80);
    const medication = await medicationApi.create({
      name: longName,
      schedules: [
        {
          dose: "1片",
          instructions: "服".repeat(160),
          anchor: "breakfast",
          offsetMinutes: 20,
        },
        {
          dose: "2片",
          instructions: "午餐后服用",
          anchor: "lunch",
          offsetMinutes: 20,
        },
        {
          dose: "3片",
          instructions: "晚餐后服用",
          anchor: "dinner",
          offsetMinutes: 20,
        },
      ],
    });
    const diagnostics = [];
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        diagnostics.push(`console.${message.type()}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
    page.on("requestfailed", (request) => {
      diagnostics.push(
        `requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText}`,
      );
    });
    page.on("response", (response) => {
      if (response.status() >= 400) {
        diagnostics.push(`response ${response.status()}: ${response.url()}`);
      }
    });

    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.locator("#todayTitle")).toHaveText("今天的用药");
    await expectNoHorizontalOverflow(page);

    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.request().method() === "GET" &&
          new URL(response.url()).pathname === "/api/history" &&
          response.ok(),
      ),
      page.getByRole("tab", { name: "记录", exact: true }).click(),
    ]);
    await expect(page.locator("#historyTitle")).toHaveText("用药记录");
    await expectNoHorizontalOverflow(page);

    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.request().method() === "GET" &&
          new URL(response.url()).pathname === "/api/medications" &&
          response.ok(),
      ),
      page.getByRole("tab", { name: "计划", exact: true }).click(),
    ]);
    await expect(page.getByRole("heading", { name: longName, exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page
      .getByRole("button", { name: `编辑${longName}的每日安排` })
      .click();
    const editor = medicationDialog(page);
    await expect(editor).toBeVisible();
    await expectDialogInsideViewport(page, editor);
    await expectNoHorizontalOverflow(page);
    await expect(editor.getByLabel("药品名称")).toHaveValue(longName);
    await expect(scheduleRow(editor, 0).getByLabel("服用要求")).toHaveValue(
      "服".repeat(160),
    );

    const scrollMetrics = await editor
      .locator(".medication-dialog-scroll")
      .evaluate((element) => ({
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
      }));
    if (viewport.width <= 390) {
      expect(scrollMetrics.scrollHeight).toBeGreaterThan(scrollMetrics.clientHeight);
    }
    const thirdDose = scheduleRow(editor, 2).getByLabel("单次剂量");
    await thirdDose.scrollIntoViewIfNeeded();
    await expect(thirdDose).toBeVisible();
    const thirdDoseBox = await thirdDose.boundingBox();
    expect(thirdDoseBox).not.toBeNull();
    expect(thirdDoseBox.y).toBeGreaterThanOrEqual(0);
    expect(thirdDoseBox.y + thirdDoseBox.height).toBeLessThanOrEqual(
      viewport.height + 1,
    );
    await expectDialogInsideViewport(page, editor);

    expect(diagnostics).toEqual([]);
  });
}
