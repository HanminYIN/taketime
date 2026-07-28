"use strict";

const APP_TIME_ZONE = "Asia/Shanghai";
const initialTodayKey = localDateKey(new Date());

const state = {
  view: "today",
  selectedDate: initialTodayKey,
  todayKey: initialTodayKey,
  day: null,
  history: null,
  medications: [],
  scheduleItems: [],
  scheduleSummary: {
    medicationCount: 0,
    dailyAdministrationCount: 0,
  },
  scheduleItemsLoaded: false,
  preferences: null,
  preferencesSaveBusy: false,
  preferencesFormDirty: false,
  preferencesFormRevision: 0,
  planLoading: false,
  planLoadToken: 0,
  renderedDate: null,
  contextFormDirty: false,
  contextFormRevision: 0,
  dayLoadToken: 0,
  viewLoadToken: 0,
  viewAbortController: null,
  pendingDateNavigation: null,
  intakeSurfaceSignature: "",
  intakeStatuses: new Map(),
  dayMutation: null,
  intakeToken: 0,
  intakeActions: new Map(),
  pendingScheduleSave: null,
  medicationEditorInitialSignature: "",
  medicationEditorBusy: false,
  medicationEditorRecovery: null,
};

const anchorLabels = {
  wake: "起床",
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  bedtime: "睡前",
};

const timingModeLabels = {
  routine: "跟随作息",
  meal: "跟随用餐",
  interval: "跟随上次服药",
};

const viewOrder = ["today", "history", "plan"];

const contextFieldOrder = [
  { anchor: "wake", field: "wakeTime", label: "起床" },
  { anchor: "breakfast", field: "breakfastTime", label: "早餐" },
  { anchor: "lunch", field: "lunchTime", label: "午餐" },
  { anchor: "dinner", field: "dinnerTime", label: "晚餐" },
  { anchor: "bedtime", field: "bedtimeTime", label: "睡前" },
];

const scheduleAnchorOrder = new Map(
  contextFieldOrder.map(({ anchor }, index) => [anchor, index]),
);

const elements = {
  brandButton: document.querySelector(".brand-button"),
  navTabs: document.querySelector(".nav-tabs"),
  navIndicator: document.querySelector(".nav-indicator"),
  lockAccessButton: document.querySelector("#lockAccessButton"),
  syncState: document.querySelector("#syncState"),
  syncStateLabel: document.querySelector("#syncStateLabel"),
  todayView: document.querySelector("#todayView"),
  dateHeadingCopy: document.querySelector(".date-heading-copy"),
  dayContent: document.querySelector("#dayContent"),
  todayDateLabel: document.querySelector("#todayDateLabel"),
  todayTitle: document.querySelector("#todayTitle"),
  selectedDateDisplay: document.querySelector("#selectedDateDisplay"),
  dateNavigationAnnouncement: document.querySelector("#dateNavigationAnnouncement"),
  focusPanel: document.querySelector("#focusPanel"),
  focusStatusAnnouncement: document.querySelector("#focusStatusAnnouncement"),
  focusMedicationList: document.querySelector("#focusMedicationList"),
  intakeFeedbackList: document.querySelector("#intakeFeedbackList"),
  wakeButton: document.querySelector("#wakeButton"),
  wakeConfirmation: document.querySelector("#wakeConfirmation"),
  wakeRecordedLabel: document.querySelector("#wakeRecordedLabel"),
  adjustScheduleButton: document.querySelector("#adjustScheduleButton"),
  currentTimeLabel: document.querySelector("#currentTimeLabel"),
  nextPanelTitle: document.querySelector("#nextPanelTitle"),
  nextPanelDetail: document.querySelector("#nextPanelDetail"),
  completedCount: document.querySelector("#completedCount"),
  totalCount: document.querySelector("#totalCount"),
  summaryLabel: document.querySelector("#summaryLabel"),
  dayProgress: document.querySelector("#dayProgress"),
  dayProgressBar: document.querySelector("#dayProgressBar"),
  pendingCount: document.querySelector("#pendingCount"),
  timeline: document.querySelector("#timeline"),
  contextForm: document.querySelector("#contextForm"),
  contextDetails: document.querySelector("#contextDetails"),
  contextTitle: document.querySelector("#contextTitle"),
  contextSourceLabel: document.querySelector("#contextSourceLabel"),
  contextInferenceNote: document.querySelector("#contextInferenceNote"),
  contextCrossDayWarning: document.querySelector("#contextCrossDayWarning"),
  saveContextButton: document.querySelector("#saveContextButton"),
  previousDayButton: document.querySelector("#previousDayButton"),
  nextDayButton: document.querySelector("#nextDayButton"),
  returnTodayButton: document.querySelector("#returnTodayButton"),
  timelineDetails: document.querySelector("#timelineDetails"),
  timelineTitle: document.querySelector("#timelineTitle"),
  historyCompleted: document.querySelector("#historyCompleted"),
  historyTotal: document.querySelector("#historyTotal"),
  historyPercent: document.querySelector("#historyPercent"),
  historyRateLabel: document.querySelector("#historyRateLabel"),
  historyList: document.querySelector("#historyList"),
  planView: document.querySelector("#planView"),
  preferencesForm: document.querySelector("#preferencesForm"),
  preferencesCrossDayWarning: document.querySelector("#preferencesCrossDayWarning"),
  savePreferencesButton: document.querySelector("#savePreferencesButton"),
  planList: document.querySelector("#planList"),
  planCount: document.querySelector("#planCount"),
  planMedicationCount: document.querySelector("#planMedicationCount"),
  planAdministrationCount: document.querySelector("#planAdministrationCount"),
  addMedicationButton: document.querySelector("#addMedicationButton"),
  medicationDialog: document.querySelector("#medicationDialog"),
  medicationDialogTitle: document.querySelector("#medicationDialogTitle"),
  medicationDialogError: document.querySelector("#medicationDialogError"),
  medicationDialogErrorMessage: document.querySelector("#medicationDialogErrorMessage"),
  reloadMedicationButton: document.querySelector("#reloadMedicationButton"),
  medicationForm: document.querySelector("#medicationForm"),
  timingModeInputs: Array.from(document.querySelectorAll('[name="timingMode"]')),
  timingModeAdvanced: document.querySelector("#timingModeAdvanced"),
  maxAutoShiftMinutesInput: document.querySelector('[name="maxAutoShiftMinutes"]'),
  scheduleEditorList: document.querySelector("#scheduleEditorList"),
  scheduleEditorFrequency: document.querySelector("#scheduleEditorFrequency"),
  addScheduleButton: document.querySelector("#addScheduleButton"),
  archiveMedicationButton: document.querySelector("#archiveMedicationButton"),
  closeMedicationDialog: document.querySelector("#closeMedicationDialog"),
  cancelMedicationButton: document.querySelector("#cancelMedicationButton"),
  crossDayDialog: document.querySelector("#crossDayDialog"),
  crossDayForm: document.querySelector("#crossDayForm"),
  crossDayDialogDescription: document.querySelector("#crossDayDialogDescription"),
  crossDayReason: document.querySelector("#crossDayReason"),
  crossDayImpactList: document.querySelector("#crossDayImpactList"),
  crossDayPreservedNote: document.querySelector("#crossDayPreservedNote"),
  crossDayDialogError: document.querySelector("#crossDayDialogError"),
  cancelCrossDayButton: document.querySelector("#cancelCrossDayButton"),
  confirmCrossDayButton: document.querySelector("#confirmCrossDayButton"),
  toast: document.querySelector("#toast"),
  errorBanner: document.querySelector("#errorBanner"),
  errorMessage: document.querySelector("#errorMessage"),
  retryButton: document.querySelector("#retryButton"),
};

function localDateKey(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: APP_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const { year, month, day } = values;
  return `${year}-${month}-${day}`;
}

function parseDateKey(key) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function shiftDate(key, days) {
  const date = parseDateKey(key);
  date.setUTCDate(date.getUTCDate() + days);
  return localDateKey(date);
}

function dayDifference(fromKey, toKey) {
  const [fromYear, fromMonth, fromDay] = fromKey.split("-").map(Number);
  const [toYear, toMonth, toDay] = toKey.split("-").map(Number);
  return Math.round(
    (Date.UTC(toYear, toMonth - 1, toDay) -
      Date.UTC(fromYear, fromMonth - 1, fromDay)) /
      86_400_000,
  );
}

function formatLongDate(key) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(parseDateKey(key));
}

function formatShortDate(key) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    month: "numeric",
    day: "numeric",
  }).format(parseDateKey(key));
}

function formatMonthDay(key) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    month: "long",
    day: "numeric",
  }).format(parseDateKey(key));
}

function formatCalendarDate(key) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(parseDateKey(key));
}

function weekdayName(key) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    weekday: "short",
  }).format(parseDateKey(key));
}

function scheduledDate(item) {
  const fallback = `${state.selectedDate}T${item.scheduledTime}:00+08:00`;
  const value = new Date(item.scheduledAt || fallback);
  return Number.isNaN(value.getTime()) ? new Date(fallback) : value;
}

function scheduledKey(item) {
  return item.scheduledAt || `${state.selectedDate}T${item.scheduledTime}:00`;
}

function formatScheduledTime(item) {
  const scheduleDate = item.scheduledAt?.slice(0, 10) || state.selectedDate;
  const offset = dayDifference(state.selectedDate, scheduleDate);
  if (offset === 1) return `次日 ${item.scheduledTime}`;
  if (offset > 1) return `${offset}日后 ${item.scheduledTime}`;
  if (offset === -1) return `前日 ${item.scheduledTime}`;
  if (offset < -1) return `${Math.abs(offset)}日前 ${item.scheduledTime}`;
  return item.scheduledTime;
}

function minutesUntil(item) {
  return Math.round((scheduledDate(item).getTime() - Date.now()) / 60_000);
}

function currentTimeText() {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date());
}

function formatTakenTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "已记录";
  const time = new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return `${time} 已记录`;
}

function formatClockTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: APP_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

function scheduleAdjustmentDirection(minutes) {
  if (minutes > 0) return `顺延 ${minutes} 分钟`;
  if (minutes < 0) return `提前 ${Math.abs(minutes)} 分钟`;
  return "时间未改变";
}

function adjustedScheduleLabel(item) {
  if (!item?.adjusted || !item.adjustmentMinutes) return "";
  const sourceTime = formatClockTime(item.adjustedByTakenAt);
  if (item.timingMode === "interval" && sourceTime) {
    return `按 ${sourceTime} 服药时间推算 · 较原计划${scheduleAdjustmentDirection(item.adjustmentMinutes)}`;
  }
  return `已调整 · 较原计划${scheduleAdjustmentDirection(item.adjustmentMinutes)}`;
}

function intakeAdjustmentCopy(adjustment, recordedAt) {
  if (!adjustment) return null;
  const recorded = formatTakenTime(recordedAt);
  if (adjustment.status === "applied") {
    const direction = scheduleAdjustmentDirection(adjustment.shiftMinutes);
    return {
      title: null,
      detail: `${recorded} · 后续 ${adjustment.affectedCount} 项已按原定间隔${direction}`,
      toast: `后续 ${adjustment.affectedCount} 项已按原定间隔${direction}`,
    };
  }
  if (adjustment.status === "outside_window") {
    const requested = adjustment.requestedShiftMinutes;
    const difference = requested >= 0
      ? `晚 ${requested} 分钟`
      : `早 ${Math.abs(requested)} 分钟`;
    return {
      title: "已记录，后续时间未自动调整",
      detail: `${recorded} · 比当时计划${difference}，超过 ${adjustment.maximumShiftMinutes} 分钟的自动范围。`,
      toast: "已记录，后续时间未自动调整",
    };
  }
  return null;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const reduceMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
const motionClassRuns = new WeakMap();
const detailsMotionRuns = new WeakMap();
let activePageViewTransition = null;
let activeFallbackPageTransition = null;
let activeDateTransition = null;
let dateNavigationSequence = 0;
let dateAnnouncementToken = 0;

function playMotionClass(element, className, duration = 360) {
  if (!element) return;
  let runs = motionClassRuns.get(element);
  if (!runs) {
    runs = new Map();
    motionClassRuns.set(element, runs);
  }
  const previous = runs.get(className);
  if (previous) {
    window.cancelAnimationFrame(previous.frameId);
    window.clearTimeout(previous.timerId);
  }
  element.classList.remove(className);
  if (reduceMotionQuery.matches) {
    runs.delete(className);
    return;
  }
  const run = { frameId: 0, timerId: 0 };
  run.frameId = window.requestAnimationFrame(() => {
    element.classList.add(className);
    run.timerId = window.setTimeout(() => {
      element.classList.remove(className);
      if (runs.get(className) === run) runs.delete(className);
    }, duration);
  });
  runs.set(className, run);
}

function finishFallbackPageTransition(run, { skipEnter = false } = {}) {
  if (!run || activeFallbackPageTransition !== run) return;
  window.clearTimeout(run.timerId);
  run.shell?.removeEventListener("animationend", run.finish);
  run.section.classList.remove(
    "is-view-leaving",
    "is-view-forward",
    "is-view-backward",
  );
  run.section.removeAttribute("inert");
  activeFallbackPageTransition = null;
  run.update();
  if (!skipEnter) run.fallback?.();
}

function runFallbackPageTransition(direction, update, fallback) {
  if (activeFallbackPageTransition) {
    finishFallbackPageTransition(activeFallbackPageTransition, {
      skipEnter: true,
    });
  }
  const section = document.querySelector(".app-view.is-active");
  const shell = section?.querySelector(".page-shell");
  if (!section || !shell) {
    update();
    fallback?.();
    return;
  }

  section.classList.remove("is-view-forward", "is-view-backward");
  section.classList.add(
    "is-view-leaving",
    direction < 0 ? "is-view-backward" : "is-view-forward",
  );
  section.setAttribute("inert", "");
  const run = {
    section,
    shell,
    update,
    fallback,
    finish: null,
    timerId: 0,
  };
  run.finish = () => finishFallbackPageTransition(run);
  activeFallbackPageTransition = run;
  shell.addEventListener("animationend", run.finish, { once: true });
  run.timerId = window.setTimeout(run.finish, 180);
}

function runPageViewTransition(direction, update, fallback) {
  if (reduceMotionQuery.matches) {
    update();
    fallback?.();
    return;
  }
  if (typeof document.startViewTransition !== "function") {
    runFallbackPageTransition(direction, update, fallback);
    return;
  }

  activePageViewTransition?.skipTransition();
  const root = document.documentElement;
  root.dataset.viewTransitionDirection = direction < 0 ? "backward" : "forward";

  try {
    const transition = document.startViewTransition(update);
    activePageViewTransition = transition;
    transition.finished
      .catch(() => {})
      .finally(() => {
        if (activePageViewTransition !== transition) return;
        activePageViewTransition = null;
        delete root.dataset.viewTransitionDirection;
      });
  } catch (_error) {
    delete root.dataset.viewTransitionDirection;
    runFallbackPageTransition(direction, update, fallback);
  }
}

reduceMotionQuery.addEventListener?.("change", (event) => {
  if (!event.matches) return;
  activePageViewTransition?.skipTransition();
  fastForwardDateTransition();
  if (activeFallbackPageTransition) {
    finishFallbackPageTransition(activeFallbackPageTransition, {
      skipEnter: true,
    });
  }
});

function setDetailsOpen(details, open, { animate = true } = {}) {
  if (!details) return;
  const previous = detailsMotionRuns.get(details);
  if (previous) window.clearTimeout(previous.timerId);
  detailsMotionRuns.delete(details);

  const shouldAnimate = animate && !reduceMotionQuery.matches;
  if (open) {
    details.open = true;
    details.classList.remove("is-closing", "is-expanded");
    if (shouldAnimate) void details.offsetHeight;
    details.classList.add("is-expanded");
    return;
  }

  if (!details.open) {
    details.classList.remove("is-expanded", "is-closing");
    return;
  }
  if (!shouldAnimate) {
    details.open = false;
    details.classList.remove("is-expanded", "is-closing");
    return;
  }

  details.classList.remove("is-expanded");
  details.classList.add("is-closing");
  const run = {
    timerId: window.setTimeout(() => {
      if (detailsMotionRuns.get(details) !== run) return;
      details.open = false;
      details.classList.remove("is-closing");
      detailsMotionRuns.delete(details);
    }, 170),
  };
  detailsMotionRuns.set(details, run);
}

function bindAnimatedDetails(details) {
  const summary = details?.querySelector(":scope > summary");
  if (!summary) return;
  setDetailsOpen(details, details.open, { animate: false });
  summary.addEventListener("click", (event) => {
    event.preventDefault();
    const opening = !details.open || details.classList.contains("is-closing");
    setDetailsOpen(details, opening);
  });
}

function setSyncState(label, syncing = false, tone = "normal") {
  const changed =
    elements.syncStateLabel.textContent !== label ||
    elements.syncState.classList.contains("is-syncing") !== syncing;
  elements.syncStateLabel.textContent = label;
  elements.syncState.classList.toggle("is-syncing", syncing);
  elements.syncState.classList.toggle("is-error", tone === "error");
  elements.syncState.classList.toggle("is-saved", tone === "saved");
  if (changed) playMotionClass(elements.syncState, "is-changing", 220);
}

const API_TIMEOUT_MS = 15_000;
let activeApiRequests = 0;
let apiBatchHadError = false;
let apiBatchHadWrite = false;

function beginApiRequest(method) {
  if (activeApiRequests === 0) {
    apiBatchHadError = false;
    apiBatchHadWrite = false;
  }
  activeApiRequests += 1;
  apiBatchHadWrite ||= method !== "GET";
  setSyncState("同步中", true);
}

function finishApiRequest({ failed = false, aborted = false } = {}) {
  if (failed && !aborted) apiBatchHadError = true;
  activeApiRequests = Math.max(0, activeApiRequests - 1);
  if (activeApiRequests > 0) return;
  if (apiBatchHadError) {
    setSyncState("未连接", false, "error");
  } else {
    setSyncState(apiBatchHadWrite ? "已保存" : "已同步", false, apiBatchHadWrite ? "saved" : "normal");
  }
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const {
    signal: callerSignal,
    timeoutMs = API_TIMEOUT_MS,
    ...requestOptions
  } = options;
  const controller = new AbortController();
  let timedOut = false;
  let failed = false;
  let aborted = false;
  const forwardAbort = () => controller.abort(callerSignal?.reason);
  if (callerSignal?.aborted) {
    forwardAbort();
  } else {
    callerSignal?.addEventListener("abort", forwardAbort, { once: true });
  }
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  beginApiRequest(method);
  try {
    const response = await fetch(path, {
      ...requestOptions,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(requestOptions.headers || {}),
      },
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : null;
    if (
      response.status === 401 &&
      response.headers.get("X-TakeTime-Access") === "required"
    ) {
      window.location.replace("/");
      throw new ApiError("访问已锁定", response.status);
    }
    if (!response.ok) {
      throw new ApiError(
        payload?.error || `请求失败（${response.status}）`,
        response.status,
      );
    }
    return payload;
  } catch (error) {
    failed = true;
    aborted = isAbortError(error) && !timedOut;
    if (timedOut) throw new ApiError("请求超时", null);
    if (error instanceof TypeError) {
      throw new ApiError("网络连接中断", null);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    callerSignal?.removeEventListener("abort", forwardAbort);
    finishApiRequest({ failed, aborted });
  }
}

function showError(error) {
  window.clearTimeout(errorExitTimer);
  const token = ++errorToken;
  console.error(error);
  elements.errorMessage.textContent = error?.message || "无法连接服务";
  elements.errorBanner.classList.remove("is-leaving");
  elements.errorBanner.hidden = false;
  playMotionClass(elements.errorBanner, "is-entering", 220);
  setSyncState("未连接", false, "error");
  return token;
}

let errorExitTimer;
let errorToken = 0;

function focusActiveViewHeading() {
  const heading = document.querySelector('.app-view:not([hidden]) h1');
  if (!heading) return;
  heading.tabIndex = -1;
  heading.focus({ preventScroll: true });
  heading.addEventListener("blur", () => heading.removeAttribute("tabindex"), {
    once: true,
  });
}

function clearError() {
  if (elements.errorBanner.hidden) return;
  window.clearTimeout(errorExitTimer);
  const token = ++errorToken;
  const restoreFocus = elements.errorBanner.contains(document.activeElement);
  const finish = () => {
    if (token !== errorToken) return;
    elements.errorBanner.hidden = true;
    elements.errorBanner.classList.remove("is-entering", "is-leaving");
    if (restoreFocus) focusActiveViewHeading();
  };
  if (reduceMotionQuery.matches) {
    finish();
    return;
  }
  elements.errorBanner.classList.remove("is-entering");
  elements.errorBanner.classList.add("is-leaving");
  errorExitTimer = window.setTimeout(finish, 140);
}

function hasReadyDay() {
  return Boolean(state.day && state.day.date === state.selectedDate);
}

function setDateNavigationPending(pending) {
  elements.todayView.classList.toggle("is-date-loading", pending);
  if (pending) elements.dayContent.setAttribute("aria-busy", "true");
  else elements.dayContent.removeAttribute("aria-busy");
  syncDayMutationControls();
  elements.dayContent
    .querySelectorAll("button, input, select, textarea")
    .forEach((control) => {
      if (pending) {
        if (control.dataset.dateNavigationWasDisabled === undefined) {
          control.dataset.dateNavigationWasDisabled = String(control.disabled);
        }
        control.disabled = true;
        return;
      }
      if (control.dataset.dateNavigationWasDisabled === undefined) return;
      control.disabled = control.dataset.dateNavigationWasDisabled === "true";
      delete control.dataset.dateNavigationWasDisabled;
    });
}

function cancelPendingDateNavigation({ abort = true } = {}) {
  if (!state.pendingDateNavigation) return;
  state.dayLoadToken += 1;
  if (abort) state.viewAbortController?.abort();
  state.pendingDateNavigation = null;
  setDateNavigationPending(false);
}

function syncDayMutationControls() {
  const busy = Boolean(state.dayMutation);
  const dayReady = hasReadyDay();
  elements.brandButton.disabled = busy;
  elements.previousDayButton.disabled = busy;
  elements.nextDayButton.disabled = busy;
  elements.returnTodayButton.disabled = busy;
  elements.navTabs.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.disabled = busy;
  });
  elements.wakeButton.disabled = busy || !dayReady;
  elements.saveContextButton.disabled = busy || !dayReady;
  document
    .querySelectorAll(
      "[data-intake-id], [data-focus-intake-id], [data-intake-retry-id], [data-intake-undo-id]",
    )
    .forEach((control) => {
      control.disabled = busy || control.getAttribute("aria-busy") === "true";
    });
  if (state.pendingScheduleSave?.kind === "context") {
    elements.confirmCrossDayButton.disabled =
      busy || Boolean(state.pendingScheduleSave.saving);
  }
}

function acquireDayMutation(kind, date) {
  if (state.dayMutation || state.pendingDateNavigation) return null;
  const mutation = { token: Symbol(kind), kind, date };
  state.dayMutation = mutation;
  syncDayMutationControls();
  return mutation;
}

function releaseDayMutation(mutation) {
  if (state.dayMutation?.token !== mutation?.token) return;
  state.dayMutation = null;
  syncDayMutationControls();
}

function setPreferencesSaveBusy(busy) {
  state.preferencesSaveBusy = busy;
  syncPlanControls();
}

function syncPlanControls() {
  const formBusy = state.planLoading || state.preferencesSaveBusy;
  elements.savePreferencesButton.disabled = formBusy;
  for (const control of elements.preferencesForm.elements) {
    control.disabled = formBusy;
  }
  elements.addMedicationButton.disabled = state.planLoading;
  elements.planList.toggleAttribute("inert", state.planLoading);
  for (const region of [elements.planList, elements.planView]) {
    if (state.planLoading) region.setAttribute("aria-busy", "true");
    else region.removeAttribute("aria-busy");
  }
  elements.planList.querySelectorAll("button").forEach((button) => {
    button.disabled = state.planLoading;
  });
}

function setPlanLoading(busy) {
  state.planLoading = busy;
  syncPlanControls();
}

let toastTimer;
let toastExitTimer;
let toastToken = 0;

function hideToast(token) {
  if (token !== toastToken || elements.toast.hidden) return;
  window.clearTimeout(toastExitTimer);
  if (reduceMotionQuery.matches) {
    elements.toast.hidden = true;
    return;
  }
  elements.toast.classList.remove("is-entering");
  elements.toast.classList.add("is-leaving");
  toastExitTimer = window.setTimeout(() => {
    if (token !== toastToken) return;
    elements.toast.hidden = true;
    elements.toast.classList.remove("is-leaving");
  }, 140);
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  window.clearTimeout(toastExitTimer);
  const token = ++toastToken;
  elements.toast.textContent = message;
  elements.toast.classList.remove("is-leaving");
  elements.toast.hidden = false;
  playMotionClass(elements.toast, "is-entering", 220);
  toastTimer = window.setTimeout(() => hideToast(token), 2600);
}

function updateNavIndicator({ instant = false } = {}) {
  const activeTab = elements.navTabs.querySelector(".nav-tab.is-active");
  if (!activeTab || !elements.navIndicator) return;
  if (instant) elements.navIndicator.classList.add("is-instant");
  const x =
    activeTab.offsetLeft +
    Math.max(0, (activeTab.offsetWidth - elements.navIndicator.offsetWidth) / 2);
  elements.navTabs.style.setProperty("--nav-indicator-x", `${x}px`);
  if (instant) {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        elements.navIndicator.classList.remove("is-instant");
      });
    });
  }
}

function playViewTransition(view, direction) {
  const section = document.querySelector(`.app-view[data-view="${view}"]`);
  if (!section) return;
  section.classList.remove("is-view-forward", "is-view-backward");
  section.classList.add(
    direction < 0 ? "is-view-backward" : "is-view-forward",
  );
  playMotionClass(section, "is-view-entering", 300);
}

function finishDateTransition(run = activeDateTransition) {
  if (!run) return;
  run.cancelled = true;
  for (const animation of run.animations) animation.cancel();
  run.animations = [];
  if (activeDateTransition !== run) return;
  activeDateTransition = null;
  elements.todayView.classList.remove("is-date-transitioning");
  elements.dayContent.removeAttribute("inert");
}

function cancelDateTransition() {
  finishDateTransition(activeDateTransition);
}

function fastForwardDateTransition(run = activeDateTransition) {
  if (!run) return;
  for (const animation of run.animations) {
    try {
      animation.finish();
    } catch (_error) {
      // Every date animation has a finite duration; cancellation remains the fallback.
      animation.cancel();
    }
  }
}

function visibleDateTransitionNode(element) {
  if (!element?.isConnected || element.hidden) return false;
  const rect = element.getBoundingClientRect();
  const computed = window.getComputedStyle(element);
  return Boolean(
    rect.width > 0 &&
      rect.height > 0 &&
      computed.display !== "none" &&
      computed.visibility !== "hidden" &&
      Number(computed.opacity) > 0,
  );
}

function dateTransitionQueue() {
  const groups = [
    {
      delay: 0,
      nodes: [
        elements.dateHeadingCopy,
        elements.selectedDateDisplay,
        elements.returnTodayButton,
      ],
    },
    {
      delay: 28,
      nodes: [
        elements.focusPanel.querySelector(".focus-heading"),
        elements.focusMedicationList,
        elements.intakeFeedbackList,
        elements.wakeButton,
        elements.wakeConfirmation,
      ],
    },
    {
      delay: 58,
      nodes: [
        elements.contextDetails.querySelector(":scope > summary > div"),
        elements.contextDetails.querySelector(".details-content-inner"),
      ],
    },
    {
      delay: 82,
      nodes: [
        elements.timelineDetails.querySelector(":scope > summary > div"),
        elements.pendingCount,
        elements.timelineDetails.querySelector(".timeline-content-inner"),
      ],
    },
  ];

  return groups.flatMap((group) =>
    group.nodes
      .filter(visibleDateTransitionNode)
      .map((element, index) => ({
        element,
        delay: Math.min(group.delay + index * 14, 96),
      })),
  );
}

function startDateAnimations(run, entries, keyframes, options) {
  const { stagger = false, ...animationOptions } = options;
  run.animations = entries.map(({ element, delay }) =>
    element.animate(keyframes, {
      fill: "both",
      ...animationOptions,
      delay: stagger ? delay : 0,
    }),
  );
}

async function waitForDateAnimations(run) {
  const animations = [...run.animations];
  const results = await Promise.all(
    animations.map((animation) =>
      animation.finished.then(
        () => true,
        () => false,
      ),
    ),
  );
  return (
    activeDateTransition === run &&
    !run.cancelled &&
    results.every(Boolean)
  );
}

async function playDateTransition({
  direction,
  animate = true,
  commit,
  isCurrent,
}) {
  if (
    !animate ||
    reduceMotionQuery.matches ||
    typeof elements.dayContent.animate !== "function"
  ) {
    if (!isCurrent()) return false;
    commit();
    return true;
  }

  cancelDateTransition();
  const run = {
    animations: [],
    cancelled: false,
    committed: false,
    phase: "leaving",
  };
  activeDateTransition = run;
  elements.todayView.classList.add("is-date-transitioning");
  elements.dayContent.setAttribute("inert", "");

  try {
    startDateAnimations(
      run,
      dateTransitionQueue(),
      [
        { opacity: 1, transform: "translate3d(0, 0, 0)" },
        {
          opacity: 0,
          transform: `translate3d(${-direction * 5}px, 0, 0)`,
        },
      ],
      {
        duration: 110,
        easing: "cubic-bezier(0.4, 0, 1, 1)",
      },
    );
    if (run.animations.length && !(await waitForDateAnimations(run))) {
      if (activeDateTransition === run) finishDateTransition(run);
      return false;
    }
    if (activeDateTransition !== run) return false;
    if (!isCurrent()) {
      finishDateTransition(run);
      return false;
    }

    commit();
    run.committed = true;
    for (const animation of run.animations) animation.cancel();
    run.animations = [];

    if (reduceMotionQuery.matches) {
      finishDateTransition(run);
      return true;
    }

    run.phase = "entering";
    startDateAnimations(
      run,
      dateTransitionQueue(),
      [
        {
          opacity: 0,
          transform: `translate3d(${direction * 7}px, 0, 0)`,
        },
        { opacity: 1, transform: "translate3d(0, 0, 0)" },
      ],
      {
        duration: 220,
        easing: "cubic-bezier(0.16, 1, 0.3, 1)",
        stagger: true,
      },
    );
    if (run.animations.length) await waitForDateAnimations(run);
    if (activeDateTransition === run) finishDateTransition(run);
    return run.committed;
  } catch (error) {
    finishDateTransition(run);
    throw error;
  }
}

function playIntakeTransition(action) {
  if (!action || state.selectedDate !== action.displayDate) return;
  const forward = action.operation === "record";
  playMotionClass(
    elements.focusPanel,
    forward ? "is-intake-forward" : "is-intake-reverse",
    420,
  );

  const timelineRow = Array.from(
    elements.timeline.querySelectorAll("[data-intake-row-id]"),
  ).find(
    (row) =>
      Number(row.dataset.intakeRowId) === action.itemId &&
      row.dataset.intakeRoutineDate === action.date,
  );
  playMotionClass(
    timelineRow,
    forward ? "is-state-confirmed" : "is-state-restored",
    420,
  );

  const identity = intakeIdentity(action.date, action.itemId);
  const feedback = Array.from(
    elements.intakeFeedbackList.querySelectorAll("[data-intake-feedback-id]"),
  ).find((row) => row.dataset.intakeFeedbackId === identity);
  playMotionClass(feedback, "is-motion-entering", 300);
}

function fillTimeForm(form, values) {
  for (const [field, value] of Object.entries(values)) {
    const input = form.elements.namedItem(field);
    if (input) input.value = value;
  }
}

function readTimeForm(form) {
  const formData = new FormData(form);
  return {
    wakeTime: formData.get("wakeTime"),
    breakfastTime: formData.get("breakfastTime"),
    lunchTime: formData.get("lunchTime"),
    dinnerTime: formData.get("dinnerTime"),
    bedtimeTime: formData.get("bedtimeTime"),
  };
}

function timeToMinutes(value) {
  const [hours, minutes] = String(value).split(":").map(Number);
  return hours * 60 + minutes;
}

function formatMinutesAsTime(value) {
  const normalized = ((value % 1440) + 1440) % 1440;
  return `${String(Math.floor(normalized / 60)).padStart(2, "0")}:${String(normalized % 60).padStart(2, "0")}`;
}

function dayOffsetLabel(offset, zeroLabel = "今日") {
  if (offset === 0) return zeroLabel;
  if (offset === 1) return "次日";
  if (offset > 1) return `${offset}日后`;
  if (offset === -1) return "前日";
  return `${Math.abs(offset)}日前`;
}

function deriveAnchorMoments(baseDate, context) {
  let dayOffset = 0;
  let previousMinutes = null;
  return contextFieldOrder.map((entry) => {
    const minutes = timeToMinutes(context[entry.field]);
    if (previousMinutes !== null && minutes < previousMinutes) dayOffset += 1;
    previousMinutes = minutes;
    return {
      ...entry,
      time: context[entry.field],
      minutes,
      dayOffset,
      dateKey: shiftDate(baseDate, dayOffset),
      absoluteMinutes: dayOffset * 1440 + minutes,
    };
  });
}

function deriveMedicationMoments(baseDate, context, items) {
  const anchors = new Map(
    deriveAnchorMoments(baseDate, context).map((moment) => [moment.anchor, moment]),
  );
  return items
    .filter((item) => anchors.has(item.anchor))
    .map((item) => {
      const anchor = anchors.get(item.anchor);
      const absoluteMinutes = anchor.absoluteMinutes + Number(item.offsetMinutes || 0);
      const dayOffset = Math.floor(absoluteMinutes / 1440);
      return {
        ...item,
        anchorDayOffset: anchor.dayOffset,
        absoluteMinutes,
        dayOffset,
        dateKey: shiftDate(baseDate, dayOffset),
        time: formatMinutesAsTime(absoluteMinutes),
      };
    })
    .sort((left, right) => left.absoluteMinutes - right.absoluteMinutes);
}

function schedulePreview(baseDate, context, items) {
  const anchors = deriveAnchorMoments(baseDate, context);
  const medications = deriveMedicationMoments(baseDate, context, items);
  const firstWrapIndex = anchors.findIndex(
    (moment, index) => index > 0 && moment.dayOffset > anchors[index - 1].dayOffset,
  );
  return {
    baseDate,
    context,
    anchors,
    medications,
    firstWrapIndex,
    crossesDay:
      anchors.some((moment) => moment.dayOffset !== 0) ||
      medications.some((item) => item.dayOffset !== 0),
  };
}

function schedulePreviewReason(preview) {
  if (preview.firstWrapIndex > 0) {
    const current = preview.anchors[preview.firstWrapIndex];
    const previous = preview.anchors[preview.firstWrapIndex - 1];
    return `${current.label} ${current.time} 早于${previous.label} ${previous.time}，因此按${dayOffsetLabel(current.dayOffset)}计算。`;
  }
  return "有用药的相对时间落在计划日之外，因此需要确认实际日期。";
}

function contextsEqual(left, right) {
  return Boolean(
    left &&
      right &&
      contextFieldOrder.every(({ field }) => left[field] === right[field]),
  );
}

function preferenceSpanError(preview) {
  const wake = preview.anchors[0];
  const bedtime = preview.anchors[preview.anchors.length - 1];
  const span = bedtime.absoluteMinutes - wake.absoluteMinutes;
  if (span <= 0 || span > 1440) {
    return "常用作息需在起床后 24 小时内结束，请检查各时段的先后顺序。";
  }
  return "";
}

function renderTimeFormPreview(
  form,
  warningElement,
  baseDate,
  items,
  zeroLabel,
  serverOffsets = null,
) {
  const context = readTimeForm(form);
  if (
    contextFieldOrder.some(
      ({ field }) => !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(String(context[field] || "")),
    )
  ) {
    setCrossDayWarning(warningElement, { visible: false });
    return null;
  }
  const preview = schedulePreview(baseDate, context, items);
  for (const moment of preview.anchors) {
    const badge = form.querySelector(`[data-day-offset-field="${moment.field}"]`);
    if (!badge) continue;
    const offset = serverOffsets?.[moment.field] ?? moment.dayOffset;
    const label = dayOffsetLabel(offset, zeroLabel);
    const isCrossDay = offset !== 0;
    const changed =
      badge.textContent !== label ||
      badge.classList.contains("is-cross-day") !== isCrossDay;
    badge.textContent = label;
    badge.classList.toggle("is-cross-day", isCrossDay);
    if (changed) playMotionClass(badge, "is-changing", 240);
  }

  const outsideCount = preview.medications.filter((item) => item.dayOffset !== 0).length;
  if (preview.crossesDay) {
    const countText = outsideCount
      ? `${outsideCount} 项用药会安排在计划日之外。`
      : "当前没有用药落在计划日之外。";
    setCrossDayWarning(warningElement, {
      visible: true,
      text: `${schedulePreviewReason(preview)}${countText}保存前会再次确认。`,
    });
  } else {
    setCrossDayWarning(warningElement, { visible: false });
  }
  return preview;
}

const crossDayWarningTokens = new WeakMap();

function setCrossDayWarning(
  warningElement,
  { visible, text = "", error = false },
) {
  const notice = warningElement.closest(".cross-day-notice");
  const wasVisible = notice?.classList.contains("is-visible");
  const contentChanged = visible && warningElement.textContent !== text;
  const token = (crossDayWarningTokens.get(warningElement) || 0) + 1;
  crossDayWarningTokens.set(warningElement, token);
  warningElement.classList.toggle("is-error", error);
  notice?.classList.toggle("is-visible", visible);
  notice?.setAttribute("aria-hidden", String(!visible));
  if (!visible) return;
  if (!contentChanged && wasVisible) return;
  warningElement.textContent = "";
  window.requestAnimationFrame(() => {
    if (
      crossDayWarningTokens.get(warningElement) !== token ||
      !notice?.classList.contains("is-visible")
    ) {
      return;
    }
    warningElement.textContent = text;
    playMotionClass(warningElement, "is-changing", 240);
  });
}

function renderContextTimePreview(serverOffsets = null) {
  if (!hasReadyDay()) return null;
  const zeroLabel =
    state.selectedDate === localDateKey(new Date()) ? "今日" : "当日";
  return renderTimeFormPreview(
    elements.contextForm,
    elements.contextCrossDayWarning,
    state.selectedDate,
    state.day.items.filter((item) => !item.taken),
    zeroLabel,
    serverOffsets,
  );
}

function renderPreferencesTimePreview() {
  const preview = renderTimeFormPreview(
    elements.preferencesForm,
    elements.preferencesCrossDayWarning,
    shiftDate(localDateKey(new Date()), 1),
    state.scheduleItems,
    "当日",
  );
  const bedtimeInput = elements.preferencesForm.elements.namedItem("bedtimeTime");
  const error = preview ? preferenceSpanError(preview) : "";
  bedtimeInput.setCustomValidity(error);
  if (error) {
    setCrossDayWarning(elements.preferencesCrossDayWarning, {
      visible: true,
      text: error,
      error: true,
    });
  }
  return preview;
}

function statusFor(item) {
  if (item.taken) return "taken";
  const difference = minutesUntil(item);
  if (difference < -45) return "overdue";
  if (difference <= 30) return "due";
  return "upcoming";
}

function statusLabel(item) {
  const status = statusFor(item);
  if (status === "taken") return formatTakenTime(item.takenAt);
  if (status === "overdue") return "原计划时间已过";
  if (status === "due") return "即将服用";
  return "待服用";
}

function itemRoutineDate(item, fallback = state.selectedDate) {
  return item?.routineDate || fallback;
}

function intakeIdentity(date, itemId) {
  return `${date}-${itemId}`;
}

function findDayItem(itemId, routineDate) {
  if (!state.day) return null;
  const candidates = [
    ...state.day.items,
    ...(state.day.carryoverItems || []),
  ];
  return (
    candidates.find(
      (item) =>
        item.id === itemId &&
        itemRoutineDate(item, state.day.date) === routineDate,
    ) || null
  );
}

function intakeActionKey(date, itemId) {
  return `${date}:${itemId}`;
}

function intakeActionFor(itemId, date = state.selectedDate) {
  return state.intakeActions.get(intakeActionKey(date, itemId)) || null;
}

function intakeActionLabel(action) {
  if (!action) return "";
  const verb = action.operation === "record" ? "记录" : "撤销";
  if (action.phase === "pending") return `${verb}中`;
  if (action.phase === "error") return action.errorMessage;
  return action.operation === "record" ? "已记录" : "已撤销";
}

function intakeButtonPresentation(item) {
  const routineDate = itemRoutineDate(item);
  const action = intakeActionFor(item.id, routineDate);
  const pending = action?.phase === "pending";
  const disabled = pending || Boolean(state.dayMutation);
  let content = item.taken ? "✓" : "";
  if (pending) content = '<span class="button-spinner" aria-hidden="true"></span>';
  return {
    action,
    pending,
    disabled,
    content,
    ariaLabel: pending
      ? `${action.operation === "record" ? "正在记录" : "正在撤销"}${item.name}`
      : `${item.taken ? "撤销" : "记录"}${item.name}`,
  };
}

function renderInlineIntakeError(action, surface) {
  if (action?.phase !== "error") return "";
  const identity = intakeIdentity(action.date, action.itemId);
  return `
    <div class="intake-inline-feedback is-error">
      <span>${escapeHtml(action.errorMessage)}</span>
      <button type="button" data-intake-retry-id="${action.itemId}" data-intake-routine-date="${action.date}" data-intake-focus-key="${surface}-retry-${identity}" ${state.dayMutation ? "disabled" : ""}>重试</button>
    </div>`;
}

function captureIntakeFocus() {
  return document.activeElement
    ?.closest?.("[data-intake-focus-key]")
    ?.getAttribute("data-intake-focus-key") || null;
}

function restoreIntakeFocus(focusKey) {
  if (!focusKey) return;
  const target = document.querySelector(`[data-intake-focus-key="${focusKey}"]`);
  if (target && !target.disabled) target.focus({ preventScroll: true });
}

function focusIntakeAfterRender(action) {
  if (!action.manageFocus || state.selectedDate !== action.displayDate) return;
  const focusPhase = `${action.attempt}:${action.phase}`;
  if (action.focusPhase === focusPhase) return;
  action.focusPhase = focusPhase;
  const id = action.itemId;
  const identity = intakeIdentity(action.date, id);
  const surface = action.focusSurface;
  let focusKeys;
  if (action.phase === "pending") {
    focusKeys = [
      surface === "feedback"
        ? `feedback-row-${identity}`
        : `${surface}-row-${identity}`,
      `focus-row-${identity}`,
      `timeline-row-${identity}`,
      `feedback-row-${identity}`,
    ];
  } else if (action.phase === "error") {
    focusKeys = [
      `${surface}-retry-${identity}`,
      `feedback-retry-${identity}`,
      `focus-retry-${identity}`,
      `timeline-retry-${identity}`,
    ];
  } else if (action.operation === "record") {
    focusKeys =
      surface === "timeline"
        ? [
            `timeline-action-${identity}`,
            `timeline-row-${identity}`,
            `feedback-undo-${identity}`,
          ]
        : [`feedback-undo-${identity}`, `focus-row-${identity}`];
  } else {
    focusKeys = [
      `${surface}-action-${identity}`,
      `focus-action-${identity}`,
      `timeline-action-${identity}`,
    ];
  }
  const expectedAttempt = action.attempt;
  const expectedPhase = action.phase;
  window.requestAnimationFrame(() => {
    const current = intakeActionFor(id, action.date);
    if (
      !current ||
      current.token !== action.token ||
      current.attempt !== expectedAttempt ||
      current.phase !== expectedPhase
    ) {
      return;
    }
    for (const focusKey of focusKeys) {
      const target = document.querySelector(
        `[data-intake-focus-key="${focusKey}"]`,
      );
      if (!target || target.disabled) continue;
      if (elements.timelineDetails.contains(target) && !elements.timelineDetails.open) {
        setDetailsOpen(elements.timelineDetails, true);
      }
      target.focus({ preventScroll: true });
      const rect = target.getBoundingClientRect();
      if (rect.top < 52 || rect.bottom > window.innerHeight) {
        target.scrollIntoView({ block: "nearest", behavior: "auto" });
      }
      break;
    }
  });
}

function renderIntakeFeedback() {
  const actions = Array.from(state.intakeActions.values()).filter(
    (action) =>
      action.displayDate === state.selectedDate &&
      (action.phase === "success" ||
        action.phase === "error" ||
        action.operation === "undo" ||
        (action.phase === "pending" && action.date !== action.displayDate)),
  );
  elements.intakeFeedbackList.hidden = !actions.length;
  elements.intakeFeedbackList.innerHTML = actions
    .map((action) => {
      const identity = intakeIdentity(action.date, action.itemId);
      const item =
        findDayItem(action.itemId, action.date) ||
        action.itemSnapshot;
      const pending = action.phase === "pending";
      const error = action.phase === "error";
      const recordedAt = item?.takenAt || action.takenAt;
      const adjustmentCopy =
        action.operation === "record" && action.phase === "success"
          ? intakeAdjustmentCopy(action.scheduleAdjustment, recordedAt)
          : null;
      const title = pending
        ? `正在${action.operation === "record" ? "记录" : "撤销记录"}`
        : error
          ? `未能确认是否${action.operation === "record" ? "记录" : "撤销"}`
          : action.operation === "record"
            ? adjustmentCopy?.title
              ? `${item.name}：${adjustmentCopy.title}`
              : `${item.name}已记录`
            : `${item.name}已撤销`;
      const detail = pending
        ? `${item.name} · 请稍候`
        : error
          ? action.errorMessage
          : action.operation === "record"
            ? adjustmentCopy?.detail || formatTakenTime(recordedAt)
            : "该项已恢复为待记录";
      const titleId = `feedback-title-${identity}`;
      const detailId = `feedback-detail-${identity}`;
      const control = error
        ? `<button class="glass-link" type="button" data-intake-retry-id="${action.itemId}" data-intake-routine-date="${action.date}" data-intake-focus-key="feedback-retry-${identity}" ${state.dayMutation ? "disabled" : ""}>重试</button>`
        : action.phase === "success" && action.operation === "record"
          ? `<button class="glass-link" type="button" data-intake-undo-id="${action.itemId}" data-intake-routine-date="${action.date}" data-intake-focus-key="feedback-undo-${identity}" ${state.dayMutation ? "disabled" : ""}>撤销</button>`
          : "";
      return `
        <div class="focus-intake-feedback is-${action.phase}" role="group" aria-labelledby="${titleId}" aria-describedby="${detailId}" ${pending ? 'aria-busy="true"' : ""} data-intake-feedback-id="${identity}" data-intake-focus-key="feedback-row-${identity}" tabindex="-1">
          <div>
            <strong id="${titleId}">${escapeHtml(title)}</strong>
            <span id="${detailId}">${escapeHtml(detail)}</span>
          </div>
          ${pending ? '<span class="button-spinner" aria-hidden="true"></span>' : control}
        </div>`;
    })
    .join("");
}

function relativeScheduleText(item) {
  const difference = minutesUntil(item);
  if (difference <= 1) return "即将开始";
  if (difference < 60) return `约 ${difference} 分钟后`;
  const hours = Math.floor(difference / 60);
  const minutes = difference % 60;
  return minutes ? `约 ${hours} 小时 ${minutes} 分钟后` : `约 ${hours} 小时后`;
}

function renderFocusItems(items, intent) {
  elements.focusMedicationList.hidden = !items.length;
  elements.focusMedicationList.innerHTML = items
    .map((item) => {
      const button = intakeButtonPresentation(item);
      const routineDate = itemRoutineDate(item);
      const identity = intakeIdentity(routineDate, item.id);
      const origin =
        routineDate === state.selectedDate
          ? ""
          : `来自 ${formatMonthDay(routineDate)}计划`;
      const meta = [
        origin,
        item.instructions,
        adjustedScheduleLabel(item),
        item.anchorEstimated ? "预计时间" : "",
        button.pending ? intakeActionLabel(button.action) : "",
      ].filter(Boolean);
      const nameId = `focus-medication-name-${identity}`;
      const doseId = `focus-medication-dose-${identity}`;
      const metaId = `focus-medication-meta-${identity}`;
      return `
        <div class="focus-action-row ${intent === "overdue" ? "is-overdue" : ""} ${routineDate !== state.selectedDate ? "is-carryover" : ""} ${button.pending ? "is-pending" : ""} ${button.action?.phase === "error" ? "is-error" : ""}" role="group" aria-labelledby="${nameId} ${doseId}" aria-describedby="${metaId}" ${button.pending ? 'aria-busy="true"' : ""} data-intake-row-id="${item.id}" data-intake-routine-date="${routineDate}" data-intake-status-key="${identity}" data-intake-surface="focus" data-intake-focus-key="focus-row-${identity}" tabindex="-1">
          <div class="focus-medication-copy">
            <div class="focus-medication-title">
              <h3 id="${nameId}">${escapeHtml(item.name)}</h3>
              <span id="${doseId}">${escapeHtml(item.dose)}</span>
            </div>
            <p id="${metaId}">${meta.map((value) => escapeHtml(value)).join(" · ")}</p>
            ${renderInlineIntakeError(button.action, "focus")}
          </div>
          <button
            class="focus-intake-button"
            type="button"
            data-focus-intake-id="${item.id}"
            data-intake-routine-date="${routineDate}"
            data-intake-focus-key="focus-action-${identity}"
            aria-label="${escapeHtml(button.ariaLabel)} ${escapeHtml(item.dose)}${origin ? `，${escapeHtml(origin)}` : ""}"
            ${button.pending ? 'aria-busy="true"' : ""}
            ${button.disabled ? "disabled" : ""}
          >${button.pending ? intakeActionLabel(button.action) : "记录"}</button>
        </div>`;
    })
    .join("");
}

function renderFocusPanel({ suppressMotion = false } = {}) {
  if (!state.day) return;
  const { items, summary } = state.day;
  const today = localDateKey(new Date());
  const isToday = state.selectedDate === today;
  const carryoverItems = isToday ? state.day.carryoverItems || [] : [];
  const hasWakeEvent = Boolean(state.day.wakeEvent);
  const completedChanged =
    elements.completedCount.textContent !== String(summary.completed);
  elements.completedCount.textContent = String(summary.completed);
  if (completedChanged && !suppressMotion) {
    playMotionClass(elements.completedCount, "is-changing", 300);
  }
  elements.totalCount.textContent = `/ ${summary.total} 项`;
  elements.dayProgressBar.style.setProperty(
    "--day-progress",
    String(Math.max(0, Math.min(100, summary.percent)) / 100),
  );
  elements.dayProgress.setAttribute("aria-valuemax", String(Math.max(summary.total, 1)));
  elements.dayProgress.setAttribute("aria-valuenow", String(summary.completed));
  elements.dayProgress.setAttribute(
    "aria-valuetext",
    `${summary.completed} / ${summary.total} 项`,
  );
  elements.pendingCount.textContent = state.day.untracked
    ? "未建立记录"
    : `${summary.total - summary.completed} 项待记录`;
  elements.focusPanel.classList.remove(
    "is-wake",
    "is-action",
    "is-summary",
    "is-complete",
    "is-carryover",
    "is-intake-forward",
    "is-intake-reverse",
    "is-wake-handoff",
    "is-time-handoff",
  );
  elements.focusMedicationList.innerHTML = "";
  elements.focusMedicationList.hidden = true;
  renderIntakeFeedback();

  if (isToday && !hasWakeEvent && !carryoverItems.length) {
    elements.focusPanel.classList.add("is-wake");
    elements.currentTimeLabel.textContent = `现在 · ${currentTimeText()}`;
    elements.nextPanelTitle.textContent = "起床后，一键开始";
    elements.nextPanelDetail.textContent =
      "记录真实起床时间，今日提醒会按常用作息自动推算";
    elements.wakeButton.hidden = false;
    elements.wakeConfirmation.hidden = true;
    return;
  }

  elements.wakeButton.hidden = !isToday || hasWakeEvent;
  elements.wakeConfirmation.hidden = !(isToday && hasWakeEvent);
  if (isToday && hasWakeEvent) {
    const scheduleState =
      state.day.contextSource === "wake_inferred"
        ? "餐次时间为预计"
        : "今日安排已调整";
    elements.wakeRecordedLabel.textContent =
      `${state.day.wakeEvent.localTime} 已记录起床 · ${scheduleState}`;
  }

  if (!isToday) {
    elements.focusPanel.classList.add("is-summary");
    elements.currentTimeLabel.textContent = formatLongDate(state.selectedDate);
    if (state.day.untracked) {
      elements.nextPanelTitle.textContent = "当天没有记录";
      elements.nextPanelDetail.textContent = "未建立用药计划";
      return;
    }
    if (state.day.preview) {
      elements.nextPanelTitle.textContent = `${summary.total} 项用药计划`;
      elements.nextPanelDetail.textContent = "计划预览";
      return;
    }
    elements.nextPanelTitle.textContent =
      summary.completed === summary.total && summary.total > 0
        ? "当天已全部记录"
        : `当天已记录 ${summary.completed} 项`;
    elements.nextPanelDetail.textContent = `共 ${summary.total} 项用药计划`;
    return;
  }

  elements.focusPanel.classList.add("is-action");
  elements.currentTimeLabel.textContent = `现在 · ${currentTimeText()}`;
  const ownPending = hasWakeEvent ? items.filter((item) => !item.taken) : [];
  const pending = [...carryoverItems, ...ownPending].sort(
    (left, right) => scheduledDate(left) - scheduledDate(right),
  );
  if (!pending.length) {
    elements.focusPanel.classList.add("is-complete");
    elements.nextPanelTitle.textContent = "今天已全部记录";
    elements.nextPanelDetail.textContent = "今日计划已完成";
    return;
  }

  const overdue = pending.filter((item) => statusFor(item) === "overdue");
  const due = pending.filter((item) => statusFor(item) === "due");
  let target;
  let intent;
  const wakePending = isToday && !hasWakeEvent;
  if (overdue.length) {
    target = overdue[0];
    intent = "overdue";
    elements.nextPanelTitle.textContent = wakePending
      ? `有 ${overdue.length} 项跨日用药待确认`
      : `有 ${overdue.length} 项记录待确认`;
    elements.nextPanelDetail.textContent = `${formatScheduledTime(target)} 原计划 · 请按医嘱确认是否服用`;
  } else if (due.length) {
    target = due[0];
    intent = "due";
    elements.nextPanelTitle.textContent = wakePending
      ? "现在先确认跨日用药"
      : "现在需要确认";
    elements.nextPanelDetail.textContent =
      `${formatScheduledTime(target)} 计划 · 服用后请记录`;
  } else {
    target = pending[0];
    intent = "upcoming";
    elements.nextPanelTitle.textContent = wakePending
      ? "下一项是跨日用药"
      : "下一次用药";
    elements.nextPanelDetail.textContent =
      `${formatScheduledTime(target)} · ${relativeScheduleText(target)}`;
  }
  const targetRoutineDate = itemRoutineDate(target);
  if (targetRoutineDate !== state.selectedDate) {
    elements.focusPanel.classList.add("is-carryover");
    elements.nextPanelDetail.textContent =
      `来自 ${formatMonthDay(targetRoutineDate)}计划 · ${elements.nextPanelDetail.textContent}`;
  }
  const targetItems = pending.filter(
    (item) => scheduledKey(item) === scheduledKey(target),
  );
  renderFocusItems(targetItems, intent);
}

function renderTimeline() {
  if (!state.day) return;
  const groups = new Map();
  for (const item of state.day.items) {
    const key = scheduledKey(item);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  if (!groups.size) {
    elements.timeline.innerHTML = `<div class="empty-state">${state.day.untracked ? "当天没有用药记录" : "当天没有用药计划"}</div>`;
    return;
  }

  elements.timeline.innerHTML = Array.from(groups.entries())
    .map(([scheduledAt, items]) => {
      const hasCurrent = items.some((item) => statusFor(item) === "due");
      const timeLabel = formatScheduledTime(items[0]);
      const cards = items
        .map((item) => {
          const status = statusFor(item);
          const button = intakeButtonPresentation(item);
          const routineDate = itemRoutineDate(item);
          const identity = intakeIdentity(routineDate, item.id);
          const displayStatus = button.pending
            ? intakeActionLabel(button.action)
            : statusLabel(item);
          const meta = [
            item.instructions,
            adjustedScheduleLabel(item),
            displayStatus,
          ].filter(Boolean);
          const nameId = `timeline-medication-name-${identity}`;
          const doseId = `timeline-medication-dose-${identity}`;
          const metaId = `timeline-medication-meta-${identity}`;
          return `
            <article class="medication-card is-${status} ${button.pending ? "is-intake-pending" : ""} ${button.action?.phase === "error" ? "is-intake-error" : ""}" role="group" aria-labelledby="${nameId} ${doseId}" aria-describedby="${metaId}" ${button.pending ? 'aria-busy="true"' : ""} data-intake-row-id="${item.id}" data-intake-routine-date="${routineDate}" data-intake-status-key="${identity}" data-intake-surface="timeline" data-intake-focus-key="timeline-row-${identity}" tabindex="-1">
              <div class="medication-copy">
                <div class="medication-title-row">
                  <h3 class="medication-title" id="${nameId}">${escapeHtml(item.name)}</h3>
                  <span class="medication-dose" id="${doseId}">${escapeHtml(item.dose)}</span>
                </div>
                <p class="medication-meta" id="${metaId}">
                  ${meta
                    .map(
                      (value, index) =>
                        `<span class="${index === meta.length - 1 ? `medication-status is-${status}` : ""}">${escapeHtml(value)}</span>`,
                    )
                    .join("<span aria-hidden=\"true\">·</span>")}
                </p>
                ${renderInlineIntakeError(button.action, "timeline")}
              </div>
              <button
                class="intake-button ${item.taken ? "is-taken" : ""} ${button.pending ? "is-pending" : ""}"
                type="button"
                data-intake-id="${item.id}"
                data-intake-routine-date="${routineDate}"
                data-intake-focus-key="timeline-action-${identity}"
                aria-label="${escapeHtml(button.ariaLabel)}"
                title="${item.taken ? "撤销记录" : "标记已服用"}"
                ${button.pending ? 'aria-busy="true"' : ""}
                ${button.disabled ? "disabled" : ""}
              >${button.content}</button>
            </article>`;
        })
        .join("");
      return `
        <div class="timeline-group ${hasCurrent ? "is-current" : ""}">
          <time class="timeline-time" datetime="${escapeHtml(scheduledAt)}">${escapeHtml(timeLabel)}</time>
          <span class="timeline-dot" aria-hidden="true"></span>
          <div class="timeline-items">${cards}</div>
        </div>`;
    })
    .join("");
}

function intakeSurfaceStateSignature() {
  if (!hasReadyDay()) return "";
  const items = [...state.day.items, ...(state.day.carryoverItems || [])]
    .map((item) => [
      itemRoutineDate(item, state.day.date),
      item.id,
      item.taken,
      item.takenAt,
      item.scheduledAt,
      statusFor(item),
    ])
    .sort((left, right) => String(left).localeCompare(String(right)));
  const actions = Array.from(state.intakeActions.values())
    .filter((action) => action.displayDate === state.selectedDate)
    .map((action) => [
      action.date,
      action.itemId,
      action.operation,
      action.phase,
      action.attempt,
    ])
    .sort((left, right) => String(left).localeCompare(String(right)));
  return JSON.stringify({
    date: state.selectedDate,
    wake: state.day.wakeEvent?.recordedAt || null,
    summary: state.day.summary,
    items,
    actions,
  });
}

function refreshLiveIntakeLabels() {
  if (!hasReadyDay() || state.selectedDate !== localDateKey(new Date())) return;
  elements.currentTimeLabel.textContent = `现在 · ${currentTimeText()}`;
  if (!elements.focusPanel.classList.contains("is-action")) return;

  const hasWakeEvent = Boolean(state.day.wakeEvent);
  const ownPending = hasWakeEvent
    ? state.day.items.filter((item) => !item.taken)
    : [];
  const pending = [
    ...(state.day.carryoverItems || []),
    ...ownPending,
  ].sort((left, right) => scheduledDate(left) - scheduledDate(right));
  if (!pending.length) return;
  if (pending.some((item) => statusFor(item) === "overdue")) return;
  if (pending.some((item) => statusFor(item) === "due")) return;

  const target = pending[0];
  const origin =
    itemRoutineDate(target) === state.selectedDate
      ? ""
      : `来自 ${formatMonthDay(itemRoutineDate(target))}计划 · `;
  elements.nextPanelDetail.textContent =
    `${origin}${formatScheduledTime(target)} · ${relativeScheduleText(target)}`;
}

function intakeStatusSnapshot() {
  if (!hasReadyDay()) return new Map();
  return new Map(
    [...state.day.items, ...(state.day.carryoverItems || [])].map((item) => [
      intakeIdentity(itemRoutineDate(item, state.day.date), item.id),
      statusFor(item),
    ]),
  );
}

function announceFocusStatus() {
  const medications = Array.from(
    elements.focusMedicationList.querySelectorAll(".focus-medication-title"),
  )
    .map((row) =>
      [row.querySelector("h3")?.textContent, row.querySelector("span")?.textContent]
        .filter(Boolean)
        .join("，"),
    )
    .filter(Boolean)
    .join("；");
  const message = [
    elements.nextPanelTitle.textContent,
    elements.nextPanelDetail.textContent,
    medications,
  ]
    .filter(Boolean)
    .join("。");
  elements.focusStatusAnnouncement.textContent = "";
  window.requestAnimationFrame(() => {
    elements.focusStatusAnnouncement.textContent = message;
  });
}

function renderIntakeSurfaces({
  timeDriven = false,
  suppressMotion = false,
} = {}) {
  const focusKey = captureIntakeFocus();
  const previousFocusMessage = `${elements.nextPanelTitle.textContent}|${elements.nextPanelDetail.textContent}`;
  const previousStatuses = state.intakeStatuses;
  renderFocusPanel({ suppressMotion });
  renderTimeline();
  syncDayMutationControls();
  restoreIntakeFocus(focusKey);
  const nextStatuses = intakeStatusSnapshot();
  if (timeDriven && previousStatuses.size) {
    const changedKeys = new Set(
      Array.from(nextStatuses).flatMap(([key, status]) =>
        previousStatuses.has(key) && previousStatuses.get(key) !== status
          ? [key]
          : [],
      ),
    );
    if (changedKeys.size) {
      const nextFocusMessage = `${elements.nextPanelTitle.textContent}|${elements.nextPanelDetail.textContent}`;
      if (nextFocusMessage !== previousFocusMessage) {
        playMotionClass(elements.focusPanel, "is-time-handoff", 340);
        announceFocusStatus();
      }
      document.querySelectorAll("[data-intake-status-key]").forEach((row) => {
        if (changedKeys.has(row.dataset.intakeStatusKey)) {
          playMotionClass(row, "is-time-state-change", 320);
        }
      });
    }
  }
  state.intakeStatuses = nextStatuses;
  state.intakeSurfaceSignature = intakeSurfaceStateSignature();
}

function renderSelectedDateHeading() {
  const isToday = state.selectedDate === state.todayKey;
  elements.todayDateLabel.textContent = formatLongDate(state.selectedDate);
  elements.todayTitle.textContent = isToday
    ? "今天的用药"
    : `${formatMonthDay(state.selectedDate)}的用药`;
  elements.selectedDateDisplay.textContent = isToday
    ? "今天"
    : formatMonthDay(state.selectedDate);
  elements.selectedDateDisplay.dateTime = state.selectedDate;
  elements.returnTodayButton.classList.toggle("is-placeholder", isToday);
  elements.returnTodayButton.tabIndex = isToday ? -1 : 0;
  if (isToday) elements.returnTodayButton.setAttribute("aria-hidden", "true");
  else elements.returnTodayButton.removeAttribute("aria-hidden");
  elements.contextTitle.textContent = isToday ? "调整今日安排" : "调整当日安排";
  elements.timelineTitle.textContent = isToday ? "每日总结" : "当日总结";
  elements.summaryLabel.textContent = isToday ? "今日完成" : "当日完成";
}

function announceSelectedDate() {
  const token = ++dateAnnouncementToken;
  const label =
    state.selectedDate === state.todayKey
      ? "今天"
      : formatLongDate(state.selectedDate);
  elements.dateNavigationAnnouncement.textContent = "";
  window.requestAnimationFrame(() => {
    if (token !== dateAnnouncementToken) return;
    elements.dateNavigationAnnouncement.textContent = `已显示${label}的用药安排`;
  });
}

function renderDayLoading() {
  renderSelectedDateHeading();
  elements.focusPanel.classList.remove(
    "is-wake",
    "is-action",
    "is-summary",
    "is-complete",
    "is-carryover",
  );
  elements.focusPanel.classList.add("is-loading");
  elements.focusPanel.setAttribute("aria-busy", "true");
  elements.currentTimeLabel.textContent = "正在同步";
  elements.nextPanelTitle.textContent = "正在读取当天安排";
  elements.nextPanelDetail.textContent = "同步用药计划与已有记录";
  elements.completedCount.textContent = "—";
  elements.totalCount.textContent = "/ — 项";
  elements.pendingCount.textContent = "正在读取";
  elements.focusMedicationList.innerHTML = "";
  elements.focusMedicationList.hidden = true;
  elements.intakeFeedbackList.innerHTML = "";
  elements.intakeFeedbackList.hidden = true;
  elements.wakeButton.hidden = true;
  elements.wakeConfirmation.hidden = true;
  elements.dayProgressBar.style.setProperty("--day-progress", "0");
  elements.dayProgress.setAttribute("aria-valuenow", "0");
  elements.dayProgress.setAttribute("aria-valuetext", "正在读取当天进度");
  elements.timeline.innerHTML =
    '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  setDetailsOpen(elements.contextDetails, false, { animate: false });
  state.intakeSurfaceSignature = "";
  state.intakeStatuses = new Map();
  syncDayMutationControls();
}

function renderToday({ suppressMotion = false } = {}) {
  if (!hasReadyDay()) return;
  const today = localDateKey(new Date());
  const isToday = state.selectedDate === today;
  renderSelectedDateHeading();
  elements.focusPanel.classList.remove("is-loading");
  elements.focusPanel.removeAttribute("aria-busy");
  const savingThisContext =
    state.dayMutation?.kind === "context" &&
    state.dayMutation.date === state.selectedDate;
  elements.saveContextButton.textContent = savingThisContext
    ? "正在保存"
    : !state.day.persisted
      ? "建立当日计划"
      : "保存时间";
  if (!state.contextFormDirty) {
    fillTimeForm(elements.contextForm, state.day.context);
    renderContextTimePreview(state.day.contextDayOffsets);
  } else {
    renderContextTimePreview();
  }
  const sourcePresentation = {
    wake_inferred: {
      label: "根据起床时间推算",
      note: "餐次与睡前时间按常用作息间隔推算，只调整提醒时间，不改变用药内容。",
    },
    manual: {
      label: "已手动调整",
      note: "这些时间只用于安排提醒，不会改变药名、剂量或服用要求。",
    },
    intake_default: {
      label: "已采用常用作息",
      note: "这些时间来自常用作息，可根据今天的实际安排修改。",
    },
    legacy: {
      label: "历史安排",
      note: "这是原有记录中的时间安排，可按当天实际情况查看或调整。",
    },
    default: {
      label: "常用作息预览",
      note: "尚未建立当天记录；这些时间来自常用作息。",
    },
  }[state.day.contextSource] || {
    label: "今日安排",
    note: "这些时间只用于安排提醒，不会改变用药内容。",
  };
  elements.contextSourceLabel.textContent = sourcePresentation.label;
  elements.contextInferenceNote.textContent = sourcePresentation.note;

  if (state.renderedDate !== state.selectedDate) {
    setDetailsOpen(elements.contextDetails, false, { animate: false });
    setDetailsOpen(elements.timelineDetails, !isToday, { animate: false });
    state.renderedDate = state.selectedDate;
  }

  renderIntakeSurfaces({ suppressMotion });
}

async function loadDay({
  signal = state.viewAbortController?.signal,
  viewToken = state.viewLoadToken,
  requestedDate = state.pendingDateNavigation?.target || state.selectedDate,
} = {}) {
  const requestToken = ++state.dayLoadToken;
  const dateNavigation =
    state.pendingDateNavigation?.target === requestedDate
      ? { ...state.pendingDateNavigation }
      : null;
  clearError();
  if (!dateNavigation && state.day?.date !== requestedDate) renderDayLoading();
  try {
    const day = await api(`/api/day?date=${encodeURIComponent(requestedDate)}`, {
      signal,
    });
    const navigationIsCurrent = dateNavigation
      ? state.pendingDateNavigation?.id === dateNavigation.id &&
        state.pendingDateNavigation.target === requestedDate
      : !state.pendingDateNavigation && requestedDate === state.selectedDate;
    if (
      requestToken !== state.dayLoadToken ||
      !navigationIsCurrent ||
      viewToken !== state.viewLoadToken ||
      state.view !== "today"
    ) {
      return;
    }
    if (dateNavigation) {
      const restoreDateFocus =
        document.activeElement === elements.returnTodayButton;
      try {
        await playDateTransition({
          direction: dateNavigation.direction,
          animate: dateNavigation.animate,
          isCurrent: () =>
            requestToken === state.dayLoadToken &&
            state.pendingDateNavigation?.id === dateNavigation.id &&
            state.pendingDateNavigation.target === requestedDate &&
            viewToken === state.viewLoadToken &&
            state.view === "today",
          commit: () => {
            reconcileIntakeActions(day, requestedDate);
            state.pendingDateNavigation = null;
            state.selectedDate = requestedDate;
            state.contextFormDirty = false;
            state.contextFormRevision += 1;
            state.day = day;
            renderToday({ suppressMotion: true });
            setDateNavigationPending(false);
            announceSelectedDate();
            if (restoreDateFocus) {
              window.requestAnimationFrame(() => {
                elements.nextDayButton.focus({ preventScroll: true });
              });
            }
          },
        });
      } catch (error) {
        cancelDateTransition();
        if (state.pendingDateNavigation?.id === dateNavigation.id) {
          state.pendingDateNavigation = null;
        }
        setDateNavigationPending(false);
        showError(error);
      }
    } else {
      reconcileIntakeActions(day, requestedDate);
      state.day = day;
      renderToday();
    }
  } catch (error) {
    const navigationIsCurrent = dateNavigation
      ? state.pendingDateNavigation?.id === dateNavigation.id &&
        state.pendingDateNavigation.target === requestedDate
      : !state.pendingDateNavigation && requestedDate === state.selectedDate;
    if (
      isAbortError(error) ||
      requestToken !== state.dayLoadToken ||
      !navigationIsCurrent ||
      viewToken !== state.viewLoadToken ||
      state.view !== "today"
    ) {
      return;
    }
    if (dateNavigation) {
      state.pendingDateNavigation = null;
      setDateNavigationPending(false);
    }
    if (!dateNavigation && state.day && state.day.date !== requestedDate) {
      state.selectedDate = state.day.date;
      state.contextFormDirty = false;
      state.contextFormRevision += 1;
      renderToday();
    }
    showError(error);
  }
}

function reconcileIntakeActions(day, date) {
  for (const action of state.intakeActions.values()) {
    if (action.displayDate !== date || action.phase !== "error") continue;
    const item =
      action.date === date
        ? day.items.find((candidate) => candidate.id === action.itemId)
        : (day.carryoverItems || []).find(
            (candidate) =>
              candidate.id === action.itemId &&
              candidate.routineDate === action.date,
          );
    const confirmed =
      action.operation === "record"
        ? action.date === date &&
          Boolean(item?.taken && item.takenAt === action.takenAt)
        : Boolean(item && !item.taken);
    if (!confirmed) continue;
    action.phase = "success";
    action.errorMessage = "";
    action.itemSnapshot = item ? { ...item } : action.itemSnapshot;
    scheduleIntakeFeedbackRemoval(action);
  }
}

function scheduleIntakeFeedbackRemoval(action, delay = 6000) {
  if (
    action.operation === "record" &&
    action.scheduleAdjustment?.status === "outside_window"
  ) {
    return;
  }
  window.clearTimeout(action.removalTimer);
  window.clearTimeout(action.exitTimer);
  action.removalTimer = window.setTimeout(() => {
    const key = intakeActionKey(action.date, action.itemId);
    const current = state.intakeActions.get(key);
    if (!current || current.token !== action.token || current.phase !== "success") return;
    const identity = intakeIdentity(action.date, action.itemId);
    const feedback = document.querySelector(
      `[data-intake-feedback-id="${identity}"]`,
    );
    if (
      document.hidden ||
      feedback?.contains(document.activeElement) ||
      feedback?.matches(":hover")
    ) {
      scheduleIntakeFeedbackRemoval(action, 1000);
      return;
    }
    const finish = () => {
      const latest = state.intakeActions.get(key);
      if (!latest || latest.token !== action.token || latest.phase !== "success") {
        return;
      }
      state.intakeActions.delete(key);
      if (
        state.view === "today" &&
        state.selectedDate === action.displayDate &&
        state.day
      ) {
        renderToday();
      }
    };
    if (!feedback || reduceMotionQuery.matches) {
      finish();
      return;
    }
    feedback.classList.add("is-motion-leaving");
    action.exitTimer = window.setTimeout(finish, 140);
  }, delay);
}

function updateCarryoverLocally(action, updatedItem) {
  if (!state.day || state.selectedDate !== action.displayDate) return;
  const items = state.day.carryoverItems || [];
  state.day.carryoverItems = items.filter(
    (item) =>
      !(
        item.id === action.itemId &&
        itemRoutineDate(item, state.day.date) === action.date
      ),
  );
  if (
    action.operation === "undo" &&
    updatedItem?.scheduledAt?.slice(0, 10) === action.displayDate
  ) {
    state.day.carryoverItems.push({
      ...updatedItem,
      routineDate: action.date,
      taken: false,
      takenAt: null,
    });
    state.day.carryoverItems.sort(
      (left, right) => scheduledDate(left) - scheduledDate(right),
    );
  }
}

async function runIntakeAction(action) {
  const key = intakeActionKey(action.date, action.itemId);
  const current = state.intakeActions.get(key);
  if (!current || current.token !== action.token) return;
  const mutation = acquireDayMutation("intake", action.date);
  if (!mutation) return;
  let confirmedTransition = false;

  action.attempt = (action.attempt || 0) + 1;
  action.phase = "pending";
  action.errorMessage = "";
  state.dayLoadToken += 1;
  clearError();
  if (state.selectedDate === action.displayDate && state.day) {
    renderToday();
    focusIntakeAfterRender(action);
  }

  try {
    const day =
      action.operation === "undo"
        ? await api(
            `/api/intakes/${encodeURIComponent(action.date)}/${action.itemId}`,
            { method: "DELETE" },
          )
        : await api("/api/intakes", {
            method: "POST",
            body: JSON.stringify({
              date: action.date,
              scheduleItemId: action.itemId,
              takenAt: action.takenAt,
            }),
          });
    const latest = state.intakeActions.get(key);
    if (!latest || latest.token !== action.token) return;
    action.phase = "success";
    action.scheduleAdjustment =
      action.operation === "record" ? day.scheduleAdjustment || null : null;
    const updatedItem = day.items.find((item) => item.id === action.itemId);
    if (updatedItem) {
      action.itemSnapshot = {
        ...updatedItem,
        ...(action.date === action.displayDate
          ? {}
          : { routineDate: action.date }),
      };
      if (action.operation === "record") action.takenAt = updatedItem.takenAt;
    }
    if (state.selectedDate === action.displayDate) {
      if (action.date === action.displayDate) {
        state.dayLoadToken += 1;
        state.day = day;
      } else {
        updateCarryoverLocally(action, updatedItem);
        await loadDay();
      }
      const adjustmentCopy = intakeAdjustmentCopy(
        action.scheduleAdjustment,
        action.itemSnapshot.takenAt || action.takenAt,
      );
      showToast(
        action.operation === "record"
          ? `${action.itemSnapshot.name}已记录${adjustmentCopy?.toast ? `；${adjustmentCopy.toast}` : ""}`
          : `${action.itemSnapshot.name}已撤销`,
      );
    }
    confirmedTransition = true;
    scheduleIntakeFeedbackRemoval(action);
  } catch (error) {
    const latest = state.intakeActions.get(key);
    if (!latest || latest.token !== action.token) return;
    const verb = action.operation === "record" ? "记录" : "撤销";
    const definitive =
      error instanceof ApiError && error.status >= 400 && error.status < 500;
    action.phase = "error";
    action.errorMessage = definitive
      ? `无法${verb}：${error.message}`
      : `未能确认是否${verb}，请重试核对：${error instanceof ApiError ? error.message : "网络连接中断"}`;
    if (state.selectedDate === action.displayDate) {
      showError(new Error(action.errorMessage));
    }
  } finally {
    releaseDayMutation(mutation);
    if (
      state.view === "today" &&
      state.selectedDate === action.displayDate &&
      state.day
    ) {
      renderToday();
      if (confirmedTransition) playIntakeTransition(action);
      focusIntakeAfterRender(action);
    }
  }
}

function toggleIntake(
  itemId,
  requestedOperation = null,
  focusRequest = null,
  routineDate = state.selectedDate,
) {
  if (!hasReadyDay() || state.dayMutation || state.pendingDateNavigation) return;
  const existing = intakeActionFor(itemId, routineDate);
  const item = findDayItem(itemId, routineDate) || existing?.itemSnapshot;
  if (!item) return;
  if (existing?.phase === "error") {
    existing.manageFocus = Boolean(focusRequest?.keyboard);
    existing.focusSurface = focusRequest?.surface || "timeline";
    existing.focusPhase = "";
    existing.displayDate = state.selectedDate;
    runIntakeAction(existing);
    return;
  }
  if (existing?.removalTimer) window.clearTimeout(existing.removalTimer);
  if (existing?.exitTimer) window.clearTimeout(existing.exitTimer);
  const operation = requestedOperation || (item.taken ? "undo" : "record");
  const action = {
    token: ++state.intakeToken,
    date: routineDate,
    displayDate: state.selectedDate,
    itemId,
    itemSnapshot: {
      ...item,
      ...(routineDate === state.selectedDate ? {} : { routineDate }),
    },
    operation,
    phase: "pending",
    takenAt: operation === "record" ? new Date().toISOString() : null,
    errorMessage: "",
    attempt: 0,
    manageFocus: Boolean(focusRequest?.keyboard),
    focusSurface: focusRequest?.surface || "timeline",
    focusPhase: "",
    scheduleAdjustment: null,
  };
  state.intakeActions.set(intakeActionKey(action.date, itemId), action);
  runIntakeAction(action);
}

async function checkInWake(event) {
  if (
    state.dayMutation ||
    state.pendingDateNavigation ||
    !hasReadyDay() ||
    state.selectedDate !== localDateKey(new Date()) ||
    state.day.wakeEvent
  ) {
    return;
  }

  const actionDate = state.selectedDate;
  const moveFocusAfterWake =
    event?.detail === 0 || document.activeElement === elements.wakeButton;
  const formRevision = state.contextFormRevision;
  const mutation = acquireDayMutation("wake", actionDate);
  if (!mutation) return;
  let confirmedTransition = false;
  state.dayLoadToken += 1;
  elements.wakeButton.textContent = "正在记录";
  clearError();
  try {
    const day = await api("/api/wake-events", {
      method: "POST",
      body: JSON.stringify({ date: actionDate }),
    });
    if (state.selectedDate !== actionDate) return;
    state.dayLoadToken += 1;
    if (state.contextFormRevision === formRevision) {
      state.contextFormDirty = false;
    }
    state.day = day;
    confirmedTransition = true;
    showToast("已记录起床，今日安排已更新");
  } catch (error) {
    if (state.selectedDate === actionDate) showError(error);
  } finally {
    releaseDayMutation(mutation);
    if (state.view === "today" && state.selectedDate === actionDate) {
      elements.wakeButton.textContent = "我起床了";
      if (state.day) {
        renderToday();
        if (confirmedTransition) {
          playMotionClass(elements.focusPanel, "is-wake-handoff", 420);
          if (moveFocusAfterWake) {
            window.requestAnimationFrame(() => {
              const target =
                elements.focusMedicationList.querySelector(
                  "[data-focus-intake-id]:not(:disabled)",
                ) || elements.adjustScheduleButton;
              target?.focus({ preventScroll: true });
              const rect = target?.getBoundingClientRect();
              if (rect && (rect.top < 52 || rect.bottom > window.innerHeight)) {
                target.scrollIntoView({ block: "nearest", behavior: "auto" });
              }
            });
          }
        }
      }
    }
  }
}

function openScheduleAdjustment() {
  setDetailsOpen(elements.contextDetails, true);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  elements.contextDetails.scrollIntoView({
    behavior: reduceMotion ? "auto" : "smooth",
    block: "start",
  });
  window.setTimeout(() => {
    elements.contextForm.elements.namedItem("wakeTime")?.focus({ preventScroll: true });
  }, reduceMotion ? 0 : 220);
}

async function ensureScheduleItems() {
  if (state.scheduleItemsLoaded) return state.scheduleItems;
  const schedule = await api("/api/schedule-items");
  applySchedulePayload(schedule);
  return state.scheduleItems;
}

async function contextItemsForScheduleSave(day) {
  if (!day) return [];
  if (day.untracked && !day.contextPersisted) {
    return (await ensureScheduleItems()).map((item) => ({ ...item, taken: false }));
  }
  return day.items.filter((item) => !item.taken);
}

function impactedCrossDayMedications(preview) {
  return preview.medications.filter(
    (item) => item.anchorDayOffset !== 0 || item.dayOffset !== 0,
  );
}

function renderCrossDayImpactList(pending) {
  const impacted = impactedCrossDayMedications(pending.preview);
  if (!impacted.length) {
    elements.crossDayImpactList.innerHTML =
      '<p class="cross-day-empty">没有未记录药物受此次跨日安排影响。</p>';
    return;
  }

  const groups = new Map();
  for (const item of impacted) {
    if (!groups.has(item.dateKey)) groups.set(item.dateKey, []);
    groups.get(item.dateKey).push(item);
  }
  elements.crossDayImpactList.innerHTML = Array.from(groups.entries())
    .map(([dateKey, items]) => {
      const offset = dayDifference(pending.baseDate, dateKey);
      const zeroLabel =
        pending.kind === "context"
          ? pending.baseDate === localDateKey(new Date())
            ? "今日"
            : "当日"
          : "计划当日";
      return `
        <section class="cross-day-impact-group" aria-label="${escapeHtml(formatCalendarDate(dateKey))}">
          <h3>${escapeHtml(dayOffsetLabel(offset, zeroLabel))} · ${escapeHtml(formatCalendarDate(dateKey))}</h3>
          <ul>
            ${items
              .map(
                (item) => `
                  <li>
                    <div>
                      <strong>${escapeHtml(item.name)}</strong>
                      <span>${escapeHtml(item.dose)}</span>
                    </div>
                    <time datetime="${escapeHtml(`${dateKey}T${item.time}`)}">${escapeHtml(item.time)}</time>
                  </li>`,
              )
              .join("")}
          </ul>
        </section>`;
    })
    .join("");
}

function openCrossDayConfirmation(pending) {
  state.pendingScheduleSave = pending;
  const isContext = pending.kind === "context";
  elements.cancelCrossDayButton.disabled = false;
  elements.confirmCrossDayButton.disabled = false;
  elements.crossDayDialogDescription.textContent = isContext
    ? `${formatCalendarDate(pending.baseDate)}的安排包含跨日时段。确认后，只会调整尚未记录的用药。`
    : `常用作息包含跨日时段。以下以 ${formatCalendarDate(pending.baseDate)} 为计划日示例。`;
  elements.crossDayReason.textContent = schedulePreviewReason(pending.preview);
  renderCrossDayImpactList(pending);
  elements.crossDayPreservedNote.textContent = isContext
    ? pending.preservedCount
      ? `已记录的 ${pending.preservedCount} 项保留原计划时间，不会改变。`
      : "当前没有已记录项目；确认后，未记录项目会采用以上日期。"
    : "常用作息只用于之后新建立的日期和起床后推算，不会更改已经建立的日期。";
  elements.crossDayDialogError.hidden = true;
  elements.crossDayDialogError.textContent = "";
  elements.confirmCrossDayButton.textContent = isContext
    ? "确认并保存当日安排"
    : "确认并保存常用作息";
  elements.crossDayDialog.showModal();
  window.requestAnimationFrame(() => elements.cancelCrossDayButton.focus());
}

function closeCrossDayConfirmation() {
  if (state.pendingScheduleSave?.saving) return;
  const trigger = state.pendingScheduleSave?.trigger;
  state.pendingScheduleSave = null;
  if (elements.crossDayDialog.open) elements.crossDayDialog.close("cancel");
  trigger?.focus();
}

async function commitScheduleSave(pending) {
  if (pending.saving) return;
  const isContext = pending.kind === "context";
  const isPreferences = pending.kind === "preferences";
  if (isPreferences && state.preferencesSaveBusy) return;
  const mutation = isContext
    ? acquireDayMutation("context", pending.baseDate)
    : null;
  if (isContext && !mutation) {
    if (elements.crossDayDialog.open) {
      elements.crossDayDialogError.textContent = "另一项当日操作正在处理，请稍候再试";
      elements.crossDayDialogError.hidden = false;
    } else {
      showToast("另一项当日操作正在处理，请稍候");
    }
    return;
  }
  if (isPreferences) setPreferencesSaveBusy(true);
  pending.saving = true;
  const inDialog = elements.crossDayDialog.open;
  const actionButton = inDialog ? elements.confirmCrossDayButton : pending.trigger;
  const originalLabel = actionButton.textContent;
  actionButton.disabled = true;
  actionButton.textContent = "正在保存";
  if (inDialog) elements.cancelCrossDayButton.disabled = true;
  clearError();

  try {
    if (pending.kind === "context") {
      const day = await api(
        `/api/context/${encodeURIComponent(pending.baseDate)}`,
        { method: "PUT", body: JSON.stringify(pending.payload) },
      );
      if (state.selectedDate === pending.baseDate) {
        state.dayLoadToken += 1;
        if (state.contextFormRevision === pending.formRevision) {
          state.contextFormDirty = false;
        }
        state.day = day;
        renderToday();
      }
      showToast(
        !pending.wasPersisted
          ? "当日计划已建立"
          : pending.baseDate === localDateKey(new Date())
            ? "今日提醒时间已更新"
            : "当日提醒时间已更新",
      );
    } else {
      state.preferences = await api("/api/preferences", {
        method: "PUT",
        body: JSON.stringify(pending.payload),
      });
      if (state.preferencesFormRevision === pending.formRevision) {
        state.preferencesFormDirty = false;
        fillTimeForm(elements.preferencesForm, state.preferences);
      }
      renderPreferencesTimePreview();
      showToast("默认作息已保存");
    }
    if (inDialog) {
      state.pendingScheduleSave = null;
      elements.crossDayDialog.close("saved");
      pending.trigger?.focus();
    }
  } catch (error) {
    if (inDialog) {
      console.error(error);
      elements.crossDayDialogError.textContent = error?.message || "保存时出现问题，请重试";
      elements.crossDayDialogError.hidden = false;
      setSyncState("保存失败", false);
    } else {
      showError(error);
    }
  } finally {
    pending.saving = false;
    if (inDialog) {
      actionButton.disabled = false;
      actionButton.textContent = originalLabel;
      elements.cancelCrossDayButton.disabled = false;
    } else if (!isContext) {
      actionButton.disabled = false;
      actionButton.textContent = originalLabel;
    }
    if (mutation) {
      releaseDayMutation(mutation);
      if (state.day?.date === state.selectedDate) renderToday();
    }
    if (isPreferences) setPreferencesSaveBusy(false);
  }
}

async function requestContextSave() {
  if (
    state.dayMutation ||
    state.pendingDateNavigation ||
    !hasReadyDay() ||
    !elements.contextForm.reportValidity()
  ) {
    return;
  }
  const sourceDay = state.day;
  const baseDate = state.selectedDate;
  const formRevision = state.contextFormRevision;
  const payload = readTimeForm(elements.contextForm);
  if (sourceDay.contextPersisted && contextsEqual(payload, sourceDay.context)) {
    state.contextFormDirty = false;
    renderContextTimePreview(sourceDay.contextDayOffsets);
    showToast("时间没有变化");
    return;
  }
  try {
    const items = await contextItemsForScheduleSave(sourceDay);
    if (
      state.selectedDate !== baseDate ||
      state.day !== sourceDay ||
      state.contextFormRevision !== formRevision
    ) {
      return;
    }
    const preview = schedulePreview(baseDate, payload, items);
    const pending = {
      kind: "context",
      payload,
      baseDate,
      preview,
      preservedCount: sourceDay.items.filter((item) => item.taken).length,
      wasPersisted: sourceDay.persisted,
      trigger: elements.saveContextButton,
      saving: false,
      formRevision,
    };
    if (preview.crossesDay) openCrossDayConfirmation(pending);
    else await commitScheduleSave(pending);
  } catch (error) {
    showError(error);
  }
}

function renderHistory() {
  if (!state.history) return;
  const { summary, days } = state.history;
  const hasTrackedDoses = summary.total > 0;
  elements.historyCompleted.textContent = String(summary.completed);
  elements.historyTotal.textContent = hasTrackedDoses
    ? ` / ${summary.total}`
    : " / —";
  elements.historyPercent.textContent = hasTrackedDoses
    ? `${summary.percent}%`
    : "—";
  elements.historyRateLabel.textContent = hasTrackedDoses
    ? "完成率"
    : "暂无记录";
  elements.historyList.innerHTML = days
    .slice()
    .reverse()
    .map((entry) => {
      const hasDailyPlan = entry.total > 0;
      const accessibleStatus = hasDailyPlan
        ? `完成率 ${entry.percent}%`
        : "当天未建立用药记录";
      return `
        <div class="history-row" role="listitem">
          <div class="history-date">
            <span>${escapeHtml(formatShortDate(entry.date))}</span>
            <small>${escapeHtml(weekdayName(entry.date))}</small>
          </div>
          <div class="history-bar" aria-hidden="true">
            <span data-history-progress="${entry.percent}" style="--history-progress: ${reduceMotionQuery.matches ? Math.max(0, Math.min(100, entry.percent)) / 100 : 0}"></span>
          </div>
          <div class="history-value">${entry.completed} / ${entry.total || "—"}</div>
          <span class="sr-only">${accessibleStatus}</span>
        </div>`;
    })
    .join("");
  if (!reduceMotionQuery.matches) {
    window.requestAnimationFrame(() => {
      elements.historyList
        .querySelectorAll("[data-history-progress]")
        .forEach((bar) => {
          const percent = Number(bar.dataset.historyProgress);
          bar.style.setProperty(
            "--history-progress",
            String(Math.max(0, Math.min(100, percent)) / 100),
          );
        });
    });
  }
}

async function loadHistory({
  signal = state.viewAbortController?.signal,
  viewToken = state.viewLoadToken,
} = {}) {
  const isCurrent = () =>
    !signal?.aborted &&
    viewToken === state.viewLoadToken &&
    state.view === "history";
  if (!isCurrent()) return;
  clearError();
  elements.historyList.innerHTML = '<div class="empty-state">正在读取记录</div>';
  try {
    const history = await api(
      `/api/history?days=7&end=${encodeURIComponent(localDateKey(new Date()))}`,
      { signal },
    );
    if (!isCurrent()) return;
    state.history = history;
    renderHistory();
    playMotionClass(elements.historyList, "is-data-ready", 300);
  } catch (error) {
    if (!isAbortError(error) && isCurrent()) showError(error);
  }
}

function formatScheduleMoment(item) {
  const anchor = anchorLabels[item.anchor] || item.anchor;
  if (item.offsetMinutes === 0) return anchor;
  if (item.offsetMinutes < 0) return `${anchor}前 ${Math.abs(item.offsetMinutes)} 分钟`;
  return `${anchor}后 ${item.offsetMinutes} 分钟`;
}

function scheduleSummaryForItems(items) {
  return {
    medicationCount: new Set(items.map((item) => item.name.trim())).size,
    dailyAdministrationCount: items.length,
  };
}

function normalizedTimingMode(medication) {
  if (Object.hasOwn(timingModeLabels, medication?.timingMode)) {
    return medication.timingMode;
  }
  if (medication?.adjustAfterIntake === true) return "interval";
  const schedules = Array.isArray(medication?.schedules)
    ? medication.schedules
    : [];
  if (
    schedules.length &&
    schedules.every((item) => ["breakfast", "lunch", "dinner"].includes(item.anchor))
  ) {
    return "meal";
  }
  return "routine";
}

function applySchedulePayload(schedule) {
  const payloadMedications = Array.isArray(schedule?.medications)
    ? schedule.medications
    : null;
  const payloadItems = Array.isArray(schedule?.items) ? schedule.items : [];
  const fallbackMedications = groupScheduleItemsByMedication(payloadItems).map(
    ({ name, items }) => ({
      id: items[0]?.medicationId ?? items[0]?.id,
      name,
      revision: 1,
      schedules: items,
    }),
  );
  const medications = (payloadMedications ?? fallbackMedications).map((medication) => ({
    id: medication.id,
    name: String(medication.name || "").trim(),
    revision: Number.isInteger(medication.revision) ? medication.revision : 1,
    timingMode: normalizedTimingMode(medication),
    maxAutoShiftMinutes:
      Number.isInteger(medication.maxAutoShiftMinutes) &&
      medication.maxAutoShiftMinutes >= 1 &&
      medication.maxAutoShiftMinutes <= 240
        ? medication.maxAutoShiftMinutes
        : 120,
    schedules: (Array.isArray(medication.schedules) ? medication.schedules : [])
      .slice()
      .sort(compareScheduleItems),
  }));
  const items = payloadItems.length
    ? payloadItems
    : medications.flatMap((medication) =>
      medication.schedules.map((item) => ({
        ...item,
        medicationId: medication.id,
        name: medication.name,
      })),
    );
  const fallback = scheduleSummaryForItems(items);
  const medicationCount = schedule?.summary?.medicationCount;
  const dailyAdministrationCount = schedule?.summary?.dailyAdministrationCount;
  state.medications = medications;
  state.scheduleItems = items;
  state.scheduleSummary = {
    medicationCount:
      Number.isInteger(medicationCount) && medicationCount >= 0
        ? medicationCount
        : fallback.medicationCount,
    dailyAdministrationCount:
      Number.isInteger(dailyAdministrationCount) && dailyAdministrationCount >= 0
        ? dailyAdministrationCount
        : fallback.dailyAdministrationCount,
  };
  state.scheduleItemsLoaded = true;
}

function medicationFirstSortOrder(medication) {
  return Math.min(
    ...(medication.schedules || []).map(
      (schedule) => schedule.sortOrder ?? Number.MAX_SAFE_INTEGER,
    ),
    Number.MAX_SAFE_INTEGER,
  );
}

function compareMedicationPlanOrder(left, right) {
  const sortDifference =
    medicationFirstSortOrder(left) - medicationFirstSortOrder(right);
  if (sortDifference) return sortDifference;
  return (left.id ?? Number.MAX_SAFE_INTEGER) -
    (right.id ?? Number.MAX_SAFE_INTEGER);
}

function applyMedicationMutationPayload(payload, { archivedMedicationId = null } = {}) {
  let medications = state.medications.filter(
    (medication) => medication.id !== archivedMedicationId,
  );
  if (payload?.medication) {
    const saved = payload.medication;
    const existingIndex = medications.findIndex(
      (medication) => medication.id === saved.id,
    );
    if (existingIndex >= 0) medications[existingIndex] = saved;
    else medications.push(saved);
  }
  medications = medications.slice().sort(compareMedicationPlanOrder);
  applySchedulePayload({ medications, summary: payload?.summary });
  renderPlan();
}

function compareScheduleItems(left, right) {
  const anchorDifference =
    (scheduleAnchorOrder.get(left.anchor) ?? Number.MAX_SAFE_INTEGER) -
    (scheduleAnchorOrder.get(right.anchor) ?? Number.MAX_SAFE_INTEGER);
  if (anchorDifference) return anchorDifference;
  if (left.offsetMinutes !== right.offsetMinutes) {
    return left.offsetMinutes - right.offsetMinutes;
  }
  return (left.sortOrder ?? 0) - (right.sortOrder ?? 0);
}

function groupScheduleItemsByMedication(items) {
  const groups = new Map();
  for (const item of items) {
    const key = item.name.trim();
    if (!groups.has(key)) groups.set(key, { name: key, items: [] });
    groups.get(key).items.push(item);
  }
  for (const group of groups.values()) {
    group.items.sort(compareScheduleItems);
  }
  return Array.from(groups.values());
}

function informativeScheduleInstruction(item) {
  const instruction = item.instructions.trim();
  const isMeal = ["breakfast", "lunch", "dinner"].includes(item.anchor);
  if (!isMeal) return instruction;
  if (item.offsetMinutes < 0 && instruction === "餐前") return "";
  if (item.offsetMinutes > 0 && instruction === "餐后") return "";
  return instruction;
}

function renderPlan() {
  elements.planMedicationCount.textContent = `${state.scheduleSummary.medicationCount} 种药`;
  elements.planAdministrationCount.textContent =
    `每日 ${state.scheduleSummary.dailyAdministrationCount} 次安排`;
  if (!state.medications.length) {
    elements.planList.innerHTML = '<li class="empty-state">暂无生效的用药安排</li>';
    return;
  }
  elements.planList.innerHTML = state.medications
    .map(
      ({ id, name, timingMode, schedules }, groupIndex) => {
        const headingId = `plan-medication-${id ?? groupIndex}`;
        const timingSummary = timingModeLabels[timingMode] || timingModeLabels.routine;
        return `
        <li class="plan-medication" aria-labelledby="${headingId}">
          <div class="plan-medication-header">
            <div class="plan-medication-heading-copy">
              <h3 id="${headingId}" dir="auto">${escapeHtml(name)}</h3>
              <p>${schedules.length} 次/日 · ${timingSummary}</p>
            </div>
            <button class="secondary-button plan-manage-button" type="button" data-manage-medication-id="${id}" aria-label="编辑${escapeHtml(name)}的每日安排">编辑安排</button>
          </div>
          <ul class="plan-schedules" aria-label="${escapeHtml(name)}的每日安排">
            ${schedules
            .map(
              (item) => {
                const moment = formatScheduleMoment(item);
                const instruction = informativeScheduleInstruction(item);
                const details = [item.dose, instruction].filter(Boolean).join(" · ");
                return `
                <li class="plan-row" data-plan-item-id="${item.id}">
                  <div class="plan-row-copy">
                    <p class="plan-moment" dir="auto">${escapeHtml(moment)}</p>
                    <p class="plan-meta" dir="auto">${escapeHtml(details)}</p>
                  </div>
                </li>`;
              },
            )
            .join("")}
          </ul>
        </li>`;
      },
    )
    .join("");
}

async function loadPlan({
  signal = state.viewAbortController?.signal,
  viewToken = state.viewLoadToken,
  focusRequest = null,
} = {}) {
  const loadToken = ++state.planLoadToken;
  const formRevision = state.preferencesFormRevision;
  const isCurrent = () =>
    !signal?.aborted &&
    loadToken === state.planLoadToken &&
    viewToken === state.viewLoadToken &&
    state.view === "plan";
  if (!isCurrent()) return;
  clearError();
  setPlanLoading(true);
  elements.planList.classList.toggle("is-updating", Boolean(focusRequest));
  if (!focusRequest) {
    elements.planList.innerHTML = '<li class="empty-state">正在读取用药计划</li>';
  }
  try {
    const [schedule, preferences] = await Promise.all([
      api("/api/medications", { signal }),
      api("/api/preferences", { signal }),
    ]);
    if (!isCurrent()) return;
    applySchedulePayload(schedule);
    state.preferences = preferences;
    if (
      !state.preferencesFormDirty &&
      state.preferencesFormRevision === formRevision
    ) {
      fillTimeForm(elements.preferencesForm, state.preferences);
    }
    renderPreferencesTimePreview();
    renderPlan();
    playMotionClass(elements.planList, "is-data-ready", 300);
    focusPlanAfterLoad(focusRequest);
  } catch (error) {
    if (!isAbortError(error) && isCurrent()) showError(error);
  } finally {
    if (loadToken === state.planLoadToken) {
      elements.planList.classList.remove("is-updating");
      setPlanLoading(false);
    }
  }
}

function focusPlanAfterLoad(request) {
  if (!request) return;
  window.requestAnimationFrame(() => {
    const target = request.medicationId
      ? elements.planList.querySelector(
        `[data-manage-medication-id="${request.medicationId}"]`,
      )
      : null;
    const focusTarget = target || request.fallback || elements.addMedicationButton;
    if (target && request.animate) {
      playMotionClass(target.closest(".plan-medication"), "is-plan-updated", 320);
    }
    focusTarget?.focus({ preventScroll: true });
    focusTarget?.scrollIntoView({ block: "nearest", behavior: "auto" });
  });
}

async function requestPreferencesSave() {
  if (state.planLoading || state.preferencesSaveBusy) return;
  const basicValuesValid = contextFieldOrder.every(({ field }) => {
    const input = elements.preferencesForm.elements.namedItem(field);
    return input?.checkValidity();
  });
  if (!basicValuesValid) {
    elements.preferencesForm.reportValidity();
    return;
  }

  try {
    await ensureScheduleItems();
    const preview = renderPreferencesTimePreview();
    if (!preview || !elements.preferencesForm.reportValidity()) return;
    const payload = readTimeForm(elements.preferencesForm);
    if (contextsEqual(payload, state.preferences)) {
      state.preferencesFormDirty = false;
      showToast("时间没有变化");
      return;
    }
    const pending = {
      kind: "preferences",
      payload,
      baseDate: preview.baseDate,
      preview,
      preservedCount: 0,
      trigger: elements.savePreferencesButton,
      saving: false,
      formRevision: state.preferencesFormRevision,
    };
    if (preview.crossesDay) openCrossDayConfirmation(pending);
    else await commitScheduleSave(pending);
  } catch (error) {
    showError(error);
  }
}

function emptyScheduleDraft() {
  return {
    id: null,
    dose: "",
    instructions: "",
    anchor: "",
    offsetMinutes: 0,
  };
}

function scheduleRelation(offsetMinutes) {
  if (offsetMinutes < 0) return "before";
  if (offsetMinutes > 0) return "after";
  return "at";
}

function selectedOption(value, expected) {
  return value === expected ? " selected" : "";
}

function scheduleAnchorOptions(selectedAnchor) {
  const options = [
    `<option value="" disabled${selectedOption(selectedAnchor, "")}>请选择</option>`,
  ];
  for (const [value, label] of Object.entries(anchorLabels)) {
    options.push(
      `<option value="${value}"${selectedOption(selectedAnchor, value)}>${label}</option>`,
    );
  }
  return options.join("");
}

function scheduleEditorRowMarkup(schedule, index, total) {
  const relation = scheduleRelation(Number(schedule.offsetMinutes));
  const minutes = Math.abs(Number(schedule.offsetMinutes) || 0);
  const moment = schedule.anchor ? formatScheduleMoment(schedule) : `第 ${index + 1} 次安排`;
  return `
    <li class="schedule-editor-row" data-schedule-editor-row data-schedule-id="${schedule.id ?? ""}">
      <fieldset>
        <legend class="sr-only">第 ${index + 1} 次服用安排</legend>
        <div class="schedule-editor-row-heading">
          <span>第 ${index + 1} 次</span>
          <button class="remove-schedule-button" type="button" data-remove-schedule-index="${index}" aria-label="移除${escapeHtml(moment)}"${total === 1 ? " disabled" : ""}>移除</button>
        </div>
        <div class="schedule-editor-fields">
          <label class="form-field schedule-anchor-field">
            <span>关联时段</span>
            <select data-schedule-field="anchor" aria-errormessage="medicationDialogErrorMessage" required>
              ${scheduleAnchorOptions(schedule.anchor)}
            </select>
          </label>
          <label class="form-field schedule-relation-field">
            <span>相对位置</span>
            <select data-schedule-field="relation" aria-errormessage="medicationDialogErrorMessage" required>
              <option value="before"${selectedOption(relation, "before")}>前</option>
              <option value="at"${selectedOption(relation, "at")}>当时</option>
              <option value="after"${selectedOption(relation, "after")}>后</option>
            </select>
          </label>
          <label class="form-field schedule-minutes-field">
            <span>分钟</span>
            <input type="number" data-schedule-field="minutes" min="1" max="240" step="1" value="${minutes}" aria-errormessage="medicationDialogErrorMessage" required${relation === "at" ? " disabled" : ""} />
          </label>
          <label class="form-field schedule-dose-field">
            <span>单次剂量</span>
            <input type="text" data-schedule-field="dose" dir="auto" data-code-point-max="80" data-field-label="单次剂量" value="${escapeHtml(schedule.dose)}" aria-errormessage="medicationDialogErrorMessage" required />
          </label>
          <label class="form-field schedule-instructions-field">
            <span>服用要求</span>
            <input type="text" data-schedule-field="instructions" dir="auto" data-code-point-max="160" data-field-label="服用要求" value="${escapeHtml(schedule.instructions)}" aria-errormessage="medicationDialogErrorMessage" placeholder="例如：餐后，整片吞服" />
          </label>
        </div>
      </fieldset>
    </li>`;
}

function readScheduleEditorRow(row) {
  const relation = row.querySelector('[data-schedule-field="relation"]').value;
  const minutes = Number(
    row.querySelector('[data-schedule-field="minutes"]').value || 0,
  );
  const id = Number(row.dataset.scheduleId);
  return {
    ...(Number.isInteger(id) && id > 0 ? { id } : {}),
    dose: row.querySelector('[data-schedule-field="dose"]').value,
    instructions: row.querySelector('[data-schedule-field="instructions"]').value,
    anchor: row.querySelector('[data-schedule-field="anchor"]').value,
    offsetMinutes:
      relation === "before" ? -minutes : relation === "after" ? minutes : 0,
  };
}

function readScheduleEditorRows() {
  return Array.from(
    elements.scheduleEditorList.querySelectorAll("[data-schedule-editor-row]"),
    readScheduleEditorRow,
  );
}

function codePointLength(value) {
  return Array.from(value).length;
}

function validateMedicationTextField(field) {
  const value = field.value.trim();
  const maximum = Number(field.dataset.codePointMax);
  const label = field.dataset.fieldLabel || "此字段";
  let message = "";
  if (field.required && !value) {
    message = `请填写${label}`;
  } else if (Number.isInteger(maximum) && codePointLength(value) > maximum) {
    message = `${label}最多 ${maximum} 个字符`;
  }
  field.setCustomValidity(message);
  if (message) field.setAttribute("aria-invalid", "true");
  else field.removeAttribute("aria-invalid");
  return !message;
}

function validateMedicationForm() {
  elements.medicationForm
    .querySelectorAll('[data-schedule-field="anchor"]')
    .forEach((field) => {
      field.setCustomValidity("");
      field.removeAttribute("aria-invalid");
    });
  elements.medicationForm
    .querySelectorAll("[data-code-point-max]")
    .forEach(validateMedicationTextField);
  const valid = elements.medicationForm.checkValidity();
  if (!valid) elements.medicationForm.reportValidity();
  return valid;
}

function updateScheduleRemoveLabel(row) {
  const rows = Array.from(
    elements.scheduleEditorList.querySelectorAll("[data-schedule-editor-row]"),
  );
  const index = rows.indexOf(row);
  if (index < 0) return;
  const schedule = readScheduleEditorRow(row);
  const moment = schedule.anchor
    ? formatScheduleMoment(schedule)
    : `第 ${index + 1} 次安排`;
  row
    .querySelector("[data-remove-schedule-index]")
    ?.setAttribute("aria-label", `移除${moment}`);
}

function readMedicationEditorDraft() {
  const id = Number(elements.medicationForm.elements.namedItem("id").value);
  const revision = Number(
    elements.medicationForm.elements.namedItem("revision").value,
  );
  return {
    ...(Number.isInteger(id) && id > 0 ? { id } : {}),
    ...(Number.isInteger(revision) && revision > 0 ? { revision } : {}),
    name: elements.medicationForm.elements.namedItem("name").value,
    timingMode:
      elements.medicationForm.elements.namedItem("timingMode").value || "routine",
    maxAutoShiftMinutes: Number(elements.maxAutoShiftMinutesInput.value),
    schedules: readScheduleEditorRows(),
  };
}

function medicationEditorSignature() {
  return JSON.stringify(readMedicationEditorDraft());
}

function updateScheduleEditorFrequency() {
  const count = elements.scheduleEditorList.querySelectorAll(
    "[data-schedule-editor-row]",
  ).length;
  elements.scheduleEditorFrequency.textContent = `${count} 次/日`;
  elements.addScheduleButton.disabled = count >= 24;
}

function renderScheduleEditor(schedules, { focusIndex = null } = {}) {
  const rows = schedules.length ? schedules : [emptyScheduleDraft()];
  elements.scheduleEditorList.innerHTML = rows
    .map((schedule, index) => scheduleEditorRowMarkup(schedule, index, rows.length))
    .join("");
  updateScheduleEditorFrequency();
  if (focusIndex === null) return;
  window.requestAnimationFrame(() => {
    elements.scheduleEditorList
      .querySelectorAll("[data-schedule-editor-row]")
      [focusIndex]?.querySelector('[data-schedule-field="anchor"]')
      ?.focus();
  });
}

function clearMedicationDialogFeedback() {
  elements.medicationDialogError.hidden = true;
  elements.medicationDialogErrorMessage.textContent = "";
  elements.reloadMedicationButton.hidden = true;
  state.medicationEditorRecovery = null;
}

function clearMedicationFieldValidity() {
  elements.medicationForm.querySelectorAll("input, select").forEach((field) => {
    field.setCustomValidity?.("");
    field.removeAttribute("aria-invalid");
  });
}

function clearMedicationValidationFeedback(field = null) {
  const recoveryKind = state.medicationEditorRecovery?.kind;
  if (recoveryKind && !(recoveryKind === "duplicate" && field?.name === "name")) {
    return;
  }
  if (elements.medicationDialogError.hidden) return;
  clearMedicationDialogFeedback();
  setSyncState("待保存");
}

function syncTimingModeControls() {
  const timingMode =
    elements.medicationForm.elements.namedItem("timingMode").value || "routine";
  const intervalBased = timingMode === "interval";
  elements.maxAutoShiftMinutesInput.disabled = !intervalBased;
  elements.timingModeAdvanced.hidden = !intervalBased;
  if (!intervalBased) elements.timingModeAdvanced.open = false;
}

function populateMedicationDialog(medication = null) {
  elements.medicationForm.reset();
  clearMedicationFieldValidity();
  clearMedicationDialogFeedback();
  elements.medicationDialogTitle.textContent = medication ? "编辑用药" : "添加药物";
  elements.archiveMedicationButton.hidden = !medication;
  elements.medicationForm.elements.namedItem("id").value = medication?.id ?? "";
  elements.medicationForm.elements.namedItem("revision").value =
    medication?.revision ?? "";
  elements.medicationForm.elements.namedItem("name").value = medication?.name ?? "";
  const timingMode = medication?.timingMode || "routine";
  const timingModeInput = elements.timingModeInputs.find(
    (input) => input.value === timingMode,
  );
  if (timingModeInput) timingModeInput.checked = true;
  elements.maxAutoShiftMinutesInput.value =
    medication?.maxAutoShiftMinutes ?? 120;
  elements.timingModeAdvanced.open = false;
  syncTimingModeControls();
  renderScheduleEditor(
    medication?.schedules?.map((schedule) => ({ ...schedule })) ?? [emptyScheduleDraft()],
  );
  elements.medicationDialog.querySelector(".medication-dialog-scroll").scrollTop = 0;
  state.medicationEditorInitialSignature = medicationEditorSignature();
}

function openMedicationDialog(medication = null) {
  if (state.medicationEditorBusy) return;
  populateMedicationDialog(medication);
  elements.medicationDialog.showModal();
  window.requestAnimationFrame(() => {
    const focusTarget = medication
      ? elements.medicationDialogTitle
      : elements.medicationForm.elements.namedItem("name");
    focusTarget?.focus();
  });
}

function requestCloseMedicationDialog() {
  if (state.medicationEditorBusy) return;
  if (
    state.medicationEditorInitialSignature &&
    medicationEditorSignature() !== state.medicationEditorInitialSignature &&
    !window.confirm("尚有未保存的更改，确定放弃吗？")
  ) {
    return;
  }
  state.medicationEditorInitialSignature = "";
  clearMedicationDialogFeedback();
  elements.medicationDialog.close();
}

function addScheduleEditorRow() {
  const schedules = readScheduleEditorRows();
  if (schedules.length >= 24) return;
  clearMedicationValidationFeedback();
  schedules.push(emptyScheduleDraft());
  renderScheduleEditor(schedules, { focusIndex: schedules.length - 1 });
}

function removeScheduleEditorRow(index) {
  const schedules = readScheduleEditorRows();
  if (schedules.length <= 1 || !schedules[index]) return;
  clearMedicationValidationFeedback();
  schedules.splice(index, 1);
  const focusIndex = Math.min(index, schedules.length - 1);
  renderScheduleEditor(schedules, { focusIndex });
}

function syncScheduleMinutesControl(row) {
  const relation = row.querySelector('[data-schedule-field="relation"]').value;
  const minutes = row.querySelector('[data-schedule-field="minutes"]');
  const exact = relation === "at";
  minutes.disabled = exact;
  if (exact) minutes.value = "0";
  else if (Number(minutes.value) < 1) minutes.value = "1";
}

function trapDialogFocus(event) {
  if (event.key !== "Tab") return;
  const dialog = event.currentTarget;
  const controls = Array.from(
    dialog.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((control) => !control.hidden && control.getClientRects().length > 0);
  if (!controls.length) return;
  const first = controls[0];
  const last = controls[controls.length - 1];
  const active = document.activeElement;
  if (event.shiftKey && (!dialog.contains(active) || active === first)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (!dialog.contains(active) || active === last)) {
    event.preventDefault();
    first.focus();
  }
}

function showMedicationDialogError(
  error,
  {
    message = "",
    recovery = false,
    recoveryKind = "latest",
    recoveryMedicationId = null,
    focus = "error",
  } = {},
) {
  elements.medicationDialogError.hidden = true;
  elements.medicationDialogErrorMessage.textContent =
    message || error?.message || "保存时出现问题，当前内容已保留";
  elements.reloadMedicationButton.hidden = !recovery;
  state.medicationEditorRecovery = recovery
    ? { kind: recoveryKind, medicationId: recoveryMedicationId }
    : null;
  elements.medicationDialogError.hidden = false;
  playMotionClass(elements.medicationDialogError, "is-entering", 220);
  setSyncState("保存未完成", false, "error");
  window.requestAnimationFrame(() => {
    if (focus === "recovery" && recovery) {
      elements.reloadMedicationButton.focus();
    } else if (focus === "error") {
      elements.medicationDialogError.focus();
    }
  });
}

function normalizedScheduleSignature(schedules) {
  return schedules
    .map((schedule) => ({
      dose: String(schedule.dose || "").trim(),
      instructions: String(schedule.instructions || "").trim(),
      anchor: schedule.anchor,
      offsetMinutes: Number(schedule.offsetMinutes),
    }))
    .sort(compareScheduleItems)
    .map(
      ({ dose, instructions, anchor, offsetMinutes }) =>
        JSON.stringify([anchor, offsetMinutes, dose, instructions]),
    );
}

function medicationMatchesDraft(medication, draft) {
  if (!medication || medication.name.trim() !== draft.name.trim()) return false;
  if (medication.timingMode !== draft.timingMode) return false;
  if (medication.maxAutoShiftMinutes !== draft.maxAutoShiftMinutes) return false;
  const current = normalizedScheduleSignature(medication.schedules || []);
  const requested = normalizedScheduleSignature(draft.schedules || []);
  return current.length === requested.length &&
    current.every((signature, index) => signature === requested[index]);
}

async function refreshMedicationPlanState() {
  const plan = await api("/api/medications");
  applySchedulePayload(plan);
  renderPlan();
  return plan;
}

function completeMedicationSave(
  medication,
  { payload = null, reconciled = false } = {},
) {
  if (payload) applyMedicationMutationPayload(payload);
  state.medicationEditorInitialSignature = "";
  clearMedicationDialogFeedback();
  elements.medicationDialog.close("saved");
  clearError();
  focusPlanAfterLoad({
    medicationId: medication.id,
    fallback: elements.addMedicationButton,
    animate: true,
  });
  showToast(
    `${medication.name}已${reconciled ? "核对并确认保存" : "保存"}，每日 ${medication.schedules.length} 次`,
  );
}

function completeMedicationArchive(
  medication,
  neighbor,
  { payload = null, reconciled = false } = {},
) {
  if (payload) {
    applyMedicationMutationPayload(payload, {
      archivedMedicationId: medication.id,
    });
  }
  state.medicationEditorInitialSignature = "";
  clearMedicationDialogFeedback();
  elements.medicationDialog.close("archived");
  clearError();
  focusPlanAfterLoad({
    medicationId: neighbor?.id,
    fallback: elements.addMedicationButton,
  });
  showToast(`${medication.name}已${reconciled ? "核对并确认停用" : "停用"}`);
}

async function reconcileMedicationSave(draft) {
  let plan;
  try {
    plan = await refreshMedicationPlanState();
  } catch (error) {
    showMedicationDialogError(error, {
      message: "保存结果尚未确认，当前内容已保留。恢复连接后请载入最新安排，再决定是否重试。",
      recovery: true,
      focus: "recovery",
    });
    return;
  }
  const medication = draft.id
    ? plan.medications.find((candidate) => candidate.id === draft.id)
    : plan.medications.find(
      (candidate) => candidate.name.trim() === draft.name.trim(),
    );
  const revisionAdvanced =
    !draft.id || (medication?.revision ?? 0) > (draft.revision ?? 0);
  if (
    medication &&
    revisionAdvanced &&
    medicationMatchesDraft(medication, draft)
  ) {
    completeMedicationSave(medication, { reconciled: true });
    return;
  }
  showMedicationDialogError(null, {
    message: medication
      ? "保存结果尚未确认，最新安排与当前填写内容不一致。当前内容已保留，请先载入最新安排。"
      : "保存结果尚未确认，最新计划中尚未发现该药物。当前内容已保留，请稍后再次核对。",
    recovery: true,
    focus: "recovery",
  });
}

async function reconcileMedicationArchive(medication, neighbor) {
  let plan;
  try {
    plan = await refreshMedicationPlanState();
  } catch (error) {
    showMedicationDialogError(error, {
      message: "停用结果尚未确认。恢复连接后请载入最新安排，再决定是否重试。",
      recovery: true,
      focus: "recovery",
    });
    return;
  }
  const remainsActive = plan.medications.some(
    (candidate) => candidate.id === medication.id,
  );
  if (!remainsActive) {
    completeMedicationArchive(medication, neighbor, { reconciled: true });
    return;
  }
  showMedicationDialogError(null, {
    message: "停用结果尚未确认，该药物仍在最新计划中。请先载入最新安排，再决定是否重试。",
    recovery: true,
    focus: "recovery",
  });
}

async function reloadMedicationEditor() {
  if (state.medicationEditorBusy || !state.medicationEditorRecovery) return;
  if (
    !window.confirm(
      "载入最新安排可能替换当前未保存的更改，确定继续吗？",
    )
  ) {
    return;
  }
  const {
    kind: recoveryKind,
    medicationId: recoveryMedicationId,
  } = state.medicationEditorRecovery;
  const draft = readMedicationEditorDraft();
  setMedicationEditorBusy(true);
  try {
    const plan = await refreshMedicationPlanState();
    const latest = recoveryMedicationId
      ? plan.medications.find(
        (candidate) => candidate.id === recoveryMedicationId,
      )
      : draft.id
        ? plan.medications.find((candidate) => candidate.id === draft.id)
        : plan.medications.find(
          (candidate) => candidate.name.trim() === draft.name.trim(),
        );
    if (latest) {
      populateMedicationDialog(latest);
      showToast(`${latest.name}的最新安排已载入`);
      window.requestAnimationFrame(() => elements.medicationDialogTitle.focus());
      return;
    }
    if (recoveryMedicationId) {
      clearMedicationFieldValidity();
      clearMedicationDialogFeedback();
      showToast("已核对最新计划，未发现同名药物；当前内容仍未保存");
      window.requestAnimationFrame(() => {
        elements.medicationForm.querySelector('[type="submit"]')?.focus();
      });
      return;
    }
    if (draft.id) {
      state.medicationEditorInitialSignature = "";
      clearMedicationDialogFeedback();
      elements.medicationDialog.close("missing");
      focusPlanAfterLoad({ fallback: elements.addMedicationButton });
      showToast("该药物已不在当前计划中");
      return;
    }
    clearMedicationDialogFeedback();
    showToast("已核对最新计划，未发现同名药物；当前内容仍未保存");
    window.requestAnimationFrame(() => {
      elements.medicationForm.querySelector('[type="submit"]')?.focus();
    });
  } catch (error) {
    showMedicationDialogError(error, {
      message: "暂时无法载入最新安排，当前内容仍已保留。请恢复连接后再试。",
      recovery: true,
      recoveryKind,
      recoveryMedicationId,
      focus: "recovery",
    });
  } finally {
    setMedicationEditorBusy(false);
  }
}

function setMedicationEditorBusy(busy) {
  state.medicationEditorBusy = busy;
  elements.medicationForm.toggleAttribute("aria-busy", busy);
  elements.medicationForm
    .querySelectorAll("button, input, select")
    .forEach((control) => {
      if (busy) {
        control.dataset.medicationEditorWasDisabled = String(control.disabled);
        control.disabled = true;
        return;
      }
      if (control.dataset.medicationEditorWasDisabled === undefined) return;
      control.disabled = control.dataset.medicationEditorWasDisabled === "true";
      delete control.dataset.medicationEditorWasDisabled;
    });
}

async function saveMedication(event) {
  event.preventDefault();
  if (state.medicationEditorBusy) return;
  if (!validateMedicationForm()) return;
  const draft = readMedicationEditorDraft();
  const normalizedName = draft.name.trim();
  const duplicateMedication = state.medications.find(
    (medication) =>
      medication.id !== draft.id && medication.name.trim() === normalizedName,
  );
  if (duplicateMedication) {
    const field = elements.medicationForm.elements.namedItem("name");
    const message = "该药物已存在，请载入现有药物并添加服用时间。";
    field.setCustomValidity(message);
    field.setAttribute("aria-invalid", "true");
    showMedicationDialogError(new Error(message), {
      recovery: true,
      recoveryKind: "duplicate",
      recoveryMedicationId: duplicateMedication.id,
      focus: false,
    });
    field.reportValidity();
    field.focus();
    return;
  }
  const slots = new Map();
  const originalMedication = draft.id
    ? state.medications.find((medication) => medication.id === draft.id)
    : null;
  const originalSlotsById = new Map(
    (originalMedication?.schedules || []).map((schedule) => [
      schedule.id,
      `${schedule.anchor}:${schedule.offsetMinutes}`,
    ]),
  );
  for (const [index, schedule] of draft.schedules.entries()) {
    const slot = `${schedule.anchor}:${schedule.offsetMinutes}`;
    if (slots.has(slot)) {
      const previous = slots.get(slot);
      const preservesLegacyDuplicate = [previous.schedule, schedule].every(
        (candidate) =>
          candidate.id && originalSlotsById.get(candidate.id) === slot,
      );
      if (!preservesLegacyDuplicate) {
        const field = elements.scheduleEditorList
          .querySelectorAll("[data-schedule-editor-row]")
          [index]?.querySelector('[data-schedule-field="anchor"]');
        const message = `第 ${previous.index + 1} 次与第 ${index + 1} 次的服用时间重复，请调整后保存。`;
        field?.setCustomValidity(message);
        field?.setAttribute("aria-invalid", "true");
        showMedicationDialogError(new Error(message), { focus: false });
        field?.reportValidity();
        field?.focus();
        return;
      }
    } else {
      slots.set(slot, { index, schedule });
    }
  }
  const payload = {
    name: normalizedName,
    ...(draft.id ? { revision: draft.revision } : {}),
    timingMode: draft.timingMode,
    maxAutoShiftMinutes: draft.maxAutoShiftMinutes,
    schedules: draft.schedules.map(({ id, dose, instructions, anchor, offsetMinutes }) => ({
      ...(id ? { id } : {}),
      dose: dose.trim(),
      instructions: instructions.trim(),
      anchor,
      offsetMinutes,
    })),
  };
  const requestedDraft = {
    ...draft,
    name: payload.name,
    schedules: payload.schedules,
  };
  clearMedicationDialogFeedback();
  setMedicationEditorBusy(true);
  try {
    const response = await api(draft.id ? `/api/medications/${draft.id}` : "/api/medications", {
      method: draft.id ? "PUT" : "POST",
      ...(draft.id
        ? { headers: { "If-Match": `"${draft.revision}"` } }
        : {}),
      body: JSON.stringify(payload),
    });
    const savedMedication = response.medication || response;
    completeMedicationSave(savedMedication, { payload: response });
  } catch (error) {
    const definitive =
      error instanceof ApiError && error.status >= 400 && error.status < 500;
    if (!definitive) {
      await reconcileMedicationSave(requestedDraft);
    } else if (error.status === 409) {
      showMedicationDialogError(error, {
        message: `${error.message} 当前填写内容已保留，请载入最新安排后再修改。`,
        recovery: true,
        focus: "recovery",
      });
    } else {
      showMedicationDialogError(error);
    }
  } finally {
    setMedicationEditorBusy(false);
  }
}

async function archiveMedication() {
  if (state.medicationEditorBusy) return;
  const id = Number(elements.medicationForm.elements.namedItem("id").value);
  const revision = Number(
    elements.medicationForm.elements.namedItem("revision").value,
  );
  const medication = state.medications.find((candidate) => candidate.id === id);
  if (!medication || !Number.isInteger(revision) || revision < 1) return;
  if (!window.confirm(`确定停用“${medication.name}”及其 ${medication.schedules.length} 条每日安排吗？既往记录不会改变。`)) {
    return;
  }
  setMedicationEditorBusy(true);
  const medicationIndex = state.medications.findIndex((candidate) => candidate.id === id);
  const neighbor =
    state.medications[medicationIndex + 1] || state.medications[medicationIndex - 1] || null;
  clearMedicationDialogFeedback();
  try {
    const response = await api(`/api/medications/${id}`, {
      method: "DELETE",
      headers: { "If-Match": `"${revision}"` },
    });
    completeMedicationArchive(medication, neighbor, { payload: response });
  } catch (error) {
    const definitive =
      error instanceof ApiError && error.status >= 400 && error.status < 500;
    if (!definitive) {
      await reconcileMedicationArchive(medication, neighbor);
    } else if (error.status === 409) {
      showMedicationDialogError(error, {
        message: `${error.message} 请载入最新安排后再操作。`,
        recovery: true,
        focus: "recovery",
      });
    } else {
      showMedicationDialogError(error);
    }
  } finally {
    setMedicationEditorBusy(false);
  }
}

async function switchView(view, { forceReload = false, skipLoad = false } = {}) {
  if (!viewOrder.includes(view)) return;
  if (state.dayMutation && view !== state.view) return;
  const previousView = state.view;
  if (view === previousView && !forceReload) {
    updateNavIndicator();
    return;
  }

  state.viewAbortController?.abort();
  if (view !== "today") {
    cancelPendingDateNavigation({ abort: false });
    cancelDateTransition();
  }
  const controller = new AbortController();
  state.viewAbortController = controller;
  const viewToken = ++state.viewLoadToken;
  state.view = view;

  const commitActiveView = () => {
    for (const section of document.querySelectorAll(".app-view")) {
      const active = section.dataset.view === view;
      section.hidden = !active;
      section.classList.toggle("is-active", active);
    }
    for (const tab of document.querySelectorAll(".nav-tab")) {
      const active = tab.dataset.viewTarget === view;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    }
    updateNavIndicator();
    if (view !== previousView) window.scrollTo({ top: 0, behavior: "auto" });
  };

  if (view !== previousView) {
    const direction = viewOrder.indexOf(view) - viewOrder.indexOf(previousView);
    runPageViewTransition(
      direction,
      commitActiveView,
      () => playViewTransition(view, direction),
    );
  } else {
    commitActiveView();
  }
  const loadOptions = { signal: controller.signal, viewToken };
  if (!skipLoad) {
    if (view === "today") await loadDay(loadOptions);
    if (view === "history") await loadHistory(loadOptions);
    if (view === "plan") await loadPlan(loadOptions);
  }
}

function selectDate(date, { animate = true } = {}) {
  if (state.dayMutation || state.view !== "today") return;
  if (state.pendingDateNavigation?.target === date) return;

  activePageViewTransition?.skipTransition();
  cancelDateTransition();
  if (date === state.selectedDate) {
    cancelPendingDateNavigation();
    return;
  }

  state.viewAbortController?.abort();
  state.viewAbortController = new AbortController();
  const navigation = {
    id: ++dateNavigationSequence,
    target: date,
    direction: date < state.selectedDate ? -1 : 1,
    animate,
  };
  state.pendingDateNavigation = navigation;
  setDateNavigationPending(true);
  loadDay({
    signal: state.viewAbortController.signal,
    viewToken: state.viewLoadToken,
    requestedDate: date,
  });
}

function refreshTodayBoundary() {
  if (state.dayMutation) return false;
  const nextTodayKey = localDateKey(new Date());
  if (nextTodayKey === state.todayKey) return false;
  const previousTodayKey = state.todayKey;
  const followingToday =
    !state.pendingDateNavigation &&
    state.selectedDate === previousTodayKey;
  state.todayKey = nextTodayKey;

  if (!followingToday) {
    if (
      state.view === "today" &&
      !state.pendingDateNavigation &&
      state.day
    ) {
      renderToday();
    }
    return false;
  }

  if (elements.crossDayDialog.open && !state.pendingScheduleSave?.saving) {
    closeCrossDayConfirmation();
  }
  if (state.view === "today") {
    selectDate(nextTodayKey);
  } else {
    cancelPendingDateNavigation();
    cancelDateTransition();
    state.selectedDate = nextTodayKey;
    state.contextFormDirty = false;
    state.contextFormRevision += 1;
  }
  return true;
}

function keyboardFocusRequest(event, surface) {
  return event.detail === 0 ? { keyboard: true, surface } : null;
}

async function returnToToday() {
  if (state.dayMutation) return;
  const today = localDateKey(new Date());
  state.todayKey = today;
  if (state.view === "today") {
    selectDate(today);
    return;
  }

  cancelDateTransition();
  const sourceView = state.view;
  if (state.selectedDate === today && state.day?.date === today) {
    renderToday();
    await switchView("today", { skipLoad: true });
    if (state.view === "today") announceSelectedDate();
    return;
  }

  state.viewAbortController?.abort();
  const controller = new AbortController();
  state.viewAbortController = controller;
  clearError();
  try {
    const day = await api(`/api/day?date=${encodeURIComponent(today)}`, {
      signal: controller.signal,
    });
    if (
      controller !== state.viewAbortController ||
      state.view !== sourceView ||
      state.dayMutation
    ) {
      return;
    }
    const currentToday = localDateKey(new Date());
    if (today !== currentToday) {
      state.todayKey = currentToday;
      return returnToToday();
    }
    reconcileIntakeActions(day, today);
    state.dayLoadToken += 1;
    state.selectedDate = today;
    state.contextFormDirty = false;
    state.contextFormRevision += 1;
    state.day = day;
    renderToday();
    await switchView("today", { skipLoad: true });
    if (state.view === "today") announceSelectedDate();
  } catch (error) {
    if (isAbortError(error)) return;
    showError(error);
  }
}

function bindEvents() {
  bindAnimatedDetails(elements.contextDetails);
  bindAnimatedDetails(elements.timelineDetails);

  document.addEventListener("click", (event) => {
    const viewButton = event.target.closest("[data-view-target]");
    if (!viewButton) return;
    if (viewButton === elements.brandButton) {
      playMotionClass(elements.brandButton, "is-brand-activating", 280);
      returnToToday();
      return;
    }
    switchView(viewButton.dataset.viewTarget);
  });

  elements.navTabs.addEventListener("keydown", (event) => {
    if (!event.target.matches('[role="tab"]')) return;
    const tabs = Array.from(elements.navTabs.querySelectorAll('[role="tab"]'));
    const currentIndex = tabs.indexOf(event.target);
    let nextIndex = null;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextTab = tabs[nextIndex];
    nextTab.focus();
    switchView(nextTab.dataset.viewTarget);
  });

  elements.timeline.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-intake-retry-id]");
    if (retry) {
      toggleIntake(
        Number(retry.dataset.intakeRetryId),
        null,
        keyboardFocusRequest(event, "timeline"),
        retry.dataset.intakeRoutineDate || state.selectedDate,
      );
      return;
    }
    const button = event.target.closest("[data-intake-id]");
    if (button) {
      toggleIntake(
        Number(button.dataset.intakeId),
        null,
        keyboardFocusRequest(event, "timeline"),
        button.dataset.intakeRoutineDate || state.selectedDate,
      );
    }
  });

  elements.focusMedicationList.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-intake-retry-id]");
    if (retry) {
      toggleIntake(
        Number(retry.dataset.intakeRetryId),
        null,
        keyboardFocusRequest(event, "focus"),
        retry.dataset.intakeRoutineDate || state.selectedDate,
      );
      return;
    }
    const button = event.target.closest("[data-focus-intake-id]");
    if (button) {
      toggleIntake(
        Number(button.dataset.focusIntakeId),
        null,
        keyboardFocusRequest(event, "focus"),
        button.dataset.intakeRoutineDate || state.selectedDate,
      );
    }
  });

  elements.intakeFeedbackList.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-intake-retry-id]");
    if (retry) {
      toggleIntake(
        Number(retry.dataset.intakeRetryId),
        null,
        keyboardFocusRequest(event, "feedback"),
        retry.dataset.intakeRoutineDate || state.selectedDate,
      );
      return;
    }
    const undo = event.target.closest("[data-intake-undo-id]");
    if (undo) {
      toggleIntake(
        Number(undo.dataset.intakeUndoId),
        "undo",
        keyboardFocusRequest(event, "feedback"),
        undo.dataset.intakeRoutineDate || state.selectedDate,
      );
    }
  });

  elements.wakeButton.addEventListener("click", checkInWake);
  elements.adjustScheduleButton.addEventListener("click", openScheduleAdjustment);

  elements.planList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-manage-medication-id]");
    if (!button) return;
    const medication = state.medications.find(
      (candidate) => candidate.id === Number(button.dataset.manageMedicationId),
    );
    if (medication) openMedicationDialog(medication);
  });

  elements.saveContextButton.addEventListener("click", requestContextSave);
  elements.contextForm.addEventListener("submit", (event) => {
    event.preventDefault();
    requestContextSave();
  });
  elements.contextForm.addEventListener("input", () => {
    state.contextFormDirty = true;
    state.contextFormRevision += 1;
    renderContextTimePreview();
  });
  elements.previousDayButton.addEventListener("click", () => {
    const baseDate = state.pendingDateNavigation?.target || state.selectedDate;
    selectDate(shiftDate(baseDate, -1));
  });
  elements.nextDayButton.addEventListener("click", () => {
    const baseDate = state.pendingDateNavigation?.target || state.selectedDate;
    selectDate(shiftDate(baseDate, 1));
  });
  elements.returnTodayButton.addEventListener("click", () => {
    selectDate(localDateKey(new Date()));
  });

  elements.savePreferencesButton.addEventListener("click", requestPreferencesSave);
  elements.preferencesForm.addEventListener("submit", (event) => {
    event.preventDefault();
    requestPreferencesSave();
  });
  elements.preferencesForm.addEventListener("input", () => {
    state.preferencesFormDirty = true;
    state.preferencesFormRevision += 1;
    renderPreferencesTimePreview();
  });
  elements.addMedicationButton.addEventListener("click", () => openMedicationDialog());
  elements.medicationForm.addEventListener("submit", saveMedication);
  elements.medicationForm.addEventListener("invalid", (event) => {
    event.target.setAttribute("aria-invalid", "true");
  }, true);
  elements.medicationForm.addEventListener("input", (event) => {
    clearMedicationValidationFeedback(event.target);
    if (event.target.matches("[data-code-point-max]")) {
      validateMedicationTextField(event.target);
      return;
    }
    event.target.setCustomValidity?.("");
    event.target.removeAttribute?.("aria-invalid");
  });
  elements.timingModeInputs.forEach((input) => {
    input.addEventListener("change", () => {
      syncTimingModeControls();
      clearMedicationValidationFeedback(input);
    });
  });
  elements.addScheduleButton.addEventListener("click", addScheduleEditorRow);
  elements.scheduleEditorList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-schedule-index]");
    if (!button) return;
    removeScheduleEditorRow(Number(button.dataset.removeScheduleIndex));
  });
  elements.scheduleEditorList.addEventListener("change", (event) => {
    if (
      !event.target.matches(
        '[data-schedule-field="anchor"], [data-schedule-field="relation"], [data-schedule-field="minutes"]',
      )
    ) {
      return;
    }
    const row = event.target.closest("[data-schedule-editor-row]");
    if (!row) return;
    clearMedicationValidationFeedback(event.target);
    event.target.setCustomValidity("");
    event.target.removeAttribute("aria-invalid");
    if (event.target.matches('[data-schedule-field="relation"]')) {
      syncScheduleMinutesControl(row);
    }
    updateScheduleRemoveLabel(row);
  });
  elements.scheduleEditorList.addEventListener("input", (event) => {
    if (!event.target.matches('[data-schedule-field="minutes"]')) return;
    clearMedicationValidationFeedback(event.target);
    event.target.setCustomValidity("");
    event.target.removeAttribute("aria-invalid");
    const row = event.target.closest("[data-schedule-editor-row]");
    if (row) updateScheduleRemoveLabel(row);
  });
  elements.archiveMedicationButton.addEventListener("click", archiveMedication);
  elements.reloadMedicationButton.addEventListener("click", reloadMedicationEditor);
  elements.closeMedicationDialog.addEventListener("click", requestCloseMedicationDialog);
  elements.cancelMedicationButton.addEventListener("click", requestCloseMedicationDialog);
  elements.medicationDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    requestCloseMedicationDialog();
  });
  elements.medicationDialog.addEventListener("click", (event) => {
    if (event.target === elements.medicationDialog) requestCloseMedicationDialog();
  });
  elements.medicationDialog.addEventListener("keydown", trapDialogFocus);

  elements.cancelCrossDayButton.addEventListener("click", closeCrossDayConfirmation);
  elements.confirmCrossDayButton.addEventListener("click", () => {
    if (state.pendingScheduleSave) commitScheduleSave(state.pendingScheduleSave);
  });
  elements.crossDayDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeCrossDayConfirmation();
  });
  elements.crossDayDialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeCrossDayConfirmation();
      return;
    }
    trapDialogFocus(event);
  });
  elements.crossDayDialog.addEventListener("click", (event) => {
    if (event.target === elements.crossDayDialog) closeCrossDayConfirmation();
  });
  elements.crossDayForm.addEventListener("submit", (event) => event.preventDefault());

  elements.retryButton.addEventListener("click", () =>
    switchView(state.view, { forceReload: true }),
  );

  elements.lockAccessButton.addEventListener("click", async () => {
    elements.lockAccessButton.disabled = true;
    try {
      await api("/api/access", { method: "DELETE" });
      window.location.replace("/");
    } catch (error) {
      elements.lockAccessButton.disabled = false;
      showError(error);
    }
  });

  let resizeFrame = 0;
  window.addEventListener("resize", () => {
    window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(() => {
      updateNavIndicator({ instant: true });
    });
  });
}

async function initialize() {
  bindEvents();
  updateNavIndicator({ instant: true });
  state.viewAbortController = new AbortController();
  const accessStatePromise = api("/api/access")
    .then((access) => {
      elements.lockAccessButton.classList.toggle("is-visible", access.required);
      elements.lockAccessButton.setAttribute("aria-hidden", String(!access.required));
      elements.lockAccessButton.tabIndex = access.required ? 0 : -1;
    })
    .catch(() => {});
  await loadDay({
    signal: state.viewAbortController.signal,
    viewToken: state.viewLoadToken,
  });
  await accessStatePromise;
  window.setInterval(() => {
    if (refreshTodayBoundary()) return;
    if (
      state.view === "today" &&
      !state.pendingDateNavigation &&
      hasReadyDay()
    ) {
      const signature = intakeSurfaceStateSignature();
      if (signature !== state.intakeSurfaceSignature) {
        renderIntakeSurfaces({ timeDriven: true });
      } else {
        refreshLiveIntakeLabels();
      }
    }
  }, 30_000);
}

initialize();
