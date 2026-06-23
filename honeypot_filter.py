"""
honeypot_filter.py — Honeypot candidate detection module

Public API:
    detect_honeypots(candidate: dict) -> list[str]
        Returns a list of human-readable reason strings.
        Empty list means the candidate is NOT a honeypot.

Rules are grouped in three categories:
    A — Career / profile integrity  (from job_description.docx disqualifiers)
    B — Data integrity              (fake or inflated data in the candidate record)
    C — Behavioral signals          (from redrob_signals fields)
"""

from datetime import datetime, date

# ── Constants ─────────────────────────────────────────────────────────────────

PRESENT_DATE = date(2026, 6, 6)

# IT-services / outsourcing firms whose candidates are flagged if they have
# ZERO product-company experience anywhere in their career history.
CONSULTING_FIRMS = {
    "tcs", "tata consultancy services",
    "infosys", "wipro", "accenture",
    "cognizant", "cognizant technology solutions",
    "capgemini", "hcl", "hcl technologies",
    "mindtree", "mphasis", "tech mahindra",
    "hexaware", "l&t infotech", "ltimindtree",
    "igate", "patni", "mastech",
    "niit technologies",
}

# Titles that indicate a non-technical role (these candidates are honeypots if
# they also list AI keywords in their skills).
NON_TECH_TITLE_KEYWORDS = {
    "marketing manager", "operations manager", "customer support",
    "business analyst", "hr", "human resources", "recruiter",
    "sales manager", "account manager", "product marketing",
    "program manager", "project manager", "scrum master",
}

# AI / ML keywords used to detect keyword stuffing
AI_KEYWORDS = {
    "python", "pytorch", "tensorflow", "jax", "llm", "large language model",
    "machine learning", "deep learning", "nlp", "natural language processing",
    "computer vision", "transformer", "rag", "retrieval", "agent",
    "reinforcement learning", "mlops", "cuda", "triton",
    "langchain", "llamaindex", "huggingface", "generative ai", "genai",
    "embedding", "vector database", "faiss", "pinecone", "weaviate",
    "diffusion", "recommendation", "ranking", "search",
}

# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _days_since(date_str):
    """Return how many days ago a date string was (relative to PRESENT_DATE)."""
    d = _parse_date(date_str)
    if d is None:
        return None
    return (PRESENT_DATE - d).days


def _is_consulting_firm(company_name: str) -> bool:
    return (company_name or "").strip().lower() in CONSULTING_FIRMS


# ── Rule implementations ──────────────────────────────────────────────────────

def _rule_A1_title_skill_mismatch(profile, skills):
    """A1: Non-tech current title but lists AI/ML skills."""
    title = (profile.get("current_title") or profile.get("headline") or "").lower()
    if not any(kw in title for kw in NON_TECH_TITLE_KEYWORDS):
        return None
    skill_names = {(s.get("name") or s.get("skill_name") or "").lower() for s in skills}
    ai_matches = [kw for kw in AI_KEYWORDS if any(kw in sn for sn in skill_names)]
    if len(ai_matches) >= 3:
        return (
            f"Title '{profile.get('current_title', title)}' is non-technical "
            f"but lists {len(ai_matches)} AI/ML skills — possible keyword stuffing."
        )
    return None


def _rule_A2_consulting_only(history):
    """A2: Every job is at a known IT-services firm — no product-company experience."""
    if not history:
        return None
    if all(_is_consulting_firm(j.get("company", "")) for j in history):
        return "Entire career is at IT-services / outsourcing firms with no product-company experience."
    return None


def _rule_A3_keyword_stuffer(skills, history):
    """A3: 7+ AI keywords in skills but zero AI-related words in any job description."""
    skill_names = {(s.get("name") or s.get("skill_name") or "").lower() for s in skills}
    ai_skill_count = sum(1 for kw in AI_KEYWORDS if any(kw in sn for sn in skill_names))
    if ai_skill_count < 7:
        return None
    all_desc = " ".join(
        (j.get("description") or j.get("title") or "").lower() for j in history
    )
    if not any(kw in all_desc for kw in AI_KEYWORDS):
        return (
            f"{ai_skill_count} AI/ML skills listed but no AI/ML language "
            "appears in any job description — likely keyword stuffing."
        )
    return None


def _rule_A4_job_hopper(history):
    """A4: 3+ moves where each tenure ≤ 18 months and total jobs ≥ 4."""
    if len(history) < 4:
        return None
    short = sum(1 for j in history if (j.get("duration_months") or 999) <= 18)
    if short >= 3:
        return (
            f"{short} of {len(history)} jobs lasted ≤ 18 months — "
            "high job-hopping pattern unlikely to commit for 3+ years."
        )
    return None


def _rule_B1_skill_duration_fraud(skills):
    """B1: Expert/advanced skill with 0 months duration."""
    for s in skills:
        prof = (s.get("proficiency") or "").lower()
        dur = s.get("duration_months") or 0
        name = s.get("name") or s.get("skill_name") or "Unknown"
        if prof in ("expert", "advanced") and dur == 0:
            return f"Skill '{name}' is marked '{prof}' but has 0 months of experience."
    return None


def _rule_B2_timeline_impossible(history):
    """B2: Stated job duration exceeds actual date span by more than 12 months."""
    for j in history:
        dur = j.get("duration_months") or 0
        if dur <= 0 or not j.get("start_date"):
            continue
        start = _parse_date(j["start_date"])
        end_raw = j.get("end_date")
        end = _parse_date(end_raw) if end_raw else PRESENT_DATE
        if not start or not end:
            continue
        span = (end.year - start.year) * 12 + (end.month - start.month)
        if span > 0 and dur > span + 12:
            return (
                f"Job at {j.get('company', '?')}: stated {dur} months "
                f"but date span is only {span} months."
            )
    return None


def _rule_B3_experience_inflation(profile, history):
    """B3: A single job's duration exceeds total stated experience."""
    total_mo = (profile.get("years_of_experience") or 0) * 12
    if total_mo <= 0:
        return None
    for j in history:
        dur = j.get("duration_months") or 0
        if dur > total_mo:
            return (
                f"Job at {j.get('company', '?')}: {dur} months stated "
                f"but total experience is only {int(total_mo)} months."
            )
    return None


def _rule_C1_ghost_candidate(signals):
    """C1: Last active > 180 days ago."""
    days = _days_since(signals.get("last_active_date"))
    if days is not None and days > 180:
        return f"Last active {days} days ago — candidate appears unavailable."
    return None


def _rule_C2_non_responsive(signals):
    """C2: Recruiter response rate < 10%."""
    rr = signals.get("recruiter_response_rate")
    if rr is not None and rr < 0.10:
        return f"Recruiter response rate is {rr:.0%} — candidate rarely responds."
    return None


def _rule_C3_interview_ghoster(signals):
    """C3: Interview completion rate < 30%."""
    icr = signals.get("interview_completion_rate")
    if icr is not None and icr < 0.30:
        return f"Interview completion rate is {icr:.0%} — candidate frequently ghosts interviews."
    return None


def _rule_C4_not_available(signals):
    """C4: Not open to work, zero applications in 30d, inactive > 90 days."""
    open_flag = signals.get("open_to_work_flag")
    apps = signals.get("applications_submitted_30d") or 0
    days = _days_since(signals.get("last_active_date"))
    if (
        open_flag is False
        and apps == 0
        and days is not None
        and days > 90
    ):
        return (
            f"Not open to work, zero applications in 30 days, "
            f"and inactive for {days} days — candidate not actively seeking."
        )
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def detect_honeypots(candidate: dict) -> list:
    """
    Analyse a candidate record and return a list of honeypot reason strings.
    An empty list means the candidate is NOT flagged as a honeypot.

    Parameters
    ----------
    candidate : dict
        One parsed candidate record from candidates.jsonl

    Returns
    -------
    list[str]
        Human-readable reasons. Empty = clean candidate.
    """
    profile  = candidate.get("profile", {})         or {}
    history  = candidate.get("career_history", [])  or []
    skills   = candidate.get("skills", [])          or []
    signals  = candidate.get("redrob_signals", {})  or {}

    checkers = [
        _rule_A1_title_skill_mismatch(profile, skills),
        _rule_A2_consulting_only(history),
        _rule_A3_keyword_stuffer(skills, history),
        _rule_A4_job_hopper(history),
        _rule_B1_skill_duration_fraud(skills),
        _rule_B2_timeline_impossible(history),
        _rule_B3_experience_inflation(profile, history),
        _rule_C1_ghost_candidate(signals),
        _rule_C2_non_responsive(signals),
        _rule_C3_interview_ghoster(signals),
        _rule_C4_not_available(signals),
    ]

    return [reason for reason in checkers if reason is not None]


def is_honeypot(candidate: dict) -> bool:
    """Convenience wrapper — returns True if any honeypot rule triggers."""
    return len(detect_honeypots(candidate)) > 0
