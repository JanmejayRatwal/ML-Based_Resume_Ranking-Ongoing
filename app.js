/* ============================================================
   app.js — UI ↔ Python Bridge
   Wires every control in index.html to window.pywebview.api
   and renders results returned by Python.
   No scoring, no calculations — all logic lives in Python.
   ============================================================ */

// ---------- State ----------

const state = {
  filePath: null,       // path to the currently selected file (set by Python)
  results:  [],         // ranked list returned by Python
};


const BADGE_NAMES = {
  "active-gh":  "Active GitHub",
  "oss-impact": "Open Source Impact",
  "published":  "Publications",
  "patents":    "Patents",
  "so-top":     "SO Top",
  "kaggle":     "Kaggle Medals",
};

// ---------- Tiny helpers ----------

const $ = (sel) => document.querySelector(sel);

function fmt(n, d = 2) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return Number(n).toFixed(d);
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class")   node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function")
      node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child === null || child === undefined) continue;
    if (Array.isArray(child)) node.append(...child.filter(Boolean));
    else if (typeof child === "string") node.append(document.createTextNode(child));
    else node.append(child);
  }
  return node;
}

function toast(msg, type = "success") {
  const t = el("div", { class: `toast ${type === "error" ? "error" : type === "amber" ? "amber" : ""}` }, msg);
  $("#toast-container").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 250); }, 3000);
}

// ---------- Call Python ----------

function api() {
  return window.pywebview && window.pywebview.api;
}

function callPython(methodName, ...args) {
  const a = api();
  if (!a) { toast("Python bridge not ready", "error"); return; }
  return a[methodName](...args);
}

// Send current file to Python to rank
function triggerRanking() {
  if (!state.filePath) return;
  showProcessing(true);
  callPython("start_ranking", state.filePath, "{}", "{}");
}

// ── File status / spinner helpers ────────────────────────────
function showFileStatus(filePath) {
  const name = filePath ? filePath.split(/[\/\\]/).pop() : "";
  const el   = $("#file-status");
  const lbl  = $("#file-name-label");
  if (el && lbl) {
    lbl.textContent = name || filePath;
    el.style.display = "flex";
  }
}

function showProcessing(visible) {
  const row = $("#processing-row");
  if (row) row.style.display = visible ? "flex" : "none";
}

// Debounce helper (kept in case needed later)
let _searchTimer = null;
function debouncedRank(ms = 250) {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(triggerRanking, ms);
}

// ---------- Callback from Python ----------
// Python calls window.onResults(jsonString) when ranking is complete.

window.onResults = function (jsonStr) {
  showProcessing(false);
  let data;
  try { data = JSON.parse(jsonStr); }
  catch (e) { toast("Invalid data from Python", "error"); return; }

  if (data.status === "error") {
    toast("Error: " + data.message, "error");
    return;
  }

  state.results = data.ranked || [];
  renderStats(data.stats);
  renderResults();
  toast(`Ranked ${data.count} candidates`);
};

// ---------- Stats bar ----------

function renderStats(stats) {
  if (!stats) return;
  $("#stat-total").textContent    = stats.total    ?? 0;
  $("#stat-filtered").textContent = stats.honeypots ?? 0;
  $("#stat-top").textContent      = stats.topFit   ?? 0;
  $("#stat-avg").textContent      = fmt(stats.avgScore, 2);
  $("#result-count").textContent  = `${state.results.length} results`;
  $("#top-score-badge").textContent = state.results.length
    ? `Top: ${state.results[0].score.toFixed(3)}`
    : "Top: 0.000";
}

// ---------- Results list ----------

function tierFor(score, rank) {
  if (rank === 0 && score > 0) return "tier-top";
  if (score >= 0.65) return "tier-top";
  if (score >= 0.40) return "tier-mid";
  return "tier-low";
}

function renderResults() {
  const list = $("#results-list");
  list.innerHTML = "";

  if (!state.results.length) {
    list.append(el("div", { class: "empty-state" },
      el("h3", {}, "No candidates loaded"),
      el("p", {}, "Load a file using the sidebar to get started.")
    ));
    return;
  }

  const frag = document.createDocumentFragment();
  state.results.forEach((r, idx) => {
    const c       = r.candidate;
    const profile = c.profile  || {};
    const skills  = c.skills   || [];
    const matched = new Set((r.breakdown.matched_skills || []).map(s => s.toLowerCase()));
    const tier    = tierFor(r.score, idx);
    const flagged = r.honeypotReasons && r.honeypotReasons.length > 0;

    const card = el("div",
      { class: `candidate-card ${tier} ${flagged ? "flagged" : ""}`, onClick: () => openModal(r) },

      // Rank number
      el("div", { class: `cand-rank ${tier}` },
        el("span", { class: "hash" }, "#"),
        String(idx + 1).padStart(2, "0")
      ),

      // Body
      el("div", { class: "cand-body" },
        el("div", { class: "cand-name" },
          profile.anonymized_name || "—",
          flagged ? el("span", { class: "flag" }, "honeypot") : null
        ),
        el("div", { class: "cand-meta" },
          el("span", {}, `📍 ${profile.location || "Unknown"}`),
          el("span", {}, `💼 ${profile.years_of_experience || 0}y exp`),
          el("span", {}, `⏱ ${profile.notice_period_days ?? "—"}d notice`),
          el("span", {}, `🛠 ${skills.length} skills`)
        ),
        el("div", { class: "cand-skills" },
          ...skills.slice(0, 10).map(s => el("span", {
            class: `skill-chip ${matched.has((s.skill_name || "").toLowerCase()) ? "match" : ""}`,
            title: `${s.proficiency || ""} · ${s.duration_months || 0}mo`,
          }, s.skill_name)),
          skills.length > 10 ? el("span", { class: "skill-chip muted-chip" }, `+${skills.length - 10} more`) : null
        ),
        r.breakdown.badges && r.breakdown.badges.length
          ? el("div", { class: "behav-badges" },
              ...r.breakdown.badges.slice(0, 4).map(b =>
                el("span", { class: `behav-badge ${b === "published" || b === "patents" ? "violet" : ""}` },
                  BADGE_NAMES[b] || b)
              )
            )
          : null,
        el("div", { class: "cand-reason" }, r.reason || "")
      ),

      // Score
      el("div", { class: "cand-score" },
        el("div", { class: `score-num ${tier}` }, r.score.toFixed(3)),
        el("div", { class: `score-bar ${tier === "tier-low" ? "tier-low" : ""}` },
          el("div", { style: `width:${Math.min(100, r.score * 100).toFixed(1)}%` })
        )
      )
    );
    frag.appendChild(card);
  });
  list.appendChild(frag);
}

// ---------- Detail modal ----------

function openModal(r) {
  const c       = r.candidate;
  const profile = c.profile         || {};
  const history = (c.career_history || []).slice().sort((a, b) => (b.start_date || "").localeCompare(a.start_date || ""));
  const edu     = (c.education      || []).slice().sort((a, b) => (b.start_year || 0) - (a.start_year || 0));
  const skills  = c.skills          || [];
  const sig     = c.redrob_signals  || {};
  const body    = $("#modal-body");
  body.innerHTML = "";

  // Header
  body.appendChild(el("div", { class: "modal-header" },
    el("div", {},
      el("div", { class: "modal-name" }, profile.anonymized_name || "—"),
      el("div", { class: "modal-id" },   c.candidate_id)
    ),
    el("div", { class: "modal-score-box" },
      el("div", { class: "modal-score" }, r.score.toFixed(3)),
      el("div", { class: "modal-rank" },  `Rank #${state.results.indexOf(r) + 1} · ${profile.location || "Unknown"}`)
    )
  ));

  // Score breakdown pills
  const grid = el("div", { class: "score-grid" });
  for (const [k, v] of Object.entries(r.breakdown)) {
    if (typeof v !== "number") continue;
    grid.appendChild(el("div", { class: "score-pill" },
      el("div", { class: "score-pill-label" }, WEIGHT_LABELS[k] || k),
      el("div", { class: "score-pill-value" }, fmt(v, 3))
    ));
  }
  body.appendChild(grid);

  // Career history
  if (history.length) {
    const section = el("div", { class: "modal-section" },
      el("h4", {}, el("span", { class: "section-bullet" }), " Career History")
    );
    const timeline = el("div", { class: "timeline" });
    history.forEach(j => {
      const isTier1 = ["google","deepmind","meta","microsoft","amazon","apple","openai","anthropic","nvidia"].includes((j.company || "").toLowerCase());
      const isTier2 = ["scale ai","huggingface","razorpay","phonepe","flipkart","swiggy","zomato"].includes((j.company || "").toLowerCase());
      timeline.appendChild(el("div", { class: `timeline-item ${isTier1 ? "tier-1" : isTier2 ? "tier-2" : ""}` },
        el("div", { class: "timeline-date" }, `${j.start_date || "—"} → ${j.end_date || "Present"}`),
        el("div", { class: "timeline-body" },
          el("strong", {}, `${j.company || "—"} · ${j.job_title || j.title || "—"}`),
          el("div",   { class: "meta" }, `${j.duration_months || 0} months`)
        )
      ));
    });
    section.appendChild(timeline);
    body.appendChild(section);
  }

  // Education
  if (edu.length) {
    const section = el("div", { class: "modal-section" },
      el("h4", {}, el("span", { class: "section-bullet" }), " Education")
    );
    edu.forEach(e => {
      section.appendChild(el("div", { class: "kv-row" },
        el("span", { class: "k" }, `${e.degree || "—"} · ${e.institution || "—"}`),
        el("span", { class: "v" }, e.start_year && e.end_year ? `${e.start_year}–${e.end_year}` : "—")
      ));
    });
    body.appendChild(section);
  }

  // Skills
  if (skills.length) {
    const section = el("div", { class: "modal-section" },
      el("h4", {}, el("span", { class: "section-bullet" }), " Skills")
    );
    const grid2 = el("div", { class: "skill-grid" });
    skills.forEach(s => grid2.appendChild(el("span", {
      class: "skill-chip",
      title: `${s.proficiency || ""} · ${s.duration_months || 0}mo`,
    }, s.skill_name)));
    section.appendChild(grid2);
    body.appendChild(section);
  }

  // Signals
  const sigItems = [];
  if (sig.github?.username)
    sigItems.push(`GitHub: @${sig.github.username} · ${sig.github.contributions_last_year || 0} contributions · ${sig.github.total_stars || 0} stars`);
  if ((sig.publications || []).length)
    sigItems.push(`${sig.publications.length} publication(s)`);
  if ((sig.patents || []).length)
    sigItems.push(`${sig.patents.length} patent(s)`);
  if (sig.stackoverflow?.reputation)
    sigItems.push(`Stack Overflow: ${sig.stackoverflow.reputation} reputation`);
  if (sig.kaggle?.username)
    sigItems.push(`Kaggle: @${sig.kaggle.username} · ${sig.kaggle.medals || 0} medals`);
  if (sigItems.length) {
    const section = el("div", { class: "modal-section" },
      el("h4", {}, el("span", { class: "section-bullet" }), " Behavioral Signals")
    );
    sigItems.forEach(s => section.appendChild(el("div", { class: "kv-row" }, el("span", {}, s))));
    body.appendChild(section);
  }

  $("#modal-backdrop").classList.add("open");
}

function closeModal() {
  $("#modal-backdrop").classList.remove("open");
}



// ---------- Initialise ----------

function init() {
  renderResults();

  // Modal close
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-backdrop").addEventListener("click", (e) => {
    if (e.target === $("#modal-backdrop")) closeModal();
  });

  // --- Dropzone: drag-and-drop a file ---
  const dz = $("#dropzone");
  dz.addEventListener("dragover",  (e) => { e.preventDefault(); dz.classList.add("drag-over"); });
  dz.addEventListener("dragleave", ()  => dz.classList.remove("drag-over"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const path = file.path || null;
    if (path) {
      state.filePath = path;
      showFileStatus(path);
      toast(`File selected: ${file.name}`);
      triggerRanking();
    } else {
      toast("Drop is only supported inside the desktop app", "amber");
    }
  });

  // --- Dropzone click → open file dialog via Python ---
  dz.addEventListener("click", async () => {
    const a = api();
    if (!a) { toast("Python bridge not ready", "error"); return; }
    const path = await a.open_file_dialog();
    if (path) {
      state.filePath = path;
      showFileStatus(path);
      toast(`File selected`);
      triggerRanking();
    }
  });

  // --- Reload Dataset button — re-ranks the currently loaded file ---
  $("#load-all").addEventListener("click", () => {
    if (!state.filePath || state.filePath === "__preset_100k__") {
      toast("No file loaded yet — drop a file or use the file picker", "amber");
      return;
    }
    triggerRanking();
  });


  // --- Export CSV button ---
  $("#export-csv").addEventListener("click", () => {
    callPython("open_csv");
  });
}

// Boot when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
