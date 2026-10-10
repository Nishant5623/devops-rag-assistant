const form = document.getElementById("form");
const input = document.getElementById("input");
const chat = document.getElementById("chat");
const welcome = document.getElementById("welcome");
const waking = document.getElementById("waking");

const ASK_TIMEOUT = 90000;
const ASK_BUDGET = 180000;
const READY_TIMEOUT = 15000;
const READY_POLL = 2500;

let serverReady = false;
let wakingShownAt = null;
let wakingTimer = null;

// --- Example prompt chips -------------------------------------------------
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const question = (chip.dataset.q || "").trim();
    if (question) askQuestion(question);
  });
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  askQuestion(question);
});

// --- Asking (with Render free-tier cold-start retries) --------------------
async function askQuestion(question) {
  addBubble("user", question);
  if (welcome) welcome.remove();
  input.value = "";
  input.focus();

  const typing = addTyping();
  const startedAt = Date.now();

  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const resp = await fetch("/api/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, k: 3 }),
        signal: timeoutSignal(ASK_TIMEOUT),
      });

      // 502/503/504 are the signatures of an instance that is still waking
      // up (or being restarted). Retry with a friendly status update.
      if (resp.status === 502 || resp.status === 503 || resp.status === 504) {
        typing.setStatus(statusMessage(startedAt));
        await sleep(3000);
        continue;
      }

      if (!resp.ok) {
        typing.remove();
        hideWaking();
        let message = `Request failed (${resp.status})`;
        try {
          const err = await resp.json();
          if (err.detail) {
            message = Array.isArray(err.detail)
              ? err.detail.map((d) => d.msg).join("; ")
              : String(err.detail);
          }
        } catch (_) {}
        addBubble("bot", message);
        return;
      }

      const data = await resp.json();
      typing.remove();
      serverReady = true;
      if (wakingShownAt !== null) flashReady();
      else hideWaking();
      addBubble("bot", data.answer, data.sources || [], {
        notFound: data.found === false,
      });
      return;
    } catch (err) {
      const timedOut = err && err.name === "AbortError";
      const network =
        err instanceof TypeError ||
        (err && err.message && /fetch|network|failed/i.test(err.message));
      if (timedOut || network) {
        if (Date.now() - startedAt > ASK_BUDGET) {
          typing.remove();
          hideWaking();
          addBubble(
            "bot",
            "The free instance is still waking up. Please refresh the page and try again in a moment."
          );
          return;
        }
        typing.setStatus(statusMessage(startedAt));
        await sleep(3000);
        continue;
      }
      typing.remove();
      hideWaking();
      addBubble("bot", "Something went wrong: " + (err && err.message ? err.message : err));
      return;
    }
  }

  typing.remove();
  hideWaking();
  addBubble(
    "bot",
    "Couldn't reach the server yet - the free instance may still be starting. Please try again in a moment."
  );
}

function statusMessage(startedAt) {
  const s = Math.round((Date.now() - startedAt) / 1000);
  return `Still waking up the free instance\u2026 ${s}s elapsed. This can take up to ~60s on Render's free tier.`;
}

// --- Readiness probe (started on load so wake-up begins immediately) ------
async function watchServer() {
  while (!serverReady) {
    if (await probeReady()) {
      serverReady = true;
      if (wakingShownAt !== null) flashReady();
      return;
    }
    showWaking();
    await sleep(READY_POLL);
  }
}

async function probeReady() {
  try {
    const resp = await fetch("/api/v1/ready", { signal: timeoutSignal(READY_TIMEOUT) });
    return resp.ok;
  } catch (_) {
    return false;
  }
}

// --- Waking-up status bar -------------------------------------------------
function showWaking() {
  if (!waking) return;
  if (wakingShownAt === null) wakingShownAt = Date.now();
  waking.hidden = false;
  waking.classList.remove("ready");
  if (wakingTimer) clearInterval(wakingTimer);
  const update = () => {
    const s = Math.round((Date.now() - wakingShownAt) / 1000);
    waking.textContent = `Waking up the service\u2026 ${s}s elapsed. Render's free tier sleeps after 15 min idle; first load can take up to ~60s.`;
  };
  update();
  wakingTimer = setInterval(update, 1000);
}

function hideWaking() {
  if (wakingTimer) {
    clearInterval(wakingTimer);
    wakingTimer = null;
  }
  wakingShownAt = null;
  if (waking) waking.hidden = true;
}

function flashReady() {
  if (wakingTimer) {
    clearInterval(wakingTimer);
    wakingTimer = null;
  }
  if (!waking) return;
  wakingShownAt = null;
  waking.classList.add("ready");
  waking.textContent = "Ready \u2014 the service is awake.";
  waking.hidden = false;
  setTimeout(() => {
    waking.hidden = true;
  }, 2000);
}

function timeoutSignal(ms) {
  if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
    return AbortSignal.timeout(ms);
  }
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), ms);
  return ctrl.signal;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// --- Rendering ------------------------------------------------------------
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Minimal markdown-style renderer: preserves newlines, renders bold / italic /
// inline code and fenced code blocks. Deliberately kept tiny (no dependencies).
function renderMd(text) {
  const esc = escapeHtml(text);
  const withCode = esc
    .split(/```/)
    .map((part, i) =>
      i % 2 === 1
        ? "<pre class=\"code\">" + part.replace(/^\w*\n/, "") + "</pre>"
        : part
    )
    .join("");
  const inline = withCode
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  return inline.replace(/\n/g, "<br>");
}

function addBubble(role, text, sources, opts) {
  opts = opts || {};
  const div = document.createElement("div");
  div.className = "bubble " + role + (opts.notFound ? " notfound" : "");

  if (role === "bot") {
    const body = document.createElement("div");
    body.className = "body";
    body.innerHTML = renderMd(text);
    div.appendChild(body);
  } else {
    div.textContent = text;
  }

  if (sources && sources.length) {
    const src = document.createElement("div");
    src.className = "sources";
    const title = document.createElement("div");
    title.className = "sources-title";
    title.textContent = "Sources (chunks used to answer):";
    src.appendChild(title);
    sources.forEach((s, i) => {
      const det = document.createElement("details");
      det.className = "source";
      const sum = document.createElement("summary");
      const distance = s.distance != null ? s.distance.toFixed(3) : "";
      sum.textContent = `${s.source} \u00b7 chunk ${i + 1}${distance ? ` \u00b7 distance ${distance}` : ""}`;
      det.appendChild(sum);
      if (s.text) {
        const pre = document.createElement("pre");
        pre.className = "source-text";
        pre.textContent = s.text;
        det.appendChild(pre);
      }
      src.appendChild(det);
    });
    div.appendChild(src);
  }

  chat.appendChild(div);
  scrollToBottom();
}

function addTyping() {
  const t = document.createElement("div");
  t.className = "typing";
  const dots = document.createElement("span");
  dots.className = "dot";
  dots.innerHTML = "<span></span><span></span><span></span>";
  const status = document.createElement("span");
  status.className = "status";
  t.append(dots, status);
  chat.appendChild(t);
  scrollToBottom();
  return {
    setStatus: (m) => {
      status.textContent = m;
      scrollToBottom();
    },
    remove: () => t.remove(),
  };
}

function scrollToBottom() {
  chat.scrollTop = chat.scrollHeight;
}

// Kick off the readiness probe as soon as the page loads so a cold-started
// instance starts waking before the visitor finishes typing.
watchServer();
