"use strict";

const DEFAULT_CONTEXT = Object.freeze({
  wake: "07:00",
  breakfast: "07:45",
  lunch: "12:15",
  dinner: "17:30",
  bedtime: "21:00",
});

const ANCHOR_LABELS = Object.freeze({
  wake: "起床",
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  bedtime: "睡前",
});

const TIMING_MODE_LABELS = Object.freeze({
  routine: "跟随作息",
  meal: "跟随用餐",
  interval: "跟随上次服用",
});

const MAX_AUTO_SHIFT_MINUTES = 120;

// All names, doses and instructions below are fictional demonstration data.
const DEMO_ITEMS = Object.freeze([
  { id: 1, medicationId: 1, name: "示例药 A", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "wake", offset: 0, timingMode: "interval" },
  { id: 2, medicationId: 2, name: "示例药 B", dose: "1份", instructions: "演示：跟随起床作息", anchor: "wake", offset: 0, timingMode: "routine" },
  { id: 3, medicationId: 3, name: "示例药 C", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "breakfast", offset: -15, timingMode: "interval" },
  { id: 4, medicationId: 4, name: "示例药 D", dose: "1份", instructions: "演示：跟随用餐", anchor: "breakfast", offset: 0, timingMode: "meal" },
  { id: 5, medicationId: 5, name: "示例药 E", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "breakfast", offset: 20, timingMode: "interval" },
  { id: 6, medicationId: 3, name: "示例药 C", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "lunch", offset: -15, timingMode: "interval" },
  { id: 7, medicationId: 1, name: "示例药 A", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "lunch", offset: 0, timingMode: "interval" },
  { id: 8, medicationId: 5, name: "示例药 E", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "lunch", offset: 20, timingMode: "interval" },
  { id: 9, medicationId: 3, name: "示例药 C", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "dinner", offset: -15, timingMode: "interval" },
  { id: 10, medicationId: 1, name: "示例药 A", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "dinner", offset: 0, timingMode: "interval" },
  { id: 11, medicationId: 4, name: "示例药 D", dose: "1份", instructions: "演示：跟随用餐", anchor: "dinner", offset: 0, timingMode: "meal" },
  { id: 12, medicationId: 5, name: "示例药 E", dose: "1份", instructions: "演示：保持相邻间隔", anchor: "dinner", offset: 20, timingMode: "interval" },
  { id: 13, medicationId: 6, name: "示例药 F", dose: "1份", instructions: "演示：跟随睡前作息", anchor: "bedtime", offset: 0, timingMode: "routine" },
]);

const DEMO_ITEMS_BY_ID = new Map(DEMO_ITEMS.map((item) => [item.id, item]));
const SAMPLE_HISTORY = Object.freeze([13, 12, 11, 13, 12, 13]);
const VIEW_ORDER = ["today", "history", "plan"];
const INITIAL_STATUS = "选择模拟签到时间，观察三种时间模式如何处理后续安排。";

const state = {
  view: "today",
  started: false,
  context: { ...DEFAULT_CONTEXT },
  taken: new Map(),
  actions: [],
  nextSequence: 1,
  adjustedMinutes: new Map(),
  adjustmentSources: new Map(),
  status: INITIAL_STATUS,
};

const elements = {
  views: Array.from(document.querySelectorAll("[data-view]")),
  tabs: Array.from(document.querySelectorAll(".nav-tab")),
  navIndicator: document.querySelector(".nav-indicator"),
  dateLabel: document.querySelector("#todayDateLabel"),
  selectedDate: document.querySelector("#selectedDateDisplay"),
  focusPanel: document.querySelector("#focusPanel"),
  currentTimeLabel: document.querySelector("#currentTimeLabel"),
  nextPanelTitle: document.querySelector("#nextPanelTitle"),
  nextPanelDetail: document.querySelector("#nextPanelDetail"),
  completedCount: document.querySelector("#completedCount"),
  totalCount: document.querySelector("#totalCount"),
  focusList: document.querySelector("#focusMedicationList"),
  startButton: document.querySelector("#startDemoButton"),
  progress: document.querySelector("#dayProgress"),
  progressBar: document.querySelector("#dayProgressBar"),
  pendingCount: document.querySelector("#pendingCount"),
  timeline: document.querySelector("#timeline"),
  contextForm: document.querySelector("#contextForm"),
  preferencesForm: document.querySelector("#preferencesForm"),
  historyCompleted: document.querySelector("#historyCompleted"),
  historyTotal: document.querySelector("#historyTotal"),
  historyPercent: document.querySelector("#historyPercent"),
  historyList: document.querySelector("#historyList"),
  planList: document.querySelector("#planList"),
  undoButton: document.querySelector("#undoDemoButton"),
  resetButton: document.querySelector("#resetDemoButton"),
  offsetSelect: document.querySelector("#demoIntakeOffset"),
  adjustmentStatus: document.querySelector("#demoAdjustmentStatus"),
  exitButton: document.querySelector("#exitDemoButton"),
  toast: document.querySelector("#toast"),
};

let toastTimer = 0;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function localDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateByOffset(offset) {
  const date = new Date();
  date.setHours(12, 0, 0, 0);
  date.setDate(date.getDate() + offset);
  return date;
}

function formatDateLabel(date) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(date);
}

function formatShortDate(date) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
  }).format(date);
}

function weekdayName(date) {
  return new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(date);
}

function baseMinutesFor(item) {
  const [hours, minutes] = state.context[item.anchor].split(":").map(Number);
  return hours * 60 + minutes + item.offset;
}

function scheduledMinutesFor(item) {
  return state.adjustedMinutes.get(item.id) ?? baseMinutesFor(item);
}

function formatMinutes(totalMinutes) {
  const normalized = ((totalMinutes % 1440) + 1440) % 1440;
  return `${String(Math.floor(normalized / 60)).padStart(2, "0")}:${String(normalized % 60).padStart(2, "0")}`;
}

function shiftDirection(minutes) {
  if (minutes < 0) return `提前 ${Math.abs(minutes)} 分钟`;
  if (minutes > 0) return `延后 ${minutes} 分钟`;
  return "保持原计划";
}

function medicationItems(medicationId) {
  return DEMO_ITEMS.filter((item) => item.medicationId === medicationId);
}

function rebuildSchedule() {
  state.adjustedMinutes = new Map(
    DEMO_ITEMS.map((item) => [item.id, baseMinutesFor(item)]),
  );
  state.adjustmentSources = new Map();
  const completed = new Set();
  const records = Array.from(state.taken.values()).sort(
    (left, right) => left.sequence - right.sequence,
  );

  for (const record of records) {
    const item = DEMO_ITEMS_BY_ID.get(record.itemId);
    if (!item) continue;
    const plannedMinutes = scheduledMinutesFor(item);
    const shiftMinutes = record.actualMinutes - plannedMinutes;
    record.plannedMinutes = plannedMinutes;
    record.shiftMinutes = shiftMinutes;
    record.affectedCount = 0;

    if (item.timingMode !== "interval") {
      record.adjustmentStatus = "not_interval";
    } else if (Math.abs(shiftMinutes) > MAX_AUTO_SHIFT_MINUTES) {
      record.adjustmentStatus = "outside_window";
    } else if (!shiftMinutes) {
      record.adjustmentStatus = "no_change";
    } else {
      const siblings = medicationItems(item.medicationId);
      const itemIndex = siblings.findIndex((candidate) => candidate.id === item.id);
      for (const candidate of siblings.slice(itemIndex + 1)) {
        if (completed.has(candidate.id)) continue;
        state.adjustedMinutes.set(
          candidate.id,
          scheduledMinutesFor(candidate) + shiftMinutes,
        );
        state.adjustmentSources.set(candidate.id, {
          actualMinutes: record.actualMinutes,
          sourceItemId: item.id,
        });
        record.affectedCount += 1;
      }
      record.adjustmentStatus = record.affectedCount ? "applied" : "no_pending";
    }
    completed.add(item.id);
  }
}

function sortedItems() {
  return DEMO_ITEMS.slice().sort((left, right) => {
    const difference = scheduledMinutesFor(left) - scheduledMinutesFor(right);
    return difference || left.id - right.id;
  });
}

function scheduleGroups() {
  const groups = new Map();
  for (const item of sortedItems()) {
    const minutes = scheduledMinutesFor(item);
    if (!groups.has(minutes)) groups.set(minutes, []);
    groups.get(minutes).push(item);
  }
  return Array.from(groups, ([minutes, items]) => ({ minutes, items }));
}

function formatScheduleMoment(item) {
  const anchor = ANCHOR_LABELS[item.anchor];
  if (!item.offset) return anchor;
  return item.offset < 0
    ? `${anchor}前 ${Math.abs(item.offset)} 分钟`
    : `${anchor}后 ${item.offset} 分钟`;
}

function adjustedScheduleLabel(item) {
  const difference = scheduledMinutesFor(item) - baseMinutesFor(item);
  const source = state.adjustmentSources.get(item.id);
  if (!difference || !source) return "";
  return `按 ${formatMinutes(source.actualMinutes)} 模拟签到推算 · 较原计划${shiftDirection(difference)}`;
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  elements.toast.classList.remove("is-leaving");
  elements.toast.classList.add("is-entering");
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("is-entering");
    elements.toast.classList.add("is-leaving");
    window.setTimeout(() => {
      elements.toast.hidden = true;
      elements.toast.classList.remove("is-leaving");
    }, 140);
  }, 2600);
}

function snapshotState() {
  return {
    started: state.started,
    context: { ...state.context },
    taken: Array.from(state.taken, ([id, record]) => [id, { ...record }]),
    nextSequence: state.nextSequence,
    status: state.status,
  };
}

function restoreSnapshot(snapshot) {
  state.started = snapshot.started;
  state.context = { ...snapshot.context };
  state.taken = new Map(
    snapshot.taken.map(([id, record]) => [id, { ...record }]),
  );
  state.nextSequence = snapshot.nextSequence;
  state.status = snapshot.status;
  rebuildSchedule();
  fillTimeForm(elements.contextForm);
  fillTimeForm(elements.preferencesForm);
}

function rememberAction(type) {
  state.actions.push({ type, snapshot: snapshotState() });
}

function updateUndoState() {
  elements.undoButton.disabled = state.actions.length === 0;
}

function renderFocus() {
  const completed = state.taken.size;
  const pending = sortedItems().filter((item) => !state.taken.has(item.id));
  elements.completedCount.textContent = String(completed);
  elements.totalCount.textContent = `/ ${DEMO_ITEMS.length} 项`;
  elements.progress.setAttribute("aria-valuenow", String(completed));
  elements.progressBar.style.setProperty(
    "--day-progress",
    String(completed / DEMO_ITEMS.length),
  );
  elements.focusPanel.classList.toggle("is-summary", state.started && !pending.length);

  if (!state.started) {
    elements.currentTimeLabel.textContent = "演示尚未开始";
    elements.nextPanelTitle.textContent = "准备开始今天的用药";
    elements.nextPanelDetail.textContent = "6 种虚构示例药，共 13 项安排";
    elements.focusList.innerHTML = "";
    elements.startButton.hidden = false;
    return;
  }

  elements.startButton.hidden = true;
  if (!pending.length) {
    elements.currentTimeLabel.textContent = "今日完成";
    elements.nextPanelTitle.textContent = "今天的演示记录已全部完成";
    elements.nextPanelDetail.textContent = "13 项虚构安排均已确认";
    elements.focusList.innerHTML = "";
    return;
  }

  const nextMinutes = scheduledMinutesFor(pending[0]);
  const nextItems = pending.filter(
    (item) => scheduledMinutesFor(item) === nextMinutes,
  );
  const adjustedCount = nextItems.filter(
    (item) => scheduledMinutesFor(item) !== baseMinutesFor(item),
  ).length;
  elements.currentTimeLabel.textContent = `下一项 · ${formatMinutes(nextMinutes)}`;
  elements.nextPanelTitle.textContent = `${ANCHOR_LABELS[nextItems[0].anchor]}用药`;
  elements.nextPanelDetail.textContent = adjustedCount
    ? `${nextItems.length} 项待确认 · ${adjustedCount} 项已动态调整`
    : `${nextItems.length} 项待确认`;
  elements.focusList.innerHTML = nextItems.map((item) => `
    <article class="focus-action-row" role="group">
      <div class="focus-medication-copy">
        <div class="focus-medication-title">
          <h3>${escapeHtml(item.name)}</h3>
          <span>${escapeHtml(item.dose)}</span>
        </div>
        <p>${escapeHtml(TIMING_MODE_LABELS[item.timingMode])} · ${escapeHtml(item.instructions)}</p>
      </div>
      <button class="focus-intake-button" type="button" data-demo-intake-id="${item.id}" aria-label="模拟确认已服用${escapeHtml(item.name)}">模拟服用</button>
    </article>`).join("");
}

function renderTimeline() {
  const pendingItems = sortedItems().filter((item) => !state.taken.has(item.id));
  const nextMinutes = pendingItems.length
    ? scheduledMinutesFor(pendingItems[0])
    : null;
  elements.pendingCount.textContent = pendingItems.length
    ? `${pendingItems.length} 项待记录`
    : "已全部记录";
  elements.timeline.innerHTML = scheduleGroups().map(({ minutes, items }) => {
    const isCurrent = state.started && minutes === nextMinutes;
    return `
      <section class="timeline-group${isCurrent ? " is-current" : ""}">
        <time class="timeline-time">${formatMinutes(minutes)}</time>
        <span class="timeline-dot" aria-hidden="true"></span>
        <div class="timeline-items">
          ${items.map((item) => {
            const record = state.taken.get(item.id);
            const taken = Boolean(record);
            const status = taken ? "taken" : isCurrent ? "due" : "upcoming";
            const statusLabel = taken ? "已模拟记录" : state.started ? "待记录" : "等待开始";
            const details = [
              formatScheduleMoment(item),
              TIMING_MODE_LABELS[item.timingMode],
              item.instructions,
              adjustedScheduleLabel(item),
              record ? `模拟签到 ${formatMinutes(record.actualMinutes)}` : "",
            ].filter(Boolean);
            return `
              <article class="medication-card is-${status}" role="group">
                <div class="medication-copy">
                  <div class="medication-title-row">
                    <h3 class="medication-title">${escapeHtml(item.name)}</h3>
                    <span class="medication-dose">${escapeHtml(item.dose)}</span>
                  </div>
                  <p class="medication-meta">
                    ${details.map((detail) => `<span>${escapeHtml(detail)}</span>`).join("")}
                    <span class="medication-status is-${status}">${statusLabel}</span>
                  </p>
                </div>
                <button class="intake-button${taken ? " is-taken" : ""}" type="button" data-demo-intake-id="${item.id}" aria-label="${taken ? "撤销模拟服用" : "模拟确认已服用"}${escapeHtml(item.name)}"${state.started ? "" : " disabled"}>${taken ? "✓" : ""}</button>
              </article>`;
          }).join("")}
        </div>
      </section>`;
  }).join("");
}

function renderHistory() {
  const counts = [...SAMPLE_HISTORY, state.taken.size];
  const completed = counts.reduce((total, count) => total + count, 0);
  const total = counts.length * DEMO_ITEMS.length;
  const percent = Math.round((completed / total) * 100);
  elements.historyCompleted.textContent = String(completed);
  elements.historyTotal.textContent = ` / ${total}`;
  elements.historyPercent.textContent = `${percent}%`;
  elements.historyList.innerHTML = counts.map((count, index) => {
    const date = dateByOffset(index - 6);
    const dayPercent = Math.round((count / DEMO_ITEMS.length) * 100);
    return `
      <div class="history-row" role="listitem">
        <div class="history-date"><span>${formatShortDate(date)}</span><small>${index === 6 ? "今天" : weekdayName(date)}</small></div>
        <div class="history-bar" aria-hidden="true"><span style="--history-progress: ${dayPercent / 100}"></span></div>
        <div class="history-value">${count} / ${DEMO_ITEMS.length}</div>
        <span class="sr-only">完成率 ${dayPercent}%</span>
      </div>`;
  }).join("");
}

function renderPlan() {
  const medications = new Map();
  for (const item of DEMO_ITEMS) {
    if (!medications.has(item.medicationId)) {
      medications.set(item.medicationId, {
        id: item.medicationId,
        name: item.name,
        timingMode: item.timingMode,
        items: [],
      });
    }
    medications.get(item.medicationId).items.push(item);
  }
  elements.planList.innerHTML = Array.from(medications.values()).map((medication) => `
    <li class="plan-medication">
      <div class="plan-medication-header">
        <div class="plan-medication-heading-copy">
          <h3>${escapeHtml(medication.name)}</h3>
          <p>${medication.items.length} 次/日 · ${escapeHtml(TIMING_MODE_LABELS[medication.timingMode])}</p>
        </div>
        <button class="secondary-button plan-manage-button" type="button" data-demo-plan-action aria-disabled="true" title="演示版使用固定虚构计划" aria-label="编辑${escapeHtml(medication.name)}的每日安排，演示版不可用">编辑安排</button>
      </div>
      <ul class="plan-schedules" aria-label="${escapeHtml(medication.name)}的每日安排">
        ${medication.items.map((item) => `
          <li class="plan-row">
            <div class="plan-row-copy">
              <p class="plan-moment">${escapeHtml(formatScheduleMoment(item))}</p>
              <p class="plan-meta">${escapeHtml(`${item.dose} · ${item.instructions}`)}</p>
            </div>
          </li>`).join("")}
      </ul>
    </li>`).join("");
}

function renderAll() {
  renderFocus();
  renderTimeline();
  renderHistory();
  renderPlan();
  elements.adjustmentStatus.textContent = state.status;
  updateUndoState();
}

function fillTimeForm(form) {
  Object.entries(state.context).forEach(([name, value]) => {
    form.elements.namedItem(name).value = value;
  });
}

function readTimeForm(form) {
  return Object.fromEntries(
    Object.keys(DEFAULT_CONTEXT).map(
      (name) => [name, form.elements.namedItem(name).value],
    ),
  );
}

function intakeStatusCopy(item, record) {
  const actual = formatMinutes(record.actualMinutes);
  const mode = TIMING_MODE_LABELS[item.timingMode];
  if (record.adjustmentStatus === "applied") {
    return `${item.name}已按 ${actual} 模拟签到；同药后续 ${record.affectedCount} 项${shiftDirection(record.shiftMinutes)}。`;
  }
  if (record.adjustmentStatus === "outside_window") {
    return `${item.name}已记录，但偏移超过 ${MAX_AUTO_SHIFT_MINUTES} 分钟；后续时间没有自动调整。`;
  }
  if (record.adjustmentStatus === "not_interval") {
    return `${item.name}已按 ${actual} 模拟签到；“${mode}”不会推动同药后续时间。`;
  }
  if (record.adjustmentStatus === "no_pending") {
    return `${item.name}已按 ${actual} 模拟签到；该药今天没有待调整的后续项目。`;
  }
  return `${item.name}已按计划时间模拟签到，后续时间保持不变。`;
}

function recordIntake(itemId) {
  const item = DEMO_ITEMS_BY_ID.get(itemId);
  if (!item) return;
  rememberAction("intake");

  if (state.taken.has(itemId)) {
    state.taken.delete(itemId);
    rebuildSchedule();
    state.status = `已撤销${item.name}的模拟签到，并重新计算同药后续时间。`;
    renderAll();
    showToast("已撤销模拟签到");
    return;
  }

  const plannedMinutes = scheduledMinutesFor(item);
  const offsetMinutes = Number(elements.offsetSelect.value);
  state.taken.set(itemId, {
    itemId,
    sequence: state.nextSequence,
    actualMinutes: plannedMinutes + offsetMinutes,
  });
  state.nextSequence += 1;
  rebuildSchedule();
  const record = state.taken.get(itemId);
  state.status = intakeStatusCopy(item, record);
  renderAll();
  showToast(state.status);
}

function switchView(view) {
  if (!VIEW_ORDER.includes(view) || view === state.view) return;
  state.view = view;
  elements.views.forEach((panel) => {
    const active = panel.dataset.view === view;
    panel.hidden = !active;
    panel.classList.toggle("is-active", active);
  });
  elements.tabs.forEach((tab) => {
    const active = tab.dataset.viewTarget === view;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  });
  updateNavIndicator();
}

function updateNavIndicator() {
  const activeTab = elements.tabs.find(
    (tab) => tab.dataset.viewTarget === state.view,
  );
  if (!activeTab) return;
  const indicatorWidth = elements.navIndicator.getBoundingClientRect().width || 32;
  const x = activeTab.offsetLeft + (activeTab.offsetWidth - indicatorWidth) / 2;
  document
    .querySelector(".nav-tabs")
    .style.setProperty("--nav-indicator-x", `${x}px`);
}

function resetDemo() {
  state.started = false;
  state.context = { ...DEFAULT_CONTEXT };
  state.taken = new Map();
  state.actions = [];
  state.nextSequence = 1;
  state.status = INITIAL_STATUS;
  elements.offsetSelect.value = "30";
  rebuildSchedule();
  fillTimeForm(elements.contextForm);
  fillTimeForm(elements.preferencesForm);
  switchView("today");
  renderAll();
  showToast("演示已重置");
}

function undoLastAction() {
  const action = state.actions.pop();
  if (!action) return;
  restoreSnapshot(action.snapshot);
  renderAll();
  showToast("已撤销上一步");
}

function saveTimes(form, message) {
  if (!form.reportValidity()) return;
  rememberAction("context");
  state.context = readTimeForm(form);
  rebuildSchedule();
  fillTimeForm(elements.contextForm);
  fillTimeForm(elements.preferencesForm);
  state.status = "演示作息已更新；已记录项目保持模拟签到时间，后续计划已重新计算。";
  renderAll();
  showToast(message);
}

document.addEventListener("click", (event) => {
  const viewTarget = event.target.closest("[data-view-target]");
  if (viewTarget) switchView(viewTarget.dataset.viewTarget);

  const intakeButton = event.target.closest("[data-demo-intake-id]");
  if (intakeButton && state.started) {
    recordIntake(Number(intakeButton.dataset.demoIntakeId));
  }

  if (event.target.closest("[data-demo-plan-action]")) {
    showToast("演示版使用固定虚构计划，不支持修改");
  }
});

elements.startButton.addEventListener("click", () => {
  if (state.started) return;
  rememberAction("start");
  state.started = true;
  state.status = "演示已开始。默认模拟延后 30 分钟签到，可随时切换偏移。";
  renderAll();
  showToast("演示已开始");
});

elements.offsetSelect.addEventListener("change", () => {
  const label = elements.offsetSelect.selectedOptions[0]?.textContent || "按计划时间";
  state.status = `下一次确认服用将使用“${label}”。`;
  renderAll();
});

elements.undoButton.addEventListener("click", undoLastAction);
elements.resetButton.addEventListener("click", resetDemo);
document.querySelector("#saveContextButton").addEventListener("click", () => {
  saveTimes(elements.contextForm, "今日时间已更新");
});
document.querySelector("#savePreferencesButton").addEventListener("click", () => {
  saveTimes(elements.preferencesForm, "默认时间已更新");
});
document.querySelector("#addMedicationButton").addEventListener("click", () => {
  showToast("演示版使用固定虚构计划，不支持修改");
});
document.querySelector("#previousDayButton").addEventListener("click", () => {
  showToast("演示版仅展示今天");
});
document.querySelector("#nextDayButton").addEventListener("click", () => {
  showToast("演示版仅展示今天");
});

elements.tabs.forEach((tab, index) => {
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    let targetIndex = index;
    if (event.key === "ArrowLeft") {
      targetIndex = (index - 1 + elements.tabs.length) % elements.tabs.length;
    }
    if (event.key === "ArrowRight") {
      targetIndex = (index + 1) % elements.tabs.length;
    }
    if (event.key === "Home") targetIndex = 0;
    if (event.key === "End") targetIndex = elements.tabs.length - 1;
    const target = elements.tabs[targetIndex];
    switchView(target.dataset.viewTarget);
    target.focus();
  });
});

document.querySelectorAll("details").forEach((details) => {
  details.addEventListener("toggle", () => {
    details.classList.toggle("is-expanded", details.open);
  });
});

elements.exitButton.addEventListener("click", async () => {
  const exitUrl = document.body.dataset.demoExitUrl;
  if (document.body.dataset.staticDemo === "true" && exitUrl) {
    window.location.assign(exitUrl);
    return;
  }
  try {
    const response = await fetch("/api/demo-access", {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error("exit failed");
    window.location.replace("/demo");
  } catch (_error) {
    showToast("暂时无法退出，请稍后重试");
  }
});

if (document.body.dataset.staticDemo === "true") {
  elements.exitButton.textContent = "查看源码";
  elements.exitButton.setAttribute("aria-label", "前往 GitHub 查看 TakeTime 源码");
}

const today = new Date();
elements.dateLabel.textContent = formatDateLabel(today);
elements.selectedDate.dateTime = localDateKey(today);
rebuildSchedule();
fillTimeForm(elements.contextForm);
fillTimeForm(elements.preferencesForm);
renderAll();
window.addEventListener("resize", updateNavIndicator);
window.requestAnimationFrame(updateNavIndicator);
