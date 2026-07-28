"use strict";

const ACCESS_REQUEST_TIMEOUT_MS = 10_000;
const isDemoAccess = /^\/demo(?:\/|\.html)?$/.test(window.location.pathname);
const accessEndpoint = isDemoAccess ? "/api/demo-access" : "/api/access";
const accessDestination = isDemoAccess ? "/demo" : "/";
const form = document.querySelector("#accessForm");
const phraseInput = document.querySelector("#accessPhrase");
const revealButton = document.querySelector("#accessRevealButton");
const submitButton = document.querySelector("#accessSubmit");
const submitLabel = document.querySelector("#accessSubmitLabel");
const errorMessage = document.querySelector("#accessError");
const statusMessage = document.querySelector("#accessStatus");
const accessKicker = document.querySelector("#accessKicker");
const accessTitle = document.querySelector("#accessTitle");

const defaultSubmitLabel = isDemoAccess ? "进入演示" : "进入药时";

if (isDemoAccess) {
  document.title = "互动演示 · 药时";
  accessKicker.textContent = "演示访问";
  accessTitle.textContent = "互动演示";
  submitLabel.textContent = defaultSubmitLabel;
}

function setError(message = "") {
  errorMessage.textContent = message;
  phraseInput.setAttribute("aria-invalid", message ? "true" : "false");
}

function setBusy(busy) {
  form.setAttribute("aria-busy", String(busy));
  phraseInput.readOnly = busy;
  revealButton.disabled = busy;
  submitButton.setAttribute("aria-disabled", String(busy));
  submitLabel.textContent = busy ? "正在验证" : defaultSubmitLabel;
  statusMessage.textContent = busy ? "正在验证访问口令" : "";
}

async function responsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : null;
}

async function checkAccessState() {
  try {
    const response = await fetch(accessEndpoint, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) return;
    const payload = await responsePayload(response);
    if (!payload?.required || payload?.authenticated) {
      window.location.replace(accessDestination);
    }
  } catch (_error) {
    // Submission below provides the actionable network error.
  }
}

revealButton.addEventListener("click", () => {
  const reveal = phraseInput.type === "password";
  phraseInput.type = reveal ? "text" : "password";
  revealButton.textContent = reveal ? "隐藏" : "显示";
  revealButton.setAttribute("aria-label", reveal ? "隐藏访问口令" : "显示访问口令");
  revealButton.setAttribute("aria-pressed", String(reveal));
  phraseInput.focus();
});

phraseInput.addEventListener("input", () => setError());

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (form.getAttribute("aria-busy") === "true") return;
  const phrase = phraseInput.value.trim();
  if (!phrase) {
    setError("请输入访问口令");
    phraseInput.focus();
    return;
  }

  setError();
  setBusy(true);
  let entering = false;
  let shouldRefocus = false;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    ACCESS_REQUEST_TIMEOUT_MS,
  );
  try {
    const response = await fetch(accessEndpoint, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ phrase }),
      signal: controller.signal,
    });
    const payload = await responsePayload(response);
    if (!response.ok) {
      setError(payload?.error || "暂时无法验证，请稍后重试");
      shouldRefocus = true;
      return;
    }
    entering = true;
    submitLabel.textContent = "正在进入";
    window.location.replace(accessDestination);
  } catch (error) {
    setError(
      error?.name === "AbortError"
        ? "验证超时，请稍后重试"
        : "暂时无法验证，请稍后重试",
    );
    shouldRefocus = true;
  } finally {
    window.clearTimeout(timeoutId);
    if (!entering && !document.hidden) {
      setBusy(false);
      if (shouldRefocus) {
        phraseInput.focus();
        phraseInput.select();
      }
    }
  }
});

checkAccessState();
