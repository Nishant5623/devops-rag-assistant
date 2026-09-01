const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const chat = document.getElementById("chat");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = input.value.trim();
  if (!question) return;

  addBubble("user", question);
  input.value = "";
  input.focus();

  const typing = addTyping();

  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, k: 3 }),
    });

    typing.remove();

    if (!resp.ok) {
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
    addBubble("bot", data.answer, data.sources || []);
  } catch (err) {
    typing.remove();
    addBubble("bot", "Network error: " + err.message);
  }
});

function addBubble(role, text, sources) {
  const div = document.createElement("div");
  div.className = "bubble " + role;
  div.textContent = text;

  if (sources && sources.length) {
    const src = document.createElement("div");
    src.className = "sources";
    src.textContent = "Sources:";
    sources.forEach((s) => {
      const line = document.createElement("span");
      line.className = "source";
      const distance = s.distance != null ? s.distance.toFixed(3) : "";
      line.textContent = `${s.source}${distance ? ` — relevance ${distance}` : ""}`;
      src.appendChild(line);
    });
    div.appendChild(src);
  }

  chat.appendChild(div);
  scrollToBottom();
}

function addTyping() {
  const t = document.createElement("div");
  t.className = "typing";
  t.innerHTML = "<span></span><span></span><span></span>";
  chat.appendChild(t);
  scrollToBottom();
  return t;
}

function scrollToBottom() {
  chat.scrollTop = chat.scrollHeight;
}
