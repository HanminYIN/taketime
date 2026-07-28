const { expect } = require("./fixtures");

let nameSequence = 0;

function uniqueName(prefix = "自动化测试药物") {
  nameSequence += 1;
  return `${prefix}-${process.pid}-${nameSequence}`;
}

async function navigateToPlan(page) {
  await page.goto("/");
  await expect(page.locator("#todayTitle")).toHaveText("今天的用药");
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === "/api/medications" &&
        response.ok(),
    ),
    page.getByRole("tab", { name: "计划", exact: true }).click(),
  ]);
  await expect(page.locator("#planList .plan-medication").first()).toBeVisible();
}

function medicationDialog(page) {
  return page.locator("#medicationDialog");
}

async function openAddMedicationDialog(page) {
  await page.getByRole("button", { name: "添加药物" }).click();
  const dialog = medicationDialog(page);
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAccessibleName("添加药物");
  return dialog;
}

function scheduleRow(dialog, index) {
  return dialog.getByRole("group", {
    name: `第 ${index + 1} 次服用安排`,
  });
}

async function fillSchedule(
  row,
  {
    anchor,
    relation = "at",
    minutes = 0,
    dose = "1片",
    instructions = "",
  },
) {
  await row.getByLabel("关联时段").selectOption(anchor);
  await row.getByLabel("相对位置").selectOption(relation);
  if (relation !== "at") {
    await row.getByRole("spinbutton", { name: "分钟", exact: true }).fill(
      String(minutes),
    );
  }
  await row.getByLabel("单次剂量").fill(dose);
  await row.getByLabel("服用要求").fill(instructions);
}

function medicationCard(page, name) {
  return page.locator(".plan-medication").filter({
    has: page.getByRole("heading", { name, exact: true }),
  });
}

function expectPlanSummary(page, medicationCount, administrationCount) {
  return Promise.all([
    expect(page.locator("#planMedicationCount")).toHaveText(
      `${medicationCount} 种药`,
    ),
    expect(page.locator("#planAdministrationCount")).toHaveText(
      `每日 ${administrationCount} 次安排`,
    ),
  ]);
}

module.exports = {
  expectPlanSummary,
  fillSchedule,
  medicationCard,
  medicationDialog,
  navigateToPlan,
  openAddMedicationDialog,
  scheduleRow,
  uniqueName,
};
