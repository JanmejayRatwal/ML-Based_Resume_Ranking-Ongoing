/* ============================================================
   CandidateRank · Frontend Sandbox
   Mirrors the Python ranking engine (rank.py) 1:1
   ============================================================ */

// ---------- Constants (mirror rank.py) ----------

const JD_KEYWORDS = [
  "python", "pytorch", "tensorflow", "jax", "llm", "large language model",
  "machine learning", "deep learning", "nlp", "natural language processing",
  "computer vision", "transformer", "rag", "retrieval", "agent", "agents",
  "reinforcement learning", "mlops", "data pipelines", "distributed systems",
  "cuda", "triton", "kubernetes", "docker", "aws", "gcp", "azure",
  "spark", "kafka", "airflow", "mlflow", "wandb", "langchain", "llamaindex",
  "huggingface", "transformers", "embedding", "vector database", "faiss",
  "pinecone", "weaviate", "chroma", "rust", "go", "typescript", "react",
  "next.js", "fastapi", "django", "flask", "grpc", "rest api",
  "generative ai", "genai", "stable diffusion", "diffusion", "speech",
  "recommendation", "search", "ranking", "click prediction", "ab testing",
  "statistics", "linear algebra", "optimization", "research", "publication",
  "arxiv", "neurips", "icml", "acl", "emnlp", "cvpr", "iccv"
];

const PREFERRED_LOCATIONS = new Set([
  "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi",
  "gurgaon", "gurugram", "noida", "chennai", "kolkata", "india",
  "remote", "anywhere"
]);

const TIER_1_COMPANIES = new Set([
  "google", "deepmind", "meta", "facebook", "microsoft", "amazon", "aws",
  "apple", "openai", "anthropic", "nvidia", "tesla", "uber", "airbnb",
  "stripe", "linkedin", "twitter", "x", "salesforce", "adobe", "netflix",
  "ibm research", "baidu", "tencent", "alibaba", "tiktok", "bytedance",
  "snap", "pinterest", "dropbox", "slack", "snowflake", "databricks",
  "palantir", "coinbase", "doordash", "instacart", "lyft"
]);

const TIER_2_COMPANIES = new Set([
  "scale ai", "huggingface", "weights & biases", "weights and biases",
  "cohere", "mistral", "stability ai", "midjourney", "runway", "anyscale",
  "pinecone", "weaviate", "langchain", "llamaindex", "replicate",
  "together ai", "fireworks ai", "perplexity", "character.ai",
  "inflection", "x.ai", "grok", "cursor", "codeium", "replit",
  "figma", "notion", "vercel", "supabase", "linear", "ramp",
  "razorpay", "cred", "phonepe", "paytm", "flipkart", "swiggy",
  "zomato", "ola", "meesho", "zepto", "freshworks", "zoho",
  "byjus", "unacademy", "vedantu", "postman", "browserstack"
]);

const NOTICE_PERIOD_SCORES = [
  [0, 1.00], [7, 0.95], [14, 0.90], [15, 0.90], [30, 0.80],
  [45, 0.65], [60, 0.50], [75, 0.35], [90, 0.20],
  [120, 0.05], [180, 0.00]
];

const PRESENT_DATE = new Date("2026-06-06T00:00:00Z");

const DEFAULT_WEIGHTS = {
  skills: 0.35,
  experience: 0.20,
  company: 0.20,
  behavioral: 0.10,
  notice_period: 0.10,
  location: 0.05,
};

const FOUNDERS_PRESET = {
  skills: 0.40,
  experience: 0.20,
  company: 0.15,
  behavioral: 0.15,
  notice_period: 0.05,
  location: 0.05,
};

const WEIGHT_LABELS = {
  skills: "Skills Match",
  experience: "Experience",
  company: "Company Tier",
  behavioral: "Behavioral Signals",
  notice_period: "Notice Period",
  location: "Location",
};

const BADGE_NAMES = {
  "active-gh": "Active GitHub",
  "oss-impact": "Open Source Impact",
  "published": "Publications",
  "patents": "Patents",
  "so-top": "SO Top",
  "kaggle": "Kaggle Medals",
};

// ---------- App State ----------

const state = {
  candidates: [],
  weights: { ...DEFAULT_WEIGHTS },
  filters: {
    search: "",
    hideHoneypots: true,
    hideZeroYoE: false,
    indiaOnly: false,
  },
  results: [], // scored & sorted
};

// ---------- Utility ----------

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function fmt(n, digits = 2) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
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

function parseDate(s) {
  if (!s) return null;
  const d = new Date(s + (s.length === 10 ? "T00:00:00Z" : ""));
  return isNaN(d.getTime()) ? null : d;
}

function monthDiff(a, b) {
  return (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth());
}

function toast(message, type = "success") {
  const t = el("div", { class: `toast ${type === "error" ? "error" : type === "amber" ? "amber" : ""}` }, message);
  $("#toast-container").appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transform = "translateX(20px)";
    setTimeout(() => t.remove(), 250);
  }, 3000);
}

// ---------- File Parsing ----------

function parseFile(text, filename = "") {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const isJsonl = filename.endsWith(".jsonl") || trimmed.split("\n").filter(Boolean).every(l => l.trimStart().startsWith("{"));
  if (isJsonl) {
    return trimmed.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
      try { return JSON.parse(l); } catch { return null; }
    }).filter(Boolean);
  }
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return parsed;
    if (Array.isArray(parsed.candidates)) return parsed.candidates;
    return [parsed];
  } catch (e) {
    // last-ditch: try JSONL
    return trimmed.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
      try { return JSON.parse(l); } catch { return null; }
    }).filter(Boolean);
  }
}

async function fetchSample() {
  // Sample fallback: 50 pre-canned candidates
  const res = await fetch("sample_candidates.json").catch(() => null);
  if (res && res.ok) {
    const data = await res.json();
    if (Array.isArray(data)) return data;
    if (Array.isArray(data.candidates)) return data.candidates;
  }
  return null;
}

async function fetchAllCandidates() {
  const res = await fetch("candidates.jsonl").catch(() => null);
  if (res && res.ok) {
    const text = await res.text();
    return parseFile(text, "candidates.jsonl");
  }
  return null;
}

// ---------- Honeypot Detection (mirrors rank.py) ----------

function detectHoneypot(c) {
  const reasons = [];
  const skills = c.skills || [];
  const history = c.career_history || [];
  const profile = c.profile || {};
  const totalMonths = (profile.years_of_experience || 0) * 12;

  // Rule 1
  for (const s of skills) {
    const prof = (s.proficiency || "").toLowerCase();
    const dur = s.duration_months || 0;
    if ((prof === "expert" || prof === "advanced") && dur === 0) {
      reasons.push(`Skill '${s.skill_name}' marked as ${prof} with 0 months duration.`);
      break;
    }
  }
  // Rule 2
  for (const j of history) {
    if (!j.start_date || (j.duration_months || 0) <= 0) continue;
    const start = parseDate(j.start_date);
    if (!start) continue;
    const end = j.end_date ? parseDate(j.end_date) : new Date(PRESENT_DATE);
    const expected = monthDiff(start, end);
    if (expected > 0 && j.duration_months > expected + 12) {
      reasons.push(`Job at ${j.company}: stated ${j.duration_months} months vs ${expected} month span.`);
      break;
    }
  }
  // Rule 3
  if (totalMonths > 0) {
    for (const j of history) {
      if ((j.duration_months || 0) > totalMonths) {
        reasons.push(`Job at ${j.company}: ${j.duration_months} months exceeds total ${profile.years_of_experience}y experience.`);
        break;
      }
    }
  }
  return reasons;
}

// ---------- Scoring (mirrors rank.py) ----------

function scoreSkills(skills) {
  if (!skills || !skills.length) return { score: 0, matched: [] };
  const profWeight = { beginner: 0.25, intermediate: 0.5, advanced: 0.75, expert: 1.0 };
  let total = 0, earned = 0;
  const matched = [];
  for (const s of skills) {
    const name = (s.skill_name || "").toLowerCase();
    if (!name) continue;
    const prof = (s.proficiency || "intermediate").toLowerCase();
    const w = profWeight[prof] ?? 0.5;
    total += w;
    if (JD_KEYWORDS.some(kw => name.includes(kw))) {
      earned += w;
      matched.push(s.skill_name);
    }
  }
  if (total === 0) return { score: 0, matched: [] };
  return { score: Math.min(1, earned / Math.max(5, total * 0.4)), matched };
}

function scoreExperience(profile) {
  const years = profile.years_of_experience || 0;
  if (years <= 0) return 0;
  if (years >= 12) return 1;
  return Math.min(1, 1 - (1 / (1 + years / 4)));
}

function scoreCompany(history) {
  if (!history || !history.length) return { score: 0, tier1: [], topMonths: 0 };
  let tier1 = false, tier2 = false, topMonths = 0;
  const tier1List = [];
  for (const j of history) {
    const comp = (j.company || "").toLowerCase();
    const dur = j.duration_months || 0;
    if (TIER_1_COMPANIES.has(comp)) { tier1 = true; topMonths += dur; tier1List.push(j.company); }
    else if (TIER_2_COMPANIES.has(comp)) { tier2 = true; topMonths += dur; }
  }
  let score = 0;
  if (tier1) score = 1;
  else if (tier2) score = 0.7;
  else score = 0.35;
  if (topMonths >= 36) score = Math.min(1, score + 0.05);
  return { score, tier1: tier1List, topMonths };
}

function scoreLocation(profile) {
  const loc = (profile.location || "").toLowerCase();
  if (!loc) return 0.5;
  if (PREFERRED_LOCATIONS.has(loc)) return 1.0;
  if ([...PREFERRED_LOCATIONS].some(p => loc.includes(p))) return 1.0;
  return 0.4;
}

function scoreNoticePeriod(profile) {
  if (profile.notice_period_days === null || profile.notice_period_days === undefined) return 0.5;
  const np = profile.notice_period_days;
  for (const [k, v] of NOTICE_PERIOD_SCORES) {
    if (np <= k) return v;
  }
  return 0;
}

function scoreBehavioral(c) {
  const sig = c.redrob_signals || {};
  const badges = [];
  let score = 0;
  const gh = sig.github || {};
  if (gh.username) {
    const c1 = gh.contributions_last_year || 0;
    const stars = gh.total_stars || 0;
    if (c1 >= 200) { score += 0.35; badges.push("active-gh"); }
    else if (c1 >= 50) { score += 0.20; badges.push("active-gh"); }
    if (stars >= 50) { score += 0.20; badges.push("oss-impact"); }
    else if (stars >= 10) { score += 0.10; badges.push("oss-impact"); }
  }
  if ((sig.publications || []).length) {
    score += Math.min(0.30, 0.10 * sig.publications.length);
    badges.push("published");
  }
  if ((sig.patents || []).length) {
    score += Math.min(0.20, 0.07 * sig.patents.length);
    badges.push("patents");
  }
  const so = sig.stackoverflow || {};
  if ((so.reputation || 0) >= 1000) { score += 0.10; badges.push("so-top"); }
  const kg = sig.kaggle || {};
  if (kg.username && (kg.medals || 0) > 0) {
    score += Math.min(0.20, 0.05 * kg.medals);
    badges.push("kaggle");
  }
  return { score: Math.min(1, score), badges };
}

function scoreCandidate(c, w) {
  const skills = scoreSkills(c.skills);
  const exp = scoreExperience(c.profile);
  const comp = scoreCompany(c.career_history);
  const loc = scoreLocation(c.profile);
  const np = scoreNoticePeriod(c.profile);
  const behav = scoreBehavioral(c);

  const final =
    w.skills * skills.score +
    w.experience * exp +
    w.company * comp.score +
    w.behavioral * behav.score +
    w.notice_period * np +
    w.location * loc;

  return {
    final,
    breakdown: {
      skills: skills.score,
      experience: exp,
      company: comp.score,
      location: loc,
      notice_period: np,
      behavioral: behav.score,
      matched_skills: skills.matched.slice(0, 8),
      top_companies: comp.tier1.slice(0, 4),
      badges: behav.badges,
      top_company_months: comp.topMonths,
    },
  };
}

// ---------- Reason Generation (mirrors rank.py) ----------

function generateReason(c, breakdown, score) {
  const profile = c.profile || {};
  const name = profile.anonymized_name || "Candidate";
  const parts = [];

  if (breakdown.matched_skills.length) {
    parts.push(`Strong skill match on ${breakdown.matched_skills.slice(0, 4).join(", ")}`);
  }
  const years = profile.years_of_experience || 0;
  if (years >= 5) parts.push(`${years}+ years of relevant engineering experience`);
  else if (years >= 2) parts.push(`${years} years of hands-on experience`);

  if (breakdown.top_companies.length) {
    parts.push(`background at ${breakdown.top_companies.slice(0, 2).join(", ")}`);
  }
  const loc = profile.location;
  if (loc && [...PREFERRED_LOCATIONS].some(p => loc.toLowerCase().includes(p))) {
    parts.push(`based in ${loc}`);
  }
  if (profile.notice_period_days != null && profile.notice_period_days <= 30) {
    parts.push(`${profile.notice_period_days}-day notice period enables fast onboarding`);
  }
  if (breakdown.badges.length) {
    const names = breakdown.badges.slice(0, 2).map(b => BADGE_NAMES[b] || b);
    parts.push("signals: " + names.join(", "));
  }

  if (!parts.length) {
    return `${name} has a balanced profile scoring ${score.toFixed(2)} across the JD criteria.`;
  }
  const s1 = parts[0][0].toUpperCase() + parts[0].slice(1) + ".";
  let s2 = "";
  if (parts.length > 1) {
    s2 = parts.slice(1).join(" and ");
    s2 = s2[0].toUpperCase() + s2.slice(1) + ".";
  }
  return s2 ? `${s1} ${s2}` : s1;
}

// ---------- Apply Filters + Rank ----------

function applyFilters() {
  const f = state.filters;
  const q = f.search.toLowerCase().trim();

  let arr = state.candidates.map(c => {
    const honeypotReasons = detectHoneypot(c);
    const { final, breakdown } = scoreCandidate(c, state.weights);
    const reason = generateReason(c, breakdown, final);
    return { candidate: c, score: final, breakdown, reason, honeypotReasons };
  });

  if (f.hideHoneypots) arr = arr.filter(x => x.honeypotReasons.length === 0);
  if (f.hideZeroYoE) arr = arr.filter(x => (x.candidate.profile?.years_of_experience || 0) > 0);
  if (f.indiaOnly) {
    arr = arr.filter(x => {
      const loc = (x.candidate.profile?.location || "").toLowerCase();
      return [...PREFERRED_LOCATIONS].some(p => loc.includes(p));
    });
  }
  if (q) {
    arr = arr.filter(x => {
      const name = (x.candidate.profile?.anonymized_name || "").toLowerCase();
      const skills = (x.candidate.skills || []).map(s => (s.skill_name || "").toLowerCase());
      if (name.includes(q)) return true;
      if (skills.some(s => s.includes(q))) return true;
      const comps = (x.candidate.career_history || []).map(j => (j.company || "").toLowerCase());
      if (comps.some(c => c.includes(q))) return true;
      return false;
    });
  }

  arr.sort((a, b) => b.score - a.score);
  state.results = arr;
}

// ---------- Render ----------

function updateStats() {
  const total = state.candidates.length;
  const honeypots = state.candidates.filter(c => detectHoneypot(c).length > 0).length;
  const topFit = state.results.filter(r => r.score >= 0.65).length;
  const avg = state.results.length
    ? state.results.reduce((a, r) => a + r.score, 0) / state.results.length
    : 0;

  $("#stat-total").textContent = total;
  $("#stat-filtered").textContent = honeypots;
  $("#stat-top").textContent = topFit;
  $("#stat-avg").textContent = fmt(avg, 2);
  $("#result-count").textContent = `${state.results.length} result${state.results.length !== 1 ? "s" : ""}`;
  $("#top-score-badge").textContent = state.results.length
    ? `Top: ${state.results[0].score.toFixed(3)}`
    : "Top: 0.000";
}

function tierFor(score, rank) {
  if (rank === 0 && score > 0) return "tier-top";
  if (score >= 0.65) return "tier-top";
  if (score >= 0.40) return "tier-mid";
  return "tier-low";
}

function renderResults() {
  const list = $("#results-list");
  list.innerHTML = "";

  if (state.results.length === 0) {
    list.append(el("div", { class: "empty-state" },
      el("div", { html: `<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>` }),
      el("h3", {}, state.candidates.length ? "No candidates match your filters" : "No candidates loaded"),
      el("p", {}, state.candidates.length
        ? "Try clearing the search box or unchecking some filters."
        : "Click Load 50 Sample in the sidebar, or drop your own JSON/JSONL file to get started.")
    ));
    return;
  }

  const frag = document.createDocumentFragment();
  state.results.slice(0, 100).forEach((r, idx) => {
    const c = r.candidate;
    const profile = c.profile || {};
    const skills = c.skills || [];
    const matchedSet = new Set((r.breakdown.matched_skills || []).map(s => s.toLowerCase()));
    const topSkills = skills.slice(0, 10);

    const tier = tierFor(r.score, idx);
    const isFlagged = r.honeypotReasons.length > 0;

    const card = el("div", {
      class: `candidate-card ${tier} ${isFlagged ? "flagged" : ""}`,
      onClick: () => openModal(r),
    },
      el("div", { class: `cand-rank ${tier}` },
        el("span", { class: "hash" }, "#"),
        String(idx + 1).padStart(2, "0")
      ),
      el("div", { class: "cand-body" },
        el("div", { class: "cand-name" },
          profile.anonymized_name || "—",
          isFlagged ? el("span", { class: "flag" }, "honeypot") : null
        ),
        el("div", { class: "cand-meta" },
          el("span", {}, `📍 ${profile.location || "Unknown"}`),
          el("span", {}, `💼 ${profile.years_of_experience || 0}y exp`),
          el("span", {}, `⏱ ${profile.notice_period_days ?? "—"}d notice`),
          el("span", {}, `🛠 ${skills.length} skills`),
        ),
        el("div", { class: "cand-skills" },
          ...topSkills.map(s => {
            const isMatch = matchedSet.has((s.skill_name || "").toLowerCase());
            return el("span", {
              class: `skill-chip ${isMatch ? "match" : ""}`,
              title: `${s.proficiency || ""} · ${s.duration_months || 0}mo`,
            }, s.skill_name);
          }),
          skills.length > 10
            ? el("span", { class: "skill-chip muted-chip" }, `+${skills.length - 10} more`)
            : null,
        ),
        r.breakdown.badges.length
          ? el("div", { class: "behav-badges" },
              ...r.breakdown.badges.slice(0, 4).map(b =>
                el("span", { class: `behav-badge ${b === "published" || b === "patents" ? "violet" : ""}` },
                  BADGE_NAMES[b] || b)
              )
            )
          : null,
        el("div", { class: "cand-reason" }, r.reason),
      ),
      el("div", { class: "cand-score" },
        el("div", { class: `score-num ${tier}` }, r.score.toFixed(3)),
        el("div", { class: `score-bar ${tier === "tier-low" ? "tier-low" : ""}` },
          el("div", { style: `width:${Math.min(100, r.score * 100).toFixed(1)}%` })
        ),
      ),
    );
    frag.appendChild(card);
  });

  list.appendChild(frag);
}

function reRender(flash = false) {
  applyFilters();
  updateStats();
  renderResults();
  if (flash) {
    setTimeout(() => {
      $$(".candidate-card").forEach((n, i) => {
        if (i < 5) {
          n.classList.add("flash");
          setTimeout(() => n.classList.remove("flash"), 700);
        }
      });
    }, 10);
  }
}

// ---------- Weight Sliders ----------

function renderWeightSliders() {
  const grid = $("#weight-grid");
  grid.innerHTML = "";
  for (const [key, val] of Object.entries(state.weights)) {
    const row = el("div", { class: "weight-row" },
      el("div", { class: "weight-head" },
        el("span", { class: "weight-label" }, WEIGHT_LABELS[key] || key),
        el("span", { class: "weight-val", dataset: { key } }, val.toFixed(2))
      ),
      el("input", {
        type: "range",
        min: "0", max: "1", step: "0.01",
        value: String(val),
        dataset: { key },
        onInput: (e) => onWeightChange(key, parseFloat(e.target.value)),
      })
    );
    grid.appendChild(row);
  }
}

function onWeightChange(key, value) {
  state.weights[key] = value;
  // Update label
  const lbl = document.querySelector(`.weight-val[data-key="${key}"]`);
  if (lbl) lbl.textContent = value.toFixed(2);
  // Debounced re-rank
  clearTimeout(onWeightChange._t);
  onWeightChange._t = setTimeout(() => reRender(true), 80);
}

function setWeights(weights) {
  state.weights = { ...weights };
  // Normalize if needed (they should already sum to 1)
  renderWeightSliders();
  reRender(true);
}

// ---------- Detail Modal ----------

function openModal(r) {
  const c = r.candidate;
  const p = c.profile || {};
  const history = (c.career_history || []).slice().sort((a, b) =>
    (b.start_date || "").localeCompare(a.start_date || "")
  );
  const edu = (c.education || []).slice().sort((a, b) =>
    (b.start_year || 0) - (a.start_year || 0)
  );
  const sig = c.redrob_signals || {};

  const isTier1 = (comp) => TIER_1_COMPANIES.has((comp || "").toLowerCase());
  const isTier2 = (comp) => TIER_2_COMPANIES.has((comp || "").toLowerCase());

  const body = $("#modal-body");
  body.innerHTML = "";

  // Header
  body.appendChild(el("div", { class: "modal-header" },
    el("div", {},
      el("div", { class: "modal-name" }, p.anonymized_name || "—"),
      el("div", { class: "modal-id" }, c.candidate_id),
    ),
    el("div", { class: "modal-score-box" },
      el("div", { class: "modal-score" }, r.score.toFixed(3)),
      el("div", { class: "modal-rank" }, `Rank #${state.results.indexOf(r) + 1} · ${p.location || "Unknown"}`),
    ),
  ));

  // Score grid
  const scoreGrid = el("div", { class: "score-grid" });
  const
