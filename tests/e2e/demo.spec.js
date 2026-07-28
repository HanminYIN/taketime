const { expect, test } = require("./fixtures");

async function openDemo(page) {
  const response = await page.request.post("/api/demo-access", {
    data: { phrase: "测试演示口令" },
  });
  expect(response.ok()).toBeTruthy();
  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: "准备开始今天的用药" })).toBeVisible();
  await page.getByRole("button", { name: "开始演示" }).click();
}

function timelineIntake(page, itemId) {
  return page.locator(`.timeline [data-demo-intake-id="${itemId}"]`);
}

function timelineGroupFor(page, itemId) {
  return timelineIntake(page, itemId).locator("xpath=ancestor::section[contains(@class, 'timeline-group')]");
}

test("间隔模式按实际签到滚动调整同药后续时间", async ({ page }) => {
  await openDemo(page);
  await page.getByLabel("模拟签到").selectOption("30");
  await timelineIntake(page, 1).click();

  await expect(page.locator("#demoAdjustmentStatus")).toContainText(
    "同药后续 2 项延后 30 分钟",
  );
  await expect(timelineGroupFor(page, 7)).toContainText("12:45");
  await expect(timelineGroupFor(page, 7)).toContainText(
    "较原计划延后 30 分钟",
  );
  await expect(timelineGroupFor(page, 10)).toContainText("18:00");
});

test("作息模式签到不会推动后续安排", async ({ page }) => {
  await openDemo(page);
  await page.getByLabel("模拟签到").selectOption("30");
  await timelineIntake(page, 2).click();

  await expect(page.locator("#demoAdjustmentStatus")).toContainText(
    "跟随作息”不会推动同药后续时间",
  );
  await expect(page.locator("#completedCount")).toHaveText("1");
});

test("超出安全窗口时只记录签到而不自动调整", async ({ page }) => {
  await openDemo(page);
  await page.getByLabel("模拟签到").selectOption("180");
  await timelineIntake(page, 1).click();

  await expect(page.locator("#demoAdjustmentStatus")).toContainText(
    "偏移超过 120 分钟",
  );
  await expect(timelineGroupFor(page, 7)).toContainText("12:15");
  await expect(timelineGroupFor(page, 7)).not.toContainText("较原计划");
});

test("撤销签到会重放并恢复后续计划", async ({ page }) => {
  await openDemo(page);
  await timelineIntake(page, 1).click();
  await expect(timelineGroupFor(page, 7)).toContainText("12:45");

  await page.getByRole("button", { name: "撤销", exact: true }).click();
  await expect(page.locator("#completedCount")).toHaveText("0");
  await expect(timelineGroupFor(page, 7)).toContainText("12:15");
  await expect(timelineGroupFor(page, 7)).not.toContainText("较原计划");
});

test("计划页说明每种药采用的时间模式", async ({ page }) => {
  await openDemo(page);
  await page.getByRole("tab", { name: "计划", exact: true }).click();

  const plan = page.locator("#planList");
  await expect(plan).toContainText("示例药 A");
  await expect(plan).toContainText("3 次/日 · 跟随上次服用");
  await expect(plan).toContainText("1 次/日 · 跟随作息");
  await expect(plan).toContainText("2 次/日 · 跟随用餐");
});

for (const viewport of [
  { width: 320, height: 760 },
  { width: 390, height: 844 },
  { width: 1280, height: 900 },
]) {
  test(`${viewport.width}px 下演示控制与三视图完整可用`, async ({ page }) => {
    const diagnostics = [];
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        diagnostics.push(`console.${message.type()}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => diagnostics.push(`pageerror: ${error.message}`));
    page.on("requestfailed", (request) => {
      diagnostics.push(`requestfailed: ${request.url()} ${request.failure()?.errorText}`);
    });

    await page.setViewportSize(viewport);
    await openDemo(page);

    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);

    for (const control of [
      page.getByLabel("模拟签到"),
      page.getByRole("button", { name: "撤销", exact: true }),
      page.getByRole("button", { name: "重置", exact: true }),
    ]) {
      await expect(control).toBeVisible();
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box.height).toBeGreaterThanOrEqual(44);
    }

    await page.getByRole("tab", { name: "记录", exact: true }).click();
    await expect(page.getByRole("heading", { name: "用药记录" })).toBeVisible();
    await page.getByRole("tab", { name: "计划", exact: true }).click();
    await expect(page.getByRole("heading", { name: "用药计划" })).toBeVisible();

    const finalDimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(finalDimensions.scrollWidth).toBeLessThanOrEqual(
      finalDimensions.clientWidth,
    );
    expect(diagnostics).toEqual([]);
  });
}
