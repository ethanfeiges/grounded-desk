const NODES = [
  "route",
  "extract",
  "playbook",
  "gather",
  "lookup_order",
  "verify",
  "approve",
  "draft",
];

const AFTER = {
  route: ["extract", "playbook"],
  extract: ["gather"],
  playbook: ["gather"],
  gather: [],
  lookup_order: ["verify"],
  verify: ["approve"],
  approve: ["draft"],
};

const state = {
  ticketId: null,
  tickets: [],
  lastSettings: { backend: "demo", skip_approval: false },
};

const $ = (id) => document.getElementById(id);

async function boot() {
  const [health, catalog] = await Promise.all([
    fetch("/api/health").then((r) => r.json()),
    fetch("/api/tickets").then((r) => r.json()),
  ]);
  $("key-openai").textContent = health.openai ? "key set" : "no key";
  $("key-cursor").textContent = health.cursor ? "key set" : "no key";
  state.tickets = catalog.tickets;
  renderTickets();
  if (catalog.tickets[0]) selectTicket(catalog.tickets[0].ticket_id);
  $("run-form").addEventListener("submit", onRun);
  $("approve-btn").addEventListener("click", () => resume(true));
  $("reject-btn").addEventListener("click", () => resume(false));
}

function renderTickets() {
  const box = $("ticket-list");
  box.replaceChildren(
    ...state.tickets.map((ticket) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ticket" + (ticket.ticket_id === state.ticketId ? " active" : "");
      btn.innerHTML = `<strong>${ticket.ticket_id}</strong><span>${ticket.blurb}</span><small>${ticket.path}</small>`;
      btn.addEventListener("click", () => selectTicket(ticket.ticket_id));
      return btn;
    }),
  );
}

async function selectTicket(ticketId) {
  state.ticketId = ticketId;
  $("thread_id").value = `${ticketId}-${Math.random().toString(16).slice(2, 6)}`;
  renderTickets();
  const detail = await fetch(`/api/tickets/${ticketId}`).then((r) => r.json());
  $("email-block").textContent = detail.email;
  $("email-path").textContent = detail.path;
  $("policy-block").textContent = detail.policy;
  $("decoy-block").textContent = detail.decoy;
  resetRunView();
}

function resetRunView() {
  setNodeMarks({});
  $("claims").replaceChildren();
  $("scores").replaceChildren();
  $("draft-text").textContent = "Run a ticket to see the reply.";
  $("meta-thread").textContent = $("thread_id").value || "—";
  $("meta-path").textContent = $("email-path").textContent || "—";
  $("meta-next").textContent = "—";
  $("meta-approved").textContent = "—";
  $("approval").classList.add("hidden");
  $("error").classList.add("hidden");
}

function settings() {
  return {
    backend: $("backend").value,
    condition: $("condition").value,
    thread_id: $("thread_id").value.trim(),
    skip_approval: $("skip_approval").checked,
  };
}

async function onRun(event) {
  event.preventDefault();
  if (!state.ticketId) return;
  resetRunView();
  const body = { ticket_id: state.ticketId, ...settings() };
  state.lastSettings = body;
  setNodeMarks({ route: "running" });
  await consume("/api/run", body);
}

async function resume(approved) {
  const body = {
    thread_id: $("thread_id").value.trim(),
    approved,
    backend: state.lastSettings.backend,
    skip_approval: state.lastSettings.skip_approval,
  };
  setNodeMarks({ approve: "running" }, { keep: true });
  await consume("/api/resume", body);
}

async function consume(url, body) {
  $("run-btn").disabled = true;
  $("error").classList.add("hidden");
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      throw new Error(await res.text());
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop() ?? "";
      for (const block of parts) applySse(block);
    }
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    $("run-btn").disabled = false;
  }
}

function applySse(block) {
  const lines = block.split("\n");
  const event = lines.find((l) => l.startsWith("event: "))?.slice(7);
  const dataLine = lines.filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("");
  if (!event || !dataLine) return;
  const data = JSON.parse(dataLine);
  if (event === "start") {
    $("meta-thread").textContent = data.thread_id;
    return;
  }
  if (event === "node") {
    markNode(data.node, data.update);
    return;
  }
  if (event === "done") {
    renderSnapshot(data);
    return;
  }
  if (event === "error") showError(data.message);
}

function markNode(name, update) {
  const marks = currentMarks();
  marks[name] = "done";
  for (const next of AFTER[name] || []) {
    if (!marks[next]) marks[next] = "running";
  }
  if (name === "verify" && marks.lookup_order !== "done") {
    marks.lookup_order = "skipped";
  }
  setNodeMarks(marks);
  if (update) mergePartial(update);
}

function currentMarks() {
  const marks = {};
  for (const node of NODES) {
    const el = document.querySelector(`[data-node="${node}"]`);
    if (el.classList.contains("done")) marks[node] = "done";
    else if (el.classList.contains("running")) marks[node] = "running";
    else if (el.classList.contains("waiting")) marks[node] = "waiting";
    else if (el.classList.contains("skipped")) marks[node] = "skipped";
  }
  return marks;
}

function setNodeMarks(marks, { keep } = {}) {
  const next = keep ? { ...currentMarks(), ...marks } : marks;
  for (const node of NODES) {
    const el = document.querySelector(`[data-node="${node}"]`);
    el.classList.remove("running", "done", "waiting", "skipped");
    if (next[node]) el.classList.add(next[node]);
  }
}

function mergePartial(update) {
  if (update.path) $("meta-path").textContent = update.path;
  if (update.approved !== undefined) $("meta-approved").textContent = String(update.approved);
  if (update.draft) $("draft-text").textContent = update.draft;
  if (update.claims) renderClaims(update.claims, []);
  if (update.verified) renderClaims(null, update.verified);
  if (update.scores) renderScores(update.scores);
}

function renderSnapshot(snap) {
  const values = snap.values || {};
  $("meta-thread").textContent = snap.thread_id;
  $("meta-path").textContent = values.path || "—";
  $("meta-next").textContent = (snap.next || []).join(", ") || "end";
  $("meta-approved").textContent =
    values.approved === undefined || values.approved === null ? "—" : String(values.approved);
  if (values.draft) $("draft-text").textContent = values.draft;
  renderClaims(values.claims, values.verified);
  renderScores(values.scores || {});
  if (snap.paused) {
    $("approval").classList.remove("hidden");
    setNodeMarks({ approve: "waiting" }, { keep: true });
  } else {
    $("approval").classList.add("hidden");
  }
}

function renderClaims(claims, verified) {
  const rows = verified && verified.length
    ? verified.map((row) => ({
        statement: row.claim?.statement,
        span_id: row.claim?.span_id,
        quote: row.claim?.quote,
        task: row.task,
        status: row.status,
        decoy_match: row.decoy_match,
      }))
    : (claims || []).map((claim) => ({
        statement: claim.statement,
        span_id: claim.span_id,
        quote: claim.quote,
        task: claim.rule_id ? "playbook" : "extract",
        status: "pending",
      }));
  $("claims").replaceChildren(
    ...rows.map((row) => {
      const li = document.createElement("li");
      const stamp =
        row.status === "grounded" ? "ok" : row.status === "ungrounded" ? "bad" : "";
      li.innerHTML = `
        <div class="who">${row.task || "claim"} · ${row.span_id || "?"}
          <span class="stamp ${stamp}">${row.status}${row.decoy_match ? " · decoy" : ""}</span>
        </div>
        <div>${escapeHtml(row.statement || "")}</div>
        <div class="who">“${escapeHtml(row.quote || "")}”</div>`;
      return li;
    }),
  );
}

function renderScores(scores) {
  $("scores").replaceChildren(
    ...Object.entries(scores).map(([key, ok]) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="stamp ${ok ? "ok" : "bad"}">${ok ? "pass" : "fail"}</span> ${key}`;
      return li;
    }),
  );
}

function showError(message) {
  $("error").textContent = message;
  $("error").classList.remove("hidden");
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

boot();
