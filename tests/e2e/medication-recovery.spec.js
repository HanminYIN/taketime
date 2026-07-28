const { expect, test } = require("./fixtures");
const {
  medicationDialog,
  navigateToPlan,
  scheduleRow,
  uniqueName,
} = require("./helpers");

const onceDaily = (instructions = "测试安排") => [
  {
    dose: "1片",
    instructions,
    anchor: "wake",
    offsetMinutes: 0,
  },
];

test("同名药物提示可切换到既有药物而不覆盖原安排", async ({
  page,
  medicationApi,
}) => {
  const source = await medicationApi.create({
    name: uniqueName("待改名药物"),
    schedules: onceDaily("原药物安排"),
  });
  const target = await medicationApi.create({
    name: uniqueName("既有同名药物"),
    schedules: [
      {
        dose: "2片",
        instructions: "目标药物安排",
        anchor: "lunch",
        offsetMinutes: 0,
      },
    ],
  });

  await navigateToPlan(page);
  await page
    .getByRole("button", { name: `编辑${source.name}的每日安排` })
    .click();
  const editor = medicationDialog(page);
  await editor.getByLabel("药品名称").fill(target.name);
  await editor.getByRole("button", { name: "保存用药" }).click();

  await expect(editor.locator("#medicationDialogErrorMessage")).toHaveText(
    "该药物已存在，请载入现有药物并添加服用时间。",
  );
  const reloadButton = editor.getByRole("button", { name: "载入最新安排" });
  await expect(reloadButton).toBeVisible();
  const nameInput = editor.getByLabel("药品名称");
  await expect(nameInput).toBeFocused();
  await expect(nameInput).toHaveAttribute("aria-invalid", "true");
  await expect(nameInput).toHaveValue(target.name);

  page.once("dialog", (confirmation) => confirmation.accept());
  const reloadResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === "/api/medications" &&
      response.ok(),
  );
  await reloadButton.click();
  await reloadResponsePromise;

  await expect(editor.locator('input[name="id"]')).toHaveValue(String(target.id));
  await expect(editor.getByLabel("药品名称")).toHaveValue(target.name);
  await expect(scheduleRow(editor, 0).getByLabel("关联时段")).toHaveValue(
    "lunch",
  );
  await expect(scheduleRow(editor, 0).getByLabel("单次剂量")).toHaveValue("2片");
  await expect(editor.locator("#medicationDialogError")).toBeHidden();

  const plan = await medicationApi.getPlan();
  expect(plan.medications.find((item) => item.id === source.id).name).toBe(
    source.name,
  );
  expect(plan.medications.find((item) => item.id === target.id).schedules).toHaveLength(
    1,
  );
});

test("过期 revision 收到 409 后保留草稿并可载入远端最新安排", async ({
  page,
  medicationApi,
}) => {
  const created = await medicationApi.create({
    name: uniqueName("并发冲突"),
    schedules: onceDaily("初始安排"),
  });

  await navigateToPlan(page);
  await page
    .getByRole("button", { name: `编辑${created.name}的每日安排` })
    .click();
  const editor = medicationDialog(page);
  const doseInput = scheduleRow(editor, 0).getByLabel("单次剂量");
  await doseInput.fill("3片本地草稿");

  const remote = await medicationApi.update(created, {
    schedules: created.schedules.map((schedule) => ({
      ...schedule,
      instructions: "远端已经更新",
    })),
  });
  expect(remote.revision).toBe(created.revision + 1);

  const conflictResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === `/api/medications/${created.id}`,
  );
  await editor.getByRole("button", { name: "保存用药" }).click();
  expect((await conflictResponsePromise).status()).toBe(409);

  await expect(doseInput).toHaveValue("3片本地草稿");
  await expect(editor.locator("#medicationDialogErrorMessage")).toContainText(
    "药物安排已被更新，请刷新后重试",
  );
  const reloadButton = editor.getByRole("button", { name: "载入最新安排" });
  await expect(reloadButton).toBeFocused();

  page.once("dialog", (confirmation) => confirmation.accept());
  const reloadResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === "/api/medications" &&
      response.ok(),
  );
  await reloadButton.click();
  await reloadResponsePromise;

  await expect(editor.locator('input[name="revision"]')).toHaveValue(
    String(remote.revision),
  );
  await expect(scheduleRow(editor, 0).getByLabel("单次剂量")).toHaveValue("1片");
  await expect(scheduleRow(editor, 0).getByLabel("服用要求")).toHaveValue(
    "远端已经更新",
  );
  await expect(editor.locator("#medicationDialogError")).toBeHidden();
});

test("完全断网时保留草稿并在恢复后载入最新安排再保存", async ({
  page,
  medicationApi,
}) => {
  const created = await medicationApi.create({
    name: uniqueName("断网恢复"),
    schedules: onceDaily("联网状态"),
  });
  await navigateToPlan(page);
  await page
    .getByRole("button", { name: `编辑${created.name}的每日安排` })
    .click();
  const editor = medicationDialog(page);
  const instructionsInput = scheduleRow(editor, 0).getByLabel("服用要求");
  await instructionsInput.fill("断网期间的草稿");

  const medicationRequestPattern = /\/api\/medications(?:\/\d+)?$/;
  const blockMedicationRequests = async (route) => {
    const method = route.request().method();
    if (method === "PUT" || method === "GET") {
      await route.abort("internetdisconnected");
      return;
    }
    await route.continue();
  };
  await page.route(medicationRequestPattern, blockMedicationRequests);
  await editor.getByRole("button", { name: "保存用药" }).click();

  await expect(editor.locator("#medicationDialogErrorMessage")).toHaveText(
    "保存结果尚未确认，当前内容已保留。恢复连接后请载入最新安排，再决定是否重试。",
  );
  await expect(instructionsInput).toHaveValue("断网期间的草稿");
  const reloadButton = editor.getByRole("button", { name: "载入最新安排" });
  await expect(reloadButton).toBeFocused();

  await page.unroute(medicationRequestPattern, blockMedicationRequests);
  page.once("dialog", (confirmation) => confirmation.accept());
  const reloadResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === "/api/medications" &&
      response.ok(),
  );
  await reloadButton.click();
  await reloadResponsePromise;
  await expect(scheduleRow(editor, 0).getByLabel("服用要求")).toHaveValue(
    "联网状态",
  );
  await expect(editor.locator("#medicationDialogError")).toBeHidden();

  await scheduleRow(editor, 0).getByLabel("服用要求").fill("恢复连接后保存");
  const saveResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === `/api/medications/${created.id}`,
  );
  await editor.getByRole("button", { name: "保存用药" }).click();
  expect((await saveResponsePromise).ok()).toBeTruthy();
  await expect(editor).toBeHidden();
});

test("服务端已提交但响应丢失时自动对账并确认保存", async ({
  page,
  medicationApi,
}) => {
  const created = await medicationApi.create({
    name: uniqueName("响应丢失"),
    schedules: onceDaily("提交前"),
  });
  await navigateToPlan(page);
  await page
    .getByRole("button", { name: `编辑${created.name}的每日安排` })
    .click();
  const editor = medicationDialog(page);
  await scheduleRow(editor, 0).getByLabel("单次剂量").fill("4片");

  let submitted = false;
  await page.route(`**/api/medications/${created.id}`, async (route) => {
    if (!submitted && route.request().method() === "PUT") {
      submitted = true;
      const serverResponse = await route.fetch();
      expect(serverResponse.ok()).toBeTruthy();
      await route.abort("connectionreset");
      return;
    }
    await route.continue();
  });

  await editor.getByRole("button", { name: "保存用药" }).click();
  await expect(editor).toBeHidden();
  await expect(page.locator("#toast")).toContainText("核对并确认保存");

  const plan = await medicationApi.getPlan();
  const saved = plan.medications.find((medication) => medication.id === created.id);
  expect(saved.revision).toBe(created.revision + 1);
  expect(saved.schedules[0].dose).toBe("4片");
});
