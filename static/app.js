"use strict";

/* DevOps Knowledge Assistant — front-end controller.
 *
 * Vanilla JavaScript: no framework, no build step, no dependencies. The page
 * is served under a strict Content-Security-Policy (script-src 'self',
 * style-src 'self'), so all behaviour lives here and every element is built
 * with DOM APIs — no inline handlers, no eval, no inline styles.
 *
 * Responsibilities
 *   * service status pill (GET /health: live, short SHA, index loaded)
 *   * example-prompt chips
 *   * asking questions, with Render-free-tier cold-start retries
 *   * rendering answers, the out-of-scope refusal and cited source chunks
 *   * copy-to-clipboard on answers
 */

(function () {
  const $ = function (id) {
    return document.getElementById(id);
  };

  const form = $("form");
  const input = $("input");
  const sendBtn = $("send");
  const chat = $("chat");
  const welcome = $("welcome");
  const waking = $("waking");
  const statusPill = $("status");
  const statusLabel = $("status-label");
  const inputCount = $("input-count");

  const MAX_QUESTION = 500;
  const MIN_QUESTION = 3;
  const ASK_TIMEOUT = 90000;
  const ASK_BUDGET = 180000;
  const READY_TIMEOUT = 15000;
  const READY_POLL = 2500;
  const RETRY_DELAY = 3000;
  const MAX_ATTEMPTS = 8;

  let serverReady = false;
  let inFlight = false;
  let wakingShownAt = null;
  let wakingTimer = null;

  // --- Service status pill --------------------------------------------------
  // Ties the page to the SHA-verified deploy story: /health reports the live
  // commit, and a 503 (index not loaded) is shown honestly as degraded.
  function setStatus(state, label, title) {
    if (!statusPill) return;
    statusPill.dataset.state = state;
    if (statusLabel) statusLabel.textContent = label;
    statusPill.title = title || label;
  }

  async function refreshHealth() {
    setStatus("checking", "Checking service\u2026");
    let resp;
    try {
      resp = await fetch("/health", {
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: timeoutSignal(READY_TIMEOUT),
      });
    } catch (_) {
      setStatus("down", "unavailable", "The service did not respond to /health.");
      return;
    }

    let body = null;
    try {
      body = await resp.json();
    } catch (_) {
      body = null;
    }

    if (resp.ok && body && body.status === "ok") {
      const sha = typeof body.sha === "string" ? body.sha.slice(0, 7) : "";
      const index = body.index_loaded ? "index loaded" : "index missing";
      const parts = ["live"];
      if (sha) parts.push(sha);
      parts.push(index);
      serverReady = true;
      setStatus(
        "live",
        parts.join(" \u00b7 "),
        "Commit " + (body.sha || "unknown") + " \u00b7 build " + (body.build_time || "unknown")
      );
      return;
    }

    if (resp.status === 503 || (body && body.status === "unavailable")) {
      setStatus("degraded", "degraded \u00b7 index not loaded");
      return;
    }

    setStatus("down", "unavailable", "Unexpected /health response: " + resp.status);
  }

  // --- Example prompt chips -------------------------------------------------
  document.querySelectorAll(".chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      const question = (chip.dataset.q || "").trim();
      if (question) askQuestion(question);
    });
  });

  // --- Composer -------------------------------------------------------------
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    const question = input.value.trim();
    if (question.length < MIN_QUESTION) {
      input.focus();
      return;
    }
    askQuestion(question);
  });

  input.addEventListener("input", updateCount);

  function updateCount() {
    if (!inputCount) return;
    const length = input.value.length;
    if (length === 0) {
      inputCount.hidden = true;
      inputCount.textContent = "";
      inputCount.dataset.warn = "false";
      return;
    }
    inputCount.hidden = false;
    inputCount.textContent = length + "/" + MAX_QUESTION;
    inputCount.dataset.warn = length >= MAX_QUESTION - 20 ? "true" : "false";
  }

  function setBusy(busy) {
    inFlight = busy;
    if (sendBtn) {
      sendBtn.disabled = busy;
      sendBtn.setAttribute("aria-busy", busy ? "true" : "false");
    }
    form.setAttribute("aria-busy", busy ? "true" : "false");
  }

  // --- Asking (with Render free-tier cold-start retries) --------------------
  async function askQuestion(question) {
    if (inFlight) return;
    const text = (question || "").trim();
    if (text.length < MIN_QUESTION) {
      input.focus();
      return;
    }

    setBusy(true);
    addMessage("user", text);
    if (welcome) welcome.remove();
    input.value = "";
    updateCount();
    input.focus();

    const typing = addTyping();
    const startedAt = Date.now();

    try {
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        let resp;
        try {
          resp = await fetch("/api/v1/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ question: text, k: 3 }),
            signal: timeoutSignal(ASK_TIMEOUT),
          });
        } catch (err) {
          // Aborted (timeout) or a network error: a sleeping free instance
          // looks exactly like this. Keep retrying until the time budget.
          if (Date.now() - startedAt > ASK_BUDGET) {
            typing.remove();
            hideWaking();
            addMessage(
              "bot",
              "The instance is still waking up. Please refresh the page and try again in a moment.",
              { error: true }
            );
            return;
          }
          typing.setStatus(statusMessage(startedAt));
          await sleep(RETRY_DELAY);
          continue;
        }

        // 502/503/504 are the signatures of an instance that is still waking
        // up (or being restarted). Retry with a friendly status update.
        if (resp.status === 502 || resp.status === 503 || resp.status === 504) {
          typing.setStatus(statusMessage(startedAt));
          await sleep(RETRY_DELAY);
          continue;
        }

        if (!resp.ok) {
          typing.remove();
          hideWaking();
          let message = "Request failed (" + resp.status + ").";
          try {
            const err = await resp.json();
            if (err.detail) {
              message = Array.isArray(err.detail)
                ? err.detail.map(function (detail) {
                    return detail.msg;
                  }).join("; ")
                : String(err.detail);
            }
          } catch (_) {
            /* keep the generic message */
          }
          addMessage("bot", message, { error: true });
          return;
        }

        const data = await resp.json();
        typing.remove();
        serverReady = true;
        if (wakingShownAt !== null) flashReady();
        else hideWaking();

        if (data.found === false) {
          addMessage("bot", data.answer, { notFound: true });
        } else {
          addMessage("bot", data.answer, { sources: data.sources || [] });
        }
        return;
      }

      typing.remove();
      hideWaking();
      addMessage(
        "bot",
        "Couldn't reach the server yet — the instance may still be starting. Please try again in a moment.",
        { error: true }
      );
    } finally {
      setBusy(false);
    }
  }

  function statusMessage(startedAt) {
    const seconds = Math.round((Date.now() - startedAt) / 1000);
    return (
      "Still waking up the instance\u2026 " +
      seconds +
      "s elapsed. This can take up to ~60s on Render's free tier."
    );
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
      const resp = await fetch("/api/v1/ready", {
        signal: timeoutSignal(READY_TIMEOUT),
      });
      return resp.ok;
    } catch (_) {
      return false;
    }
  }

  // --- Cold-start status bar ------------------------------------------------
  function showWaking() {
    if (!waking) return;
    if (wakingShownAt === null) wakingShownAt = Date.now();
    waking.hidden = false;
    waking.classList.remove("ready");
    if (wakingTimer) clearInterval(wakingTimer);
    const update = function () {
      const seconds = Math.round((Date.now() - wakingShownAt) / 1000);
      waking.textContent =
        "Waking up the service\u2026 " +
        seconds +
        "s elapsed. Render's free tier sleeps after 15 min idle; " +
        "the first load can take up to ~60s.";
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
    waking.textContent = "Ready — the service is awake.";
    waking.hidden = false;
    setTimeout(function () {
      waking.hidden = true;
    }, 2000);
  }

  function timeoutSignal(ms) {
    if (typeof AbortSignal !== "undefined" && AbortSignal.timeout) {
      return AbortSignal.timeout(ms);
    }
    const controller = new AbortController();
    setTimeout(function () {
      controller.abort();
    }, ms);
    return controller.signal;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  // --- Rendering ------------------------------------------------------------
  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Minimal markdown-style renderer: preserves newlines, renders bold / italic /
  // inline code and fenced code blocks. Deliberately kept tiny (no dependencies).
  // Input is HTML-escaped first, so model or note text can never inject markup.
  function renderMd(text) {
    const escaped = escapeHtml(text);
    const withCode = escaped
      .split(/```/)
      .map(function (part, i) {
        return i % 2 === 1
          ? '<pre class="code">' + part.replace(/^\w*\n/, "") + "</pre>"
          : part;
      })
      .join("");
    const inline = withCode
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
    return inline.replace(/\n/g, "<br>");
  }

  function addMessage(role, text, options) {
    const opts = options || {};

    const article = document.createElement("article");
    article.className = "msg msg-" + role;
    if (opts.notFound) article.classList.add("notfound");
    if (opts.error) article.classList.add("error");

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const roleLabel = document.createElement("span");
    roleLabel.className = "msg-role";
    roleLabel.textContent = role === "user" ? "You" : "Assistant";
    const time = document.createElement("time");
    time.className = "msg-time";
    const now = new Date();
    time.dateTime = now.toISOString();
    time.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    meta.append(roleLabel, time);
    article.appendChild(meta);

    const card = document.createElement("div");
    card.className = "msg-card";
    const body = document.createElement("div");
    body.className = "msg-body";
    if (role === "bot") {
      body.innerHTML = renderMd(text);
    } else {
      body.textContent = text;
    }
    card.appendChild(body);
    if (role === "bot" && opts.sources && opts.sources.length) {
      card.appendChild(buildSources(opts.sources));
    }
    article.appendChild(card);

    if (role === "bot" && !opts.error) {
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      actions.appendChild(buildCopyButton(text));
      article.appendChild(actions);
    }

    chat.appendChild(article);
    scrollToBottom();
    return article;
  }

  // Collapsible list of the chunks an answer was built from. <details>/<summary>
  // is keyboard-accessible for free.
  function buildSources(sources) {
    const details = document.createElement("details");
    details.className = "sources";

    const summary = document.createElement("summary");
    summary.className = "sources-summary";
    const label = document.createElement("span");
    label.textContent = "Sources";
    const count = document.createElement("span");
    count.className = "sources-count";
    count.textContent = sources.length + (sources.length === 1 ? " chunk" : " chunks");
    summary.append(label, count);
    details.appendChild(summary);

    const list = document.createElement("ol");
    list.className = "sources-list";
    sources.forEach(function (source, index) {
      const item = document.createElement("li");
      item.className = "source";

      const head = document.createElement("div");
      head.className = "source-head";
      const file = document.createElement("span");
      file.className = "source-file";
      file.textContent = source.source || "unknown";
      const chunk = document.createElement("span");
      chunk.className = "source-chunk";
      chunk.textContent = "chunk " + (index + 1);
      head.append(file, chunk);
      if (typeof source.distance === "number") {
        const distance = document.createElement("span");
        distance.className = "source-distance";
        distance.textContent = "distance " + source.distance.toFixed(3);
        distance.title = "Vector distance — lower means a closer match";
        head.appendChild(distance);
      }
      item.appendChild(head);

      if (source.text) {
        const pre = document.createElement("pre");
        pre.className = "source-text";
        pre.textContent = source.text;
        item.appendChild(pre);
      }
      list.appendChild(item);
    });

    details.appendChild(list);
    return details;
  }

  function buildCopyButton(text) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy-btn";
    button.textContent = "Copy answer";
    button.setAttribute("aria-label", "Copy this answer to the clipboard");
    button.addEventListener("click", function () {
      copyText(text).then(function (ok) {
        button.dataset.copied = ok ? "true" : "false";
        button.textContent = ok ? "Copied" : "Copy failed";
        setTimeout(function () {
          button.dataset.copied = "false";
          button.textContent = "Copy answer";
        }, 1600);
      });
    });
    return button;
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(
        function () {
          return true;
        },
        function () {
          return legacyCopy(text);
        }
      );
    }
    return Promise.resolve(legacyCopy(text));
  }

  function legacyCopy(text) {
    try {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.className = "visually-hidden";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    } catch (_) {
      return false;
    }
  }

  function addTyping() {
    const typing = document.createElement("div");
    typing.className = "typing";
    typing.setAttribute("role", "status");
    const dots = document.createElement("span");
    dots.className = "dot";
    dots.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 3; i++) dots.appendChild(document.createElement("span"));
    const status = document.createElement("span");
    status.className = "status";
    status.textContent = "Searching your notes\u2026";
    typing.append(dots, status);
    chat.appendChild(typing);
    scrollToBottom();
    return {
      setStatus: function (message) {
        status.textContent = message;
        scrollToBottom();
      },
      remove: function () {
        typing.remove();
      },
    };
  }

  function scrollToBottom() {
    chat.scrollTop = chat.scrollHeight;
  }

  // --- Boot -----------------------------------------------------------------
  // Check the deploy status immediately, and re-check when the visitor comes
  // back to a tab that may have been left open while the instance slept.
  refreshHealth();
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refreshHealth();
  });

  // Kick off the readiness probe as soon as the page loads so a cold-started
  // instance starts waking before the visitor finishes typing.
  watchServer();
})();
