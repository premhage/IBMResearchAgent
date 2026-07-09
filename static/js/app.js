/**
 * app.js — ResearchAgent frontend logic
 * Handles: tab navigation, file upload, chat (ReAct), dashboard,
 * gap analysis, contradiction detection, hypothesis generation,
 * citation management, dark/light theme toggle.
 */

"use strict";

// ─────────────────────────────────────────────────────────────────────────────
//  State
// ─────────────────────────────────────────────────────────────────────────────

const state = {
  papers: [],           // KB paper list
  currentCiteStyle: "IEEE",
  theme: "dark",
};

// ─────────────────────────────────────────────────────────────────────────────
//  Utilities
// ─────────────────────────────────────────────────────────────────────────────

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/** Highlight [KB], [WEB], [INFER], [LOW-CONFIDENCE] tags in text */
function highlightTags(text) {
  return escHtml(text)
    .replace(/\[KB\]/g, '<span class="src-tag src-kb">[KB]</span>')
    .replace(/\[WEB\]/g, '<span class="src-tag src-web">[WEB]</span>')
    .replace(/\[INFER\]/g, '<span class="src-tag src-infer">[INFER]</span>')
    .replace(/\[LOW-CONFIDENCE\]/g, '<span class="src-tag" style="background:rgba(248,81,73,0.2);color:#f85149;">[LOW-CONFIDENCE]</span>');
}

function confidenceColor(c) {
  if (c >= 0.7) return "conf-high";
  if (c >= 0.45) return "conf-medium";
  return "conf-low";
}

function toast(msg, type = "info") {
  const id = "t" + Date.now();
  const colors = { info: "#3b82d4", success: "#3fb950", error: "#f85149", warning: "#d29922" };
  const html = `
    <div id="${id}" class="toast align-items-center border-0" role="alert" style="background:#21262d;color:#e6edf3;border-left:3px solid ${colors[type] || colors.info} !important;">
      <div class="d-flex">
        <div class="toast-body" style="font-size:0.82rem;">${escHtml(msg)}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    </div>`;
  $("#toastContainer").insertAdjacentHTML("beforeend", html);
  const el = document.getElementById(id);
  new bootstrap.Toast(el, { delay: 3500 }).show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

async function apiFetch(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Tab navigation
// ─────────────────────────────────────────────────────────────────────────────

function initTabs() {
  $$(".ra-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      $$(".ra-tab").forEach(t => t.classList.remove("active"));
      $$(".ra-tab-content").forEach(s => s.classList.remove("active"));
      btn.classList.add("active");
      const section = document.getElementById("tab-" + btn.dataset.tab);
      if (section) section.classList.add("active");

      // Lazy-load dashboard on first visit
      if (btn.dataset.tab === "dashboard") loadDashboard();
      if (btn.dataset.tab === "papers")    renderCitationCards();
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  System status
// ─────────────────────────────────────────────────────────────────────────────

async function checkStatus() {
  try {
    const s = await apiFetch("/api/status");
    const dot   = $("#statusDot");
    const label = $("#statusLabel");

    if (s.watsonx && s.exa) {
      dot.className = "ra-status-dot ok";
      label.textContent = "All systems online";
    } else if (s.watsonx || s.exa) {
      dot.className = "ra-status-dot warn";
      label.textContent = s.watsonx ? "watsonx ✓  Exa ✗" : "watsonx ✗  Exa ✓";
    } else {
      dot.className = "ra-status-dot warn";
      label.textContent = "Mock mode (no API keys)";
    }
  } catch (e) {
    $("#statusDot").className = "ra-status-dot err";
    $("#statusLabel").textContent = "Server error";
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Knowledge Base (sidebar + shared state)
// ─────────────────────────────────────────────────────────────────────────────

async function loadKB() {
  try {
    const data = await apiFetch("/api/papers");
    state.papers = data.papers || [];
    renderKBSidebar();
  } catch (e) {
    console.error("KB load failed", e);
  }
}

function renderKBSidebar() {
  const el = $("#kbPapersList");
  if (!state.papers.length) {
    el.innerHTML = '<p class="text-secondary small">No papers yet.</p>';
    return;
  }
  el.innerHTML = state.papers.map(p => `
    <div class="ra-kb-item">
      <div class="overflow-hidden">
        <div class="title" title="${escHtml(p.title)}">${escHtml(p.title)}</div>
        <div class="meta">${escHtml(p.authors.substring(0, 40))} · ${escHtml(p.year)}</div>
        ${p.is_test_case ? '<span class="test-case-badge">test-case</span>' : ''}
      </div>
      <button class="btn btn-sm p-0 text-danger" style="min-width:20px" onclick="removePaper('${escHtml(p.sha256)}')" title="Remove">
        <i class="bi bi-x-circle-fill" style="font-size:0.9rem;"></i>
      </button>
    </div>
  `).join("");
}

async function removePaper(sha) {
  try {
    await apiFetch(`/api/papers/${sha}`, { method: "DELETE" });
    toast("Paper removed", "success");
    await loadKB();
    renderCitationCards();
  } catch (e) {
    toast("Remove failed: " + e.message, "error");
  }
}
window.removePaper = removePaper;

// ─────────────────────────────────────────────────────────────────────────────
//  File Upload
// ─────────────────────────────────────────────────────────────────────────────

function initUpload() {
  const input   = $("#fileInput");
  const dropzone = $("#dropzone");
  const statusEl = $("#uploadStatus");

  input.addEventListener("change", () => handleFiles(input.files));

  dropzone.addEventListener("dragover", e => { e.preventDefault(); dropzone.classList.add("dragging"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragging"));
  dropzone.addEventListener("drop", e => {
    e.preventDefault();
    dropzone.classList.remove("dragging");
    handleFiles(e.dataTransfer.files);
  });

  async function handleFiles(files) {
    if (!files || !files.length) return;
    const isTest = $("#isTestCase").checked;
    statusEl.innerHTML = '<div class="ra-spinner mx-auto my-2" style="width:24px;height:24px;border-width:2px;"></div>';

    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    if (isTest) fd.append("is_test_case", "true");

    try {
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await res.json();
      const ok = data.results.filter(r => r.status === "ingested").length;
      const fail = data.results.filter(r => r.status !== "ingested").length;
      statusEl.innerHTML = `
        <div class="small mt-1">
          <span class="text-success"><i class="bi bi-check-circle-fill"></i> ${ok} ingested</span>
          ${fail ? `<span class="text-danger ms-2"><i class="bi bi-x-circle-fill"></i> ${fail} failed</span>` : ""}
        </div>`;
      toast(`${ok} paper(s) ingested`, "success");
      await loadKB();
      renderCitationCards();
    } catch (e) {
      statusEl.innerHTML = `<p class="text-danger small mt-1">${escHtml(e.message)}</p>`;
      toast("Upload failed: " + e.message, "error");
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Chat
// ─────────────────────────────────────────────────────────────────────────────

function initChat() {
  const input  = $("#chatInput");
  const sendBtn = $("#sendBtn");
  const messages = $("#chatMessages");

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  $$(".quick-q").forEach(btn =>
    btn.addEventListener("click", () => { input.value = btn.dataset.q; sendMessage(); })
  );

  async function sendMessage() {
    const query = input.value.trim();
    if (!query) return;
    input.value = "";
    input.style.height = "auto";
    sendBtn.disabled = true;
    appendUserBubble(query);
    const typingEl = appendTyping();
    const useWeb = $("#useWeb").checked;
    try {
      const data = await apiFetch("/api/chat", {
        method: "POST",
        body: JSON.stringify({ query, use_web: useWeb }),
      });
      typingEl.remove();
      appendAgentCard(data);
    } catch (e) {
      typingEl.remove();
      appendErrorCard(e.message);
    } finally {
      sendBtn.disabled = false;
      scrollToBottom();
    }
  }

  function nowTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function appendUserBubble(text) {
    const row = document.createElement("div");
    row.className = "msg-row user";
    row.innerHTML = `
      <div class="ra-bubble-user">${highlightTags(text)}</div>
      <span class="msg-timestamp">${nowTime()}</span>`;
    messages.appendChild(row);
    scrollToBottom();
  }

  function appendTyping() {
    const row = document.createElement("div");
    row.className = "msg-row agent";
    row.innerHTML = `<div class="ra-typing"><span></span><span></span><span></span></div>`;
    messages.appendChild(row);
    scrollToBottom();
    return row;
  }

  function appendAgentCard(data) {
    const steps   = data.steps || [];
    const cites   = data.citations || [];
    const answer  = data.final_answer || "No answer generated.";
    const traceId = "trace-" + Date.now();

    const row = document.createElement("div");
    row.className = "msg-row agent";
    row.innerHTML = `
      <div class="ra-agent-card">
        <div class="ra-agent-card-header">
          <div class="d-flex align-items-center gap-2">
            <div class="ra-agent-avatar">G</div>
            <span style="font-weight:700;color:var(--text);">ResearchAgent</span>
            <span style="background:rgba(163,113,247,0.18);color:#a371f7;font-size:0.65rem;padding:1px 7px;border-radius:4px;font-weight:600;">Granite</span>
          </div>
          <div class="d-flex align-items-center gap-2">
            ${data.elapsed_s ? `<span class="elapsed-tag">${data.elapsed_s}s</span>` : ""}
            <span class="msg-timestamp">${nowTime()}</span>
          </div>
        </div>
        <div class="ra-agent-card-body">
          ${steps.length ? `
            <div class="ra-trace-toggle" id="${traceId}-toggle">
              <i class="bi bi-diagram-3" style="color:var(--accent);"></i>
              <span>Reasoning Trace</span>
              <span class="trace-count">${steps.length} steps</span>
              <i class="bi bi-chevron-down toggle-arrow"></i>
            </div>
            <div class="ra-react-timeline" id="${traceId}">
              ${steps.map(s => {
                const type   = s.step_type || "thought";
                const badge  = `<span class="step-type-badge badge-${type}">${escHtml(type)}</span>`;
                const srcTag = s.source && s.source !== "INFER"
                  ? `<span class="src-tag src-${s.source.toLowerCase()}">[${s.source}]</span>` : "";
                return `<div class="ra-react-step ra-step-${type}">${badge}${srcTag}${highlightTags(s.content)}</div>`;
              }).join("")}
            </div>` : ""}
          <div class="ra-final-answer">${highlightTags(answer)}</div>
        </div>
        ${cites.length ? `
        <div class="ra-citations-strip">
          <div class="cite-label"><i class="bi bi-bookmark-fill me-1"></i>References — click to copy</div>
          ${cites.map(c => `
            <span class="ra-cite-chip" title="${escHtml(c.formatted || c.title)}"
              onclick="navigator.clipboard.writeText(${JSON.stringify(c.formatted || c.title)})">
              <span class="cite-num">${c.index}</span>
              ${escHtml(c.title || "Source")}
            </span>`).join("")}
        </div>` : ""}
      </div>`;

    messages.appendChild(row);

    // Wire up animated trace toggle
    if (steps.length) {
      const toggle   = document.getElementById(`${traceId}-toggle`);
      const timeline = document.getElementById(traceId);
      toggle.addEventListener("click", () => {
        const open = timeline.classList.toggle("open");
        toggle.classList.toggle("open", open);
      });
    }
    scrollToBottom();
  }

  function appendErrorCard(msg) {
    const row = document.createElement("div");
    row.className = "msg-row agent";
    row.innerHTML = `
      <div class="ra-agent-card">
        <div class="ra-agent-card-header">
          <div class="d-flex align-items-center gap-2">
            <div class="ra-agent-avatar" style="background:var(--danger);">!</div>
            <span style="font-weight:700;color:var(--danger);">Error</span>
          </div>
        </div>
        <div class="ra-agent-card-body">
          <p style="color:var(--danger);margin:0;font-size:0.85rem;">${escHtml(msg)}</p>
        </div>
      </div>`;
    messages.appendChild(row);
  }

  function scrollToBottom() {
    requestAnimationFrame(() => { messages.scrollTop = messages.scrollHeight; });
  }
}

// Legacy stubs (now inlined in initChat)
function buildReActTimeline() { return ""; }
function buildCitationsStrip() { return ""; }

// ─────────────────────────────────────────────────────────────────────────────
//  Dashboard
// ─────────────────────────────────────────────────────────────────────────────

async function loadDashboard() {
  try {
    const data = await apiFetch("/api/dashboard");
    renderDashboard(data);
  } catch (e) {
    console.error("Dashboard load failed", e);
  }
}

function renderDashboard(data) {
  // Stats
  $("#statPapers").textContent = data.total_papers;
  $("#statWX").textContent     = data.watsonx_configured ? "Online" : "Offline";
  $("#statExa").textContent    = data.exa_configured     ? "Online" : "Offline";
  $("#statWXIcon").style.color  = data.watsonx_configured ? "var(--success)" : "var(--danger)";
  $("#statExaIcon").style.color = data.exa_configured     ? "var(--success)" : "var(--danger)";

  // Papers list
  const papers = data.papers || [];
  const papersEl = $("#dashPapersList");
  if (!papers.length) {
    papersEl.innerHTML = '<p class="text-secondary">No papers ingested yet.</p>';
  } else {
    papersEl.innerHTML = `<div class="table-responsive">
      <table class="table table-sm" style="color:var(--text);font-size:0.8rem;">
        <thead><tr>
          <th style="color:var(--muted);">Title</th>
          <th style="color:var(--muted);">Authors</th>
          <th style="color:var(--muted);">Year</th>
          <th style="color:var(--muted);">Type</th>
        </tr></thead>
        <tbody>
          ${papers.map(p => `<tr>
            <td>${escHtml(p.title.substring(0,60))}${p.title.length > 60 ? "…" : ""}</td>
            <td>${escHtml(p.authors.substring(0,30))}${p.authors.length > 30 ? "…" : ""}</td>
            <td>${escHtml(p.year)}</td>
            <td>${p.is_test_case ? '<span class="test-case-badge">test-case</span>' : '<span style="font-size:0.7rem;color:var(--muted);">reference</span>'}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  }

  // Config
  const configEl = $("#dashConfig");
  configEl.innerHTML = `
    <dl style="font-size:0.8rem;" class="mb-0">
      <dt style="color:var(--muted);">Domain</dt>
      <dd>${escHtml(data.domain || "—")}</dd>
      <dt style="color:var(--muted);">Citation Style</dt>
      <dd><span class="ra-badge-cite badge">${escHtml(data.citation_style || "—")}</span></dd>
      <dt style="color:var(--muted);">ReAct Max Steps</dt>
      <dd>${data.react_max_steps || "—"}</dd>
      <dt style="color:var(--muted);">Model</dt>
      <dd>ibm/granite-3-3-8b-instruct</dd>
      <dt style="color:var(--muted);">Embed Model</dt>
      <dd>ibm/granite-embedding-125m-english</dd>
    </dl>`;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Citation Manager
// ─────────────────────────────────────────────────────────────────────────────

function renderCitationCards() {
  const container = $("#citationCardsList");
  const style = state.currentCiteStyle;

  if (!state.papers.length) {
    container.innerHTML = '<div class="col-12"><p class="text-secondary">No papers yet. Upload PDFs to see citations.</p></div>';
    return;
  }

  container.innerHTML = state.papers.map((p, i) => {
    const idx = i + 1;
    const formatted = formatCitation(p, idx, style);
    return `
      <div class="col-12 col-md-6">
        <div class="ra-citation-card">
          <span class="ra-citation-index">[${idx}]</span>
          <div style="font-size:0.85rem;font-weight:600;margin-bottom:4px;padding-right:40px;">${escHtml(p.title)}</div>
          <div style="font-size:0.78rem;color:var(--muted);margin-bottom:8px;">${escHtml(p.authors)} · ${escHtml(p.year)}</div>
          <div class="ra-claim-box" style="font-size:0.76rem;font-family:monospace;">${escHtml(formatted)}</div>
          <button class="btn btn-sm ra-btn-ghost mt-2" style="font-size:0.73rem;" onclick="copyText('${escHtml(formatted)}')">
            <i class="bi bi-clipboard"></i> Copy
          </button>
          ${p.is_test_case ? '<span class="test-case-badge ms-2">test-case</span>' : ''}
        </div>
      </div>`;
  }).join("");
}

function formatCitation(p, idx, style) {
  const title   = p.title || "Untitled";
  const authors = p.authors || "Unknown";
  const year    = p.year || "n.d.";
  if (style === "IRJET") {
    return `[${idx}] ${authors}, "${title}," IRJET, vol. X, no. X, ${year}.`;
  }
  return `[${idx}] ${authors}, "${title}," ${year}.`;
}

function initCitationManager() {
  const sel = $("#citeStyleSelect");
  sel.addEventListener("change", () => {
    state.currentCiteStyle = sel.value;
    renderCitationCards();
  });

  $("#copyAllCites").addEventListener("click", () => {
    if (!state.papers.length) { toast("No papers to copy", "warning"); return; }
    const all = state.papers.map((p, i) => formatCitation(p, i + 1, state.currentCiteStyle)).join("\n");
    copyText(all);
    toast("All citations copied!", "success");
  });
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(
    () => toast("Copied to clipboard!", "success"),
    () => toast("Copy failed — try manually", "error")
  );
}
window.copyText = copyText;

// ─────────────────────────────────────────────────────────────────────────────
//  Gap Analysis
// ─────────────────────────────────────────────────────────────────────────────

function initGaps() {
  $("#runGaps").addEventListener("click", async () => {
    const btn = $("#runGaps");
    const loading = $("#gapsLoading");
    const list    = $("#gapsList");

    btn.disabled = true;
    loading.classList.remove("d-none");
    list.innerHTML = "";

    try {
      const data = await apiFetch("/api/gaps");
      renderGaps(data.gaps || []);
    } catch (e) {
      toast("Gap analysis failed: " + e.message, "error");
      list.innerHTML = `<div class="col-12"><p class="text-danger">${escHtml(e.message)}</p></div>`;
    } finally {
      loading.classList.add("d-none");
      btn.disabled = false;
    }
  });
}

function renderGaps(gaps) {
  const list = $("#gapsList");
  if (!gaps.length) {
    list.innerHTML = '<div class="col-12"><p class="text-secondary">No gaps identified — upload papers first.</p></div>';
    return;
  }
  list.innerHTML = gaps.map(g => {
    const pct = Math.round((g.confidence || 0.5) * 100);
    return `
      <div class="col-12 col-md-6">
        <div class="ra-gap-card">
          <div class="ra-gap-title"><i class="bi bi-search me-2 text-primary"></i>${escHtml(g.gap_title)}</div>
          <div class="ra-gap-desc">${escHtml(g.description)}</div>
          <div class="mb-1 mt-2">
            <span style="font-size:0.72rem;color:var(--muted);">Missing evidence: </span>
            <span style="font-size:0.78rem;">${escHtml(g.missing_evidence || "—")}</span>
          </div>
          <div class="mb-2">
            <span style="font-size:0.72rem;color:var(--muted);">Potential impact: </span>
            <span style="font-size:0.78rem;">${escHtml(g.potential_impact || "—")}</span>
          </div>
          <div class="d-flex align-items-center gap-2 mt-2">
            <span style="font-size:0.72rem;color:var(--muted);">Confidence</span>
            <div class="ra-confidence-bar flex-grow-1">
              <div class="ra-confidence-fill ${confidenceColor(g.confidence)}" style="width:${pct}%"></div>
            </div>
            <span style="font-size:0.72rem;">${pct}%</span>
          </div>
        </div>
      </div>`;
  }).join("");
}

// ─────────────────────────────────────────────────────────────────────────────
//  Contradiction Detection
// ─────────────────────────────────────────────────────────────────────────────

function initContradictions() {
  $("#runContradictions").addEventListener("click", async () => {
    const btn     = $("#runContradictions");
    const loading = $("#contradictionsLoading");
    const list    = $("#contradictionsList");

    btn.disabled = true;
    loading.classList.remove("d-none");
    list.innerHTML = "";

    try {
      const data = await apiFetch("/api/contradictions");
      renderContradictions(data.contradictions || []);
    } catch (e) {
      toast("Detection failed: " + e.message, "error");
    } finally {
      loading.classList.add("d-none");
      btn.disabled = false;
    }
  });
}

function renderContradictions(items) {
  const list = $("#contradictionsList");
  if (!items.length) {
    list.innerHTML = '<p class="text-secondary px-2">No contradictions detected — or no papers uploaded yet.</p>';
    return;
  }
  list.innerHTML = items.map(c => {
    const sev = (c.severity || "medium").toLowerCase();
    const sevColor = sev === "high" ? "var(--danger)" : sev === "medium" ? "var(--warning)" : "var(--muted)";
    return `
      <div class="ra-contra-card severity-${sev}">
        <div class="ra-contra-header">
          <div class="d-flex align-items-center gap-2">
            <i class="bi bi-exclamation-triangle-fill" style="color:${sevColor};"></i>
            <span style="font-size:0.8rem;font-weight:600;">${escHtml(c.conflict_type || "Conflict")}</span>
          </div>
          <span class="badge" style="background:${sevColor};color:#fff;font-size:0.68rem;">${escHtml(c.severity || "medium").toUpperCase()}</span>
        </div>
        <div class="ra-contra-body">
          <div class="ra-contra-pair mb-2">
            <div class="ra-claim-box">
              <div>${escHtml(c.claim_a || "Claim A")}</div>
              <div class="ra-claim-source"><i class="bi bi-book me-1"></i>${escHtml(c.source_a || "Source A")}</div>
            </div>
            <div class="ra-vs-badge">VS</div>
            <div class="ra-claim-box">
              <div>${escHtml(c.claim_b || "Claim B")}</div>
              <div class="ra-claim-source"><i class="bi bi-book me-1"></i>${escHtml(c.source_b || "Source B")}</div>
            </div>
          </div>
          <p style="font-size:0.8rem;color:var(--muted);margin-bottom:0;">
            <i class="bi bi-info-circle me-1"></i>${escHtml(c.explanation || "")}
          </p>
        </div>
      </div>`;
  }).join("");
}

// ─────────────────────────────────────────────────────────────────────────────
//  Hypothesis Generator
// ─────────────────────────────────────────────────────────────────────────────

function initHypotheses() {
  $("#runHypotheses").addEventListener("click", async () => {
    const btn     = $("#runHypotheses");
    const loading = $("#hypothesesLoading");
    const list    = $("#hypothesesList");
    const topic   = ($("#hypothesisTopic").value.trim()) || "";

    btn.disabled = true;
    loading.classList.remove("d-none");
    list.innerHTML = "";

    try {
      const data = await apiFetch("/api/hypotheses", {
        method: "POST",
        body: JSON.stringify({ topic }),
      });
      renderHypotheses(data.hypotheses || [], data.topic);
    } catch (e) {
      toast("Hypothesis generation failed: " + e.message, "error");
    } finally {
      loading.classList.add("d-none");
      btn.disabled = false;
    }
  });
}

function renderHypotheses(hyps, topic) {
  const list = $("#hypothesesList");
  if (!hyps.length) {
    list.innerHTML = '<div class="col-12"><p class="text-secondary">No hypotheses generated.</p></div>';
    return;
  }
  list.innerHTML = hyps.map((h, i) => {
    const pct  = Math.round((h.confidence || 0.5) * 100);
    const cc   = confidenceColor(h.confidence);
    const testColor = h.testability === "high" ? "var(--success)" : h.testability === "medium" ? "var(--warning)" : "var(--danger)";

    const supporting = (h.supporting_evidence || []).map(e =>
      `<li style="font-size:0.78rem;">${escHtml(e)}</li>`).join("");
    const opposing = (h.opposing_evidence || []).map(e =>
      `<li style="font-size:0.78rem;color:var(--danger);">${escHtml(e)}</li>`).join("");

    return `
      <div class="col-12 col-lg-6">
        <div class="ra-hyp-card">
          <div class="d-flex align-items-start justify-content-between mb-1">
            <span class="badge" style="background:rgba(88,166,255,0.15);color:var(--accent);font-size:0.7rem;">H${i+1}</span>
            <span class="badge" style="background:rgba(0,0,0,0.2);color:${testColor};font-size:0.7rem;border:1px solid ${testColor};">
              Testability: ${escHtml(h.testability || "medium")}
            </span>
          </div>
          <div class="ra-hyp-text">${escHtml(h.hypothesis)}</div>

          <div class="d-flex align-items-center gap-2 mb-3">
            <span style="font-size:0.72rem;color:var(--muted);white-space:nowrap;">Confidence</span>
            <div class="ra-confidence-bar flex-grow-1">
              <div class="ra-confidence-fill ${cc}" style="width:${pct}%"></div>
            </div>
            <span style="font-size:0.72rem;">${pct}%</span>
          </div>

          <div class="row g-2">
            <div class="col-6">
              <p style="font-size:0.7rem;color:var(--success);font-weight:600;margin-bottom:3px;">
                <i class="bi bi-hand-thumbs-up-fill me-1"></i>Supporting
              </p>
              <ul class="ps-3 mb-0">${supporting || '<li style="font-size:0.78rem;color:var(--muted);">None listed</li>'}</ul>
            </div>
            <div class="col-6">
              <p style="font-size:0.7rem;color:var(--danger);font-weight:600;margin-bottom:3px;">
                <i class="bi bi-hand-thumbs-down-fill me-1"></i>Opposing
              </p>
              <ul class="ps-3 mb-0">${opposing || '<li style="font-size:0.78rem;color:var(--muted);">None listed</li>'}</ul>
            </div>
          </div>

          ${h.suggested_methodology ? `
            <div class="mt-3 p-2 rounded" style="background:var(--surface2);border:1px solid var(--border);">
              <span style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;font-weight:700;">Suggested Methodology</span>
              <p style="font-size:0.78rem;margin-top:3px;margin-bottom:0;">${escHtml(h.suggested_methodology)}</p>
            </div>` : ""}
        </div>
      </div>`;
  }).join("");
}

// ─────────────────────────────────────────────────────────────────────────────
//  Theme toggle
// ─────────────────────────────────────────────────────────────────────────────

function initTheme() {
  const btn = $("#themeToggle");
  btn.addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", state.theme);
    btn.innerHTML = state.theme === "dark"
      ? '<i class="bi bi-moon-stars-fill"></i>'
      : '<i class="bi bi-sun-fill"></i>';
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  Dashboard refresh button
// ─────────────────────────────────────────────────────────────────────────────

function initDashboardRefresh() {
  $("#refreshDashboard").addEventListener("click", loadDashboard);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Boot
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initTheme();
  initUpload();
  initChat();
  initGaps();
  initContradictions();
  initHypotheses();
  initCitationManager();
  initDashboardRefresh();

  // Initial data load
  checkStatus();
  loadKB();
});
