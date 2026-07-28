const { expect, test } = require("./fixtures");
const {
  expectPlanSummary,
  fillSchedule,
  medicationCard,
  medicationDialog,
  navigateToPlan,
  openAddMedicationDialog,
  scheduleRow,
  uniqueName,
} = require("./helpers");

test("用药安排可从每日一次原子更新为三次并停用", async ({
  page,
  medicationApi,
}) => {
  const baseline = await medicationApi.getPlan();
  const name = uniqueName("一次改三次");

  await navigateToPlan(page);
  const editor = await openAddMedicationDialog(page);
  await editor.getByLabel("药品名称").fill(name);
  await fillSchedule(scheduleRow(editor, 0), {
    anchor: "breakfast",
    relation: "after",
    minutes: 20,
    dose: "1片",
    instructions: "早餐后服用",
  });

  const createResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/medications",
  );
  await editor.getByRole("button", { name: "保存用药" }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status()).toBe(201);
  const created = (await createResponse.json()).medication;
  medicationApi.track(created.id);

  await expect(editor).toBeHidden();
  await expectPlanSummary(
    page,
    baseline.summary.medicationCount + 1,
    baseline.summary.dailyAdministrationCount + 1,
  );

  await page
    .getByRole("button", { name: `编辑${name}的每日安排` })
    .click();
  await expect(editor).toHaveAccessibleName("编辑用药");
  await editor.getByRole("button", { name: "添加服用时间" }).click();
  await editor.getByRole("button", { name: "添加服用时间" }).click();
  await expect(editor.locator("#scheduleEditorFrequency")).toHaveText("3 次/日");

  await fillSchedule(scheduleRow(editor, 1), {
    anchor: "lunch",
    relation: "after",
    minutes: 20,
    dose: "1片",
    instructions: "午餐后服用",
  });
  await fillSchedule(scheduleRow(editor, 2), {
    anchor: "dinner",
    relation: "after",
    minutes: 20,
    dose: "1片",
    instructions: "晚餐后服用",
  });

  const updateResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === `/api/medications/${created.id}`,
  );
  await editor.getByRole("button", { name: "保存用药" }).click();
  const updateResponse = await updateResponsePromise;
  expect(updateResponse.ok()).toBeTruthy();
  await expect(editor).toBeHidden();

  const card = medicationCard(page, name);
  await expect(card).toContainText("3 次/日");
  await expect(card).toContainText("早餐后 20 分钟");
  await expect(card).toContainText("午餐后 20 分钟");
  await expect(card).toContainText("晚餐后 20 分钟");
  await expectPlanSummary(
    page,
    baseline.summary.medicationCount + 1,
    baseline.summary.dailyAdministrationCount + 3,
  );

  const updatedPlan = await medicationApi.getPlan();
  const updated = updatedPlan.medications.find(
    (medication) => medication.id === created.id,
  );
  expect(updated.schedules).toHaveLength(3);
  expect(updated.schedules.map((schedule) => schedule.anchor)).toEqual([
    "breakfast",
    "lunch",
    "dinner",
  ]);
  expect(updatedPlan.summary).toEqual({
    medicationCount: baseline.summary.medicationCount + 1,
    dailyAdministrationCount: baseline.summary.dailyAdministrationCount + 3,
  });

  await page
    .getByRole("button", { name: `编辑${name}的每日安排` })
    .click();
  page.once("dialog", (confirmation) => confirmation.accept());
  const archiveResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      new URL(response.url()).pathname === `/api/medications/${created.id}`,
  );
  await editor.getByRole("button", { name: "停用该药物" }).click();
  expect((await archiveResponsePromise).ok()).toBeTruthy();

  await expect(editor).toBeHidden();
  await expect(card).toHaveCount(0);
  await expectPlanSummary(
    page,
    baseline.summary.medicationCount,
    baseline.summary.dailyAdministrationCount,
  );
});

test("重复提醒时段被阻止且删除冲突行后清除错误", async ({
  page,
  medicationApi,
}) => {
  const baseline = await medicationApi.getPlan();
  await navigateToPlan(page);
  const editor = await openAddMedicationDialog(page);
  await editor.getByLabel("药品名称").fill(uniqueName("重复时段"));

  await fillSchedule(scheduleRow(editor, 0), {
    anchor: "breakfast",
    relation: "after",
    minutes: 20,
  });
  await editor.getByRole("button", { name: "添加服用时间" }).click();
  await fillSchedule(scheduleRow(editor, 1), {
    anchor: "breakfast",
    relation: "after",
    minutes: 20,
  });

  await editor.getByRole("button", { name: "保存用药" }).click();
  const conflictingAnchor = scheduleRow(editor, 1).getByLabel("关联时段");
  await expect(conflictingAnchor).toHaveAttribute("aria-invalid", "true");
  await expect(conflictingAnchor).toBeFocused();
  await expect(editor.locator("#medicationDialogErrorMessage")).toHaveText(
    "第 1 次与第 2 次的服用时间重复，请调整后保存。",
  );

  await scheduleRow(editor, 1).getByRole("button", { name: /移除/ }).click();
  await expect(editor.locator("#medicationDialogError")).toBeHidden();
  await expect(scheduleRow(editor, 0).getByLabel("关联时段")).not.toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await expect(editor.locator("#scheduleEditorFrequency")).toHaveText("1 次/日");

  const after = await medicationApi.getPlan();
  expect(after.summary).toEqual(baseline.summary);
});

test("空白与 Unicode 字符边界在提交前得到一致校验", async ({
  page,
  medicationApi,
}) => {
  await navigateToPlan(page);
  const editor = await openAddMedicationDialog(page);
  const nameInput = editor.getByLabel("药品名称");
  const row = scheduleRow(editor, 0);
  const doseInput = row.getByLabel("单次剂量");
  const instructionsInput = row.getByLabel("服用要求");
  let createRequests = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/medications"
    ) {
      createRequests += 1;
    }
  });

  await nameInput.fill("   ");
  await fillSchedule(row, { anchor: "wake", dose: "   " });
  await editor.getByRole("button", { name: "保存用药" }).click();
  await expect(nameInput).toHaveAttribute("aria-invalid", "true");
  await expect(doseInput).toHaveAttribute("aria-invalid", "true");
  expect(await nameInput.evaluate((element) => element.validationMessage)).toBe(
    "请填写药品名称",
  );
  expect(await doseInput.evaluate((element) => element.validationMessage)).toBe(
    "请填写单次剂量",
  );
  expect(createRequests).toBe(0);

  const emoji = "💊";
  await nameInput.fill(emoji.repeat(81));
  await expect(nameInput).toHaveAttribute("aria-invalid", "true");
  expect(await nameInput.evaluate((element) => element.validationMessage)).toBe(
    "药品名称最多 80 个字符",
  );

  await nameInput.fill(emoji.repeat(80));
  await expect(nameInput).not.toHaveAttribute("aria-invalid", "true");
  await doseInput.fill("1片");
  await instructionsInput.fill("餐".repeat(161));
  await expect(instructionsInput).toHaveAttribute("aria-invalid", "true");
  expect(
    await instructionsInput.evaluate((element) => element.validationMessage),
  ).toBe("服用要求最多 160 个字符");
  expect(createRequests).toBe(0);

  await instructionsInput.fill("餐".repeat(160));
  const createResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/medications",
  );
  await editor.getByRole("button", { name: "保存用药" }).click();
  const response = await createResponsePromise;
  expect(response.status()).toBe(201);
  const created = (await response.json()).medication;
  medicationApi.track(created.id);
  expect(Array.from(created.name)).toHaveLength(80);
  expect(Array.from(created.schedules[0].instructions)).toHaveLength(160);
  expect(createRequests).toBe(1);
  await expect(editor).toBeHidden();
});

test("时间跟随方式保持单一选择并按需展开高级范围", async ({
  page,
  medicationApi,
}) => {
  const name = uniqueName("时间跟随设置");
  await navigateToPlan(page);
  const editor = await openAddMedicationDialog(page);
  const routineMode = editor.getByRole("radio", {
    name: "跟随作息",
  });
  const intervalMode = editor.getByRole("radio", {
    name: "跟随上次服药",
  });
  const maximum = editor.locator('[name="maxAutoShiftMinutes"]');
  await expect(routineMode).toBeChecked();
  await expect(intervalMode).not.toBeChecked();
  await expect(maximum).toBeDisabled();

  await intervalMode.check();
  await editor.getByText("高级设置", { exact: true }).click();
  await expect(maximum).toBeEnabled();
  await maximum.fill("45");
  await editor.getByLabel("药品名称").fill(name);
  await fillSchedule(scheduleRow(editor, 0), {
    anchor: "wake",
    dose: "1片",
  });
  await editor.getByRole("button", { name: "添加服用时间" }).click();
  await fillSchedule(scheduleRow(editor, 1), {
    anchor: "lunch",
    dose: "1片",
  });

  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/medications",
  );
  await editor.getByRole("button", { name: "保存用药" }).click();
  const response = await responsePromise;
  const saved = (await response.json()).medication;
  medicationApi.track(saved.id);
  expect(saved.timingMode).toBe("interval");
  expect(saved.adjustAfterIntake).toBe(true);
  expect(saved.maxAutoShiftMinutes).toBe(45);
  await expect(editor).toBeHidden();

  const card = medicationCard(page, name);
  await expect(card).toContainText("跟随上次服药");
  await expect(card).not.toContainText("45 分钟");
  await page.getByRole("button", { name: `编辑${name}的每日安排` }).click();
  await expect(intervalMode).toBeChecked();
  await editor.getByText("高级设置", { exact: true }).click();
  await expect(maximum).toHaveValue("45");
  await editor.getByRole("button", { name: "取消" }).click();
});

test("签到后解释同药后续时间的滚动调整", async ({
  page,
  request,
  medicationApi,
}) => {
  const name = uniqueName("滚动调整反馈");
  const medication = await medicationApi.create({
    name,
    timingMode: "interval",
    maxAutoShiftMinutes: 60,
    schedules: [
      {
        dose: "1片",
        instructions: "第一次",
        anchor: "wake",
        offsetMinutes: -20,
      },
      {
        dose: "1片",
        instructions: "第二次",
        anchor: "lunch",
        offsetMinutes: 0,
      },
    ],
  });
  const today = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const wakeResponse = await request.post("/api/wake-events", {
    data: { date: today },
  });
  expect(wakeResponse.ok()).toBeTruthy();

  await page.goto("/");
  await expect(page.locator("#todayTitle")).toHaveText("今天的用药");
  await page.locator("#timelineDetails > summary").click();
  const cards = page.locator(".medication-card").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });
  await expect(cards).toHaveCount(2);

  const intakeResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/intakes",
  );
  await cards.first().getByRole("button", { name: `记录${name}` }).click();
  const intakeResponse = await intakeResponsePromise;
  const payload = await intakeResponse.json();
  expect(payload.scheduleAdjustment.status).toBe("applied");
  expect(payload.scheduleAdjustment.shiftMinutes).toBe(20);
  expect(payload.scheduleAdjustment.affectedCount).toBe(1);
  await expect(page.locator("#intakeFeedbackList")).toContainText(
    "后续 1 项已按原定间隔顺延 20 分钟",
  );
  await expect(cards.last()).toContainText("服药时间推算");
  expect(medication.timingMode).toBe("interval");
  expect(medication.adjustAfterIntake).toBe(true);
});
