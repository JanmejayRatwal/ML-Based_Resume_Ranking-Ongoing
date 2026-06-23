"""
score_computer.py - Scoring logic for the candidate ranker.

Extracted from rank.py so that ranker.py can import a single
    score(candidate) -> float
function without pulling in rank.py's CLI / CSV / I/O code.

All weights, constants, and helper functions live here.
ranker.py only needs to do:
    from score_computer import score
"""

from datetime import datetime, date

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JD_KEYWORDS = [
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
    "arxiv", "neurips", "icml", "acl", "emnlp", "cvpr", "iccv",
]

PREFERRED_LOCATIONS = {
    "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi",
    "gurgaon", "gurugram", "noida", "chennai", "kolkata", "india",
    "remote", "anywhere",
}

TIER_1_COMPANIES = {
    "google", "deepmind", "meta", "facebook", "microsoft", "amazon", "aws",
    "apple", "openai", "anthropic", "nvidia", "tesla", "uber", "airbnb",
    "stripe", "linkedin", "twitter", "x", "salesforce", "adobe", "netflix",
    "ibm research", "baidu", "tencent", "alibaba", "tiktok", "bytedance",
    "snap", "pinterest", "dropbox", "slack", "snowflake", "databricks",
    "palantir", "coinbase", "doordash", "instacart", "lyft",
}

TIER_2_COMPANIES = {
    "scale ai", "huggingface", "weights & biases", "weights and biases",
    "cohere", "mistral", "stability ai", "midjourney", "runway", "anyscale",
    "pinecone", "weaviate", "langchain", "llamaindex", "replicate",
    "together ai", "fireworks ai", "perplexity", "character.ai",
    "inflection", "x.ai", "grok", "cursor", "codeium", "replit",
    "figma", "notion", "vercel", "supabase", "linear", "ramp",
    "razorpay", "cred", "phonepe", "paytm", "flipkart", "swiggy",
    "zomato", "ola", "meesho", "zepto", "freshworks", "zoho",
    "byjus", "unacademy", "vedantu", "postman", "browserstack",
}

NOTICE_PERIOD_SCORES = {
    0: 1.00, 7: 0.95, 14: 0.90, 15: 0.90, 30: 0.80,
    45: 0.65, 60: 0.50, 75: 0.35, 90: 0.20,
    120: 0.05, 180: 0.00,
}

DEFAULT_WEIGHTS = {
    "skills":        0.35,
    "experience":    0.20,
    "company":       0.20,
    "behavioral":    0.10,
    "notice_period": 0.10,
    "location":      0.05,
}

PRESENT_DATE = date(2026, 6, 6)


# ---------------------------------------------------------------------------
# Helper scorers  (same logic as rank.py — do NOT duplicate edits)
# ---------------------------------------------------------------------------

def _score_skills(skills):
    if not skills:
        return 0.0
    prof_buckets = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
    total_weight = 0.0
    earned = 0.0
    for s in skills:
        name = (s.get("skill_name") or "").strip().lower()
        if not name:
            continue
        prof = (s.get("proficiency") or "intermediate").strip().lower()
        p_weight = prof_buckets.get(prof, 2) / 4.0
        total_weight += p_weight
        if any(kw in name for kw in JD_KEYWORDS):
            earned += p_weight
    if total_weight == 0:
        return 0.0
    return min(1.0, earned / max(5.0, total_weight * 0.4))


def _score_experience(profile):
    years = profile.get("years_of_experience", 0) or 0
    if years <= 0:
        return 0.0
    if years >= 12:
        return 1.0
    return min(1.0, 1.0 - (1.0 / (1.0 + years / 4.0)))


def _score_company(history):
    if not history:
        return 0.0
    tier1_hit = False
    tier2_hit = False
    total_months_top = 0
    for job in history:
        comp = (job.get("company") or "").strip().lower()
        dur = job.get("duration_months") or 0
        if comp in TIER_1_COMPANIES:
            tier1_hit = True
            total_months_top += dur
        elif comp in TIER_2_COMPANIES:
            tier2_hit = True
            total_months_top += dur
    if tier1_hit:
        s = 1.0
    elif tier2_hit:
        s = 0.7
    else:
        s = 0.35
    if total_months_top >= 36:
        s = min(1.0, s + 0.05)
    return s


def _score_location(profile):
    loc = (profile.get("location") or "").strip().lower()
    if not loc:
        return 0.5
    return 1.0 if any(p in loc for p in PREFERRED_LOCATIONS) else 0.4


def _score_notice_period(profile):
    np_days = profile.get("notice_period_days")
    if np_days is None:
        return 0.5
    for k, v in sorted(NOTICE_PERIOD_SCORES.items()):
        if np_days <= k:
            return v
    return 0.0


def _score_behavioral(candidate):
    signals = candidate.get("redrob_signals", {}) or {}
    if not signals:
        return 0.0
    s = 0.0

    github = signals.get("github") or {}
    if github.get("username"):
        contribs = github.get("contributions_last_year", 0) or 0
        stars   = github.get("total_stars", 0) or 0
        if contribs >= 200:
            s += 0.35
        elif contribs >= 50:
            s += 0.20
        if stars >= 50:
            s += 0.20
        elif stars >= 10:
            s += 0.10

    pub = signals.get("publications") or []
    if pub:
        s += min(0.30, 0.10 * len(pub))

    pat = signals.get("patents") or []
    if pat:
        s += min(0.20, 0.07 * len(pat))

    sp  = signals.get("stackoverflow") or {}
    if (sp.get("reputation") or 0) >= 1000:
        s += 0.10

    kaggle = signals.get("kaggle") or {}
    if kaggle.get("username"):
        medals = kaggle.get("medals", 0) or 0
        if medals > 0:
            s += min(0.20, 0.05 * medals)

    return min(1.0, s)


# ---------------------------------------------------------------------------
# Public API — this is what ranker.py imports
# ---------------------------------------------------------------------------

def score(candidate, weights=None):
    """Return a single float score in [0, 1] for the given candidate dict.

    Parameters
    ----------
    candidate : dict
        One parsed line from candidates.jsonl
    weights : dict | None
        Custom weight overrides.  Falls back to DEFAULT_WEIGHTS.

    Returns
    -------
    float
        Weighted composite score in [0, 1].
    """
    w = weights or DEFAULT_WEIGHTS
    profile = candidate.get("profile", {}) or {}
    history = candidate.get("career_history", []) or []
    skills  = candidate.get("skills", []) or []

    return (
        w["skills"]        * _score_skills(skills)
        + w["experience"]  * _score_experience(profile)
        + w["company"]     * _score_company(history)
        + w["behavioral"]  * _score_behavioral(candidate)
        + w["notice_period"] * _score_notice_period(profile)
        + w["location"]    * _score_location(profile)
    )
