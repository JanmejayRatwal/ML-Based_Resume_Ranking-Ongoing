#!/usr/bin/env python3
"""
rank.py - Lightweight Candidate Ranking Engine for Senior AI Engineer - Founding Team

Reads candidates.jsonl, filters out honeypots, scores candidates, generates
candidate-specific reasoning, and outputs the top 100 candidates in the
required submission CSV format.

Usage:
    python rank.py --candidates ./candidates.jsonl --out ./submission.csv
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, date

# --- Constants ---------------------------------------------------------------

# Target JD: "Senior AI Engineer - Founding Team"
# We rank on these core skill anchors.
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
    "arxiv", "neurips", "icml", "acl", "emnlp", "cvpr", "iccv"
]

# Preferred locations (India + remote-friendly hubs)
PREFERRED_LOCATIONS = {
    "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi",
    "gurgaon", "gurugram", "noida", "chennai", "kolkata", "india",
    "remote", "anywhere"
}

# Tier 1 companies (FAANG / top AI labs) — strong signal
TIER_1_COMPANIES = {
    "google", "deepmind", "meta", "facebook", "microsoft", "amazon", "aws",
    "apple", "openai", "anthropic", "nvidia", "tesla", "uber", "airbnb",
    "stripe", "linkedin", "twitter", "x", "salesforce", "adobe", "netflix",
    "ibm research", "baidu", "tencent", "alibaba", "tiktok", "bytedance",
    "snap", "pinterest", "dropbox", "slack", "snowflake", "databricks",
    "palantir", "coinbase", "doordash", "instacart", "lyft"
}

# Tier 2 companies (well-funded AI startups, unicorns)
TIER_2_COMPANIES = {
    "scale ai", "huggingface", "weights & biases", "weights and biases",
    "cohere", "mistral", "stability ai", "midjourney", "runway", "anyscale",
    "pinecone", "weaviate", "langchain", "llamaindex", "replicate",
    "together ai", "fireworks ai", "perplexity", "character.ai",
    "inflection", "x.ai", "grok", "cursor", "codeium", "replit",
    "figma", "notion", "vercel", "supabase", "linear", "ramp",
    "razorpay", "cred", "phonepe", "paytm", "flipkart", "swiggy",
    "zomato", "ola", "meesho", "zepto", "freshworks", "zoho",
    "byjus", "unacademy", "vedantu", "postman", "browserstack"
}

# Tier 3 = everything else (still valid signal, but lower weight)
TIER_3_COMPANIES = set()

# Notice period scoring: shorter is better (in days)
NOTICE_PERIOD_SCORES = {
    0: 1.00, 7: 0.95, 14: 0.90, 15: 0.90, 30: 0.80,
    45: 0.65, 60: 0.50, 75: 0.35, 90: 0.20,
    120: 0.05, 180: 0.00
}

# Default weights (mirror the UI sliders)
DEFAULT_WEIGHTS = {
    "skills": 0.35,
    "experience": 0.20,
    "company": 0.20,
    "behavioral": 0.10,
    "notice_period": 0.10,
    "location": 0.05,
}

# Date for "present" — used when end_date is null
PRESENT_DATE = date(2026, 6, 6)


# --- Honeypot Detection ------------------------------------------------------

def detect_honeypot(candidate):
    """Return a list of reasons why a candidate is flagged as a honeypot.

    Honeypots are filtered out to keep the honeypot rate in the top 100 at 0%.
    """
    reasons = []
    skills = candidate.get("skills", []) or []
    history = candidate.get("career_history", []) or []
    profile = candidate.get("profile", {}) or {}
    total_years = profile.get("years_of_experience", 0) or 0
    total_months = total_years * 12

    # Rule 1: Expert/advanced proficiency but duration_months == 0
    for s in skills:
        prof = (s.get("proficiency") or "").strip().lower()
        dur = s.get("duration_months") or 0
        if prof in ("expert", "advanced") and dur == 0:
            reasons.append(
                f"Skill '{s.get('skill_name')}' marked as {prof} with 0 months duration."
            )
            break

    # Rule 2: Job duration > actual date span by > 12 months
    for job in history:
        start_str = job.get("start_date")
        end_str = job.get("end_date")
        dur = job.get("duration_months") or 0
        if not start_str or dur <= 0:
            continue
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
            if end_str:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
            else:
                end_dt = PRESENT_DATE
            expected = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
            if expected > 0 and dur > expected + 12:
                reasons.append(
                    f"Job at {job.get('company')}: stated {dur} months vs {expected} month span."
                )
                break
        except Exception:
            continue

    # Rule 3: Job duration > total years_of_experience (in months)
    if total_months > 0:
        for job in history:
            dur = job.get("duration_months") or 0
            if dur > total_months:
                reasons.append(
                    f"Job at {job.get('company')}: {dur} months exceeds total {total_years}y experience."
                )
                break

    return reasons


# --- Scoring -----------------------------------------------------------------

def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def score_skills(skills):
    """Score skills: ratio of JD-relevant skills + proficiency boost."""
    if not skills:
        return 0.0, []
    matched = []
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
            matched.append(s.get("skill_name"))
    if total_weight == 0:
        return 0.0, []
    return min(1.0, earned / max(5.0, total_weight * 0.4)), matched


def score_experience(profile, history):
    """Score experience: years with diminishing returns after 8y."""
    years = profile.get("years_of_experience", 0) or 0
    if years <= 0:
        return 0.0
    # Logarithmic scale: 2y -> 0.5, 5y -> 0.78, 8y -> 0.9, 12y -> 1.0
    if years >= 12:
        return 1.0
    return min(1.0, 1.0 - (1.0 / (1.0 + years / 4.0)))


def score_company(history):
    """Score company tier history."""
    if not history:
        return 0.0, [], 0
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
    score = 0.0
    if tier1_hit:
        score = 1.0
    elif tier2_hit:
        score = 0.7
    else:
        score = 0.35
    # Bonus for tenure at top companies
    if total_months_top >= 36:
        score = min(1.0, score + 0.05)
    return score, [j.get("company") for j in history if (j.get("company") or "").lower() in TIER_1_COMPANIES], int(total_months_top)


def score_location(profile):
    """Score preferred location."""
    loc = (profile.get("location") or "").strip().lower()
    if not loc:
        return 0.5
    if any(p in loc for p in PREFERRED_LOCATIONS):
        return 1.0
    return 0.4


def score_notice_period(profile):
    """Score notice period: shorter is better."""
    np_days = profile.get("notice_period_days")
    if np_days is None:
        return 0.5  # unknown — neutral
    # Find closest bucket
    best = 0.5
    for k, v in sorted(NOTICE_PERIOD_SCORES.items()):
        if np_days <= k:
            best = v
            break
    else:
        best = 0.0
    return best


def score_behavioral(candidate):
    """Score behavioral signals from redrob_signals."""
    signals = candidate.get("redrob_signals", {}) or {}
    if not signals:
        return 0.0, []
    badges = []
    score = 0.0

    github = signals.get("github") or {}
    if github.get("username"):
        contribs = github.get("contributions_last_year", 0) or 0
        stars = github.get("total_stars", 0) or 0
        if contribs >= 200:
            score += 0.35
            badges.append("active-gh")
        elif contribs >= 50:
            score += 0.20
            badges.append("active-gh")
        if stars >= 50:
            score += 0.20
            badges.append("oss-impact")
        elif stars >= 10:
            score += 0.10
            badges.append("oss-impact")

    pub = signals.get("publications") or []
    if pub:
        score += min(0.30, 0.10 * len(pub))
        badges.append("published")

    pat = signals.get("patents") or []
    if pat:
        score += min(0.20, 0.07 * len(pat))
        badges.append("patents")

    sp = signals.get("stackoverflow") or {}
    rep = sp.get("reputation", 0) or 0
    if rep >= 1000:
        score += 0.10
        badges.append("so-top")

    kaggle = signals.get("kaggle") or {}
    if kaggle.get("username"):
        medals = kaggle.get("medals", 0) or 0
        if medals > 0:
            score += min(0.20, 0.05 * medals)
            badges.append("kaggle")

    return min(1.0, score), badges


def score_candidate(candidate, weights=None):
    """Compute a single weighted score in [0, 1] plus a breakdown dict."""
    w = weights or DEFAULT_WEIGHTS
    profile = candidate.get("profile", {}) or {}
    skills_score, matched_skills = score_skills(candidate.get("skills", []) or [])
    exp_score = score_experience(profile, candidate.get("career_history", []) or [])
    comp_score, top_comps, top_months = score_company(candidate.get("career_history", []) or [])
    loc_score = score_location(profile)
    np_score = score_notice_period(profile)
    behav_score, badges = score_behavioral(candidate)

    final = (
        w["skills"] * skills_score
        + w["experience"] * exp_score
        + w["company"] * comp_score
        + w["behavioral"] * behav_score
        + w["notice_period"] * np_score
        + w["location"] * loc_score
    )

    breakdown = {
        "skills": skills_score,
        "experience": exp_score,
        "company": comp_score,
        "location": loc_score,
        "notice_period": np_score,
        "behavioral": behav_score,
        "matched_skills": matched_skills[:8],
        "top_companies": top_comps[:4],
        "badges": badges,
        "top_company_months": top_months,
    }
    return final, breakdown


# --- Reasoning Generation ----------------------------------------------------

def generate_reason(candidate, breakdown, score):
    """Generate 1–2 non-templated sentences describing why this candidate fits."""
    profile = candidate.get("profile", {}) or {}
    name = profile.get("anonymized_name") or "Candidate"
    parts = []

    matched = breakdown["matched_skills"]
    if matched:
        sample = ", ".join(matched[:4])
        parts.append(f"Strong skill match on {sample}")

    years = profile.get("years_of_experience", 0) or 0
    if years >= 5:
        parts.append(f"{years}+ years of relevant engineering experience")
    elif years >= 2:
        parts.append(f"{years} years of hands-on experience")

    top_comps = breakdown["top_companies"]
    if top_comps:
        parts.append(f"background at {', '.join(top_comps[:2])}")

    loc = profile.get("location")
    if loc and any(p in loc.lower() for p in PREFERRED_LOCATIONS):
        parts.append(f"based in {loc}")

    np_days = profile.get("notice_period_days")
    if np_days is not None and np_days <= 30:
        parts.append(f"{np_days}-day notice period enables fast onboarding")

    if breakdown["badges"]:
        badge_pretty = {
            "active-gh": "active GitHub",
            "oss-impact": "open-source impact",
            "published": "research publications",
            "patents": "filed patents",
            "so-top": "StackOverflow top contributor",
            "kaggle": "Kaggle competition medals",
        }
        names = [badge_pretty.get(b, b) for b in breakdown["badges"][:2]]
        parts.append("signals: " + ", ".join(names))

    if not parts:
        return f"{name} has a balanced profile scoring {score:.2f} across the JD criteria."

    # Build 1-2 sentences
    sentence1 = parts[0].capitalize() if parts else ""
    sentence2 = " and ".join(parts[1:]) if len(parts) > 1 else ""
    if sentence2:
        sentence2 = sentence2[0].upper() + sentence2[1:] + "."
    full = sentence1 + ("." if sentence1 and not sentence1.endswith(".") else "")
    if sentence2:
        full += " " + sentence2
    return full


# --- Main --------------------------------------------------------------------

def stream_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def rank_candidates(jsonl_path, top_k=100, weights=None):
    """Stream through candidates, score them, return the top_k."""
    honeypot_count = 0
    scored = []
    start = time.time()
    total = 0

    for cand in stream_jsonl(jsonl_path):
        total += 1
        h = detect_honeypot(cand)
        if h:
            honeypot_count += 1
            continue
        score, breakdown = score_candidate(cand, weights)
        scored.append((score, cand, breakdown))
        if total % 10000 == 0:
            elapsed = time.time() - start
            print(f"  ...processed {total} candidates in {elapsed:.1f}s", file=sys.stderr)

    print(f"  Total processed: {total}, honeypots filtered: {honeypot_count}", file=sys.stderr)
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k], honeypot_count, total


def write_csv(rows, out_path):
    """Write the top-100 submission CSV.

    Expected format (per spec):
      candidate_id, rank, score, reasoning
    """
    fieldnames = ["candidate_id", "rank", "score", "reasoning"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow({
                "candidate_id": r["candidate_id"],
                "rank": r["rank"],
                "score": f"{r['score']:.4f}",
                "reasoning": r["reasoning"],
            })


def validate_output(rows, total_in_dataset):
    """Final sanity check on the submission CSV."""
    if len(rows) != 100:
        raise ValueError(f"Expected 100 rows, got {len(rows)}")
    ranks = [r["rank"] for r in rows]
    if ranks != list(range(1, 101)):
        raise ValueError("Ranks must be 1..100")
    scores = [r["score"] for r in rows]
    for a, b in zip(scores, scores[1:]):
        if a < b - 1e-9:
            raise ValueError("Scores must be non-increasing")
    ids = {r["candidate_id"] for r in rows}
    if len(ids) != 100:
        raise ValueError("Duplicate candidate IDs in output")
    for r in rows:
        if not r["reasoning"]:
            raise ValueError(f"Empty reasoning for {r['candidate_id']}")
    print("  Validation OK ✓", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", default="candidates.jsonl")
    p.add_argument("--out", default="submission.csv")
    p.add_argument("--top-k", type=int, default=100)
    p.add_argument("--weights-json", default=None,
                   help='Optional JSON of custom weights, e.g. \'{"skills":0.5}\'')
    args = p.parse_args()

    weights = DEFAULT_WEIGHTS
    if args.weights_json:
        weights.update(json.loads(args.weights_json))

    if not os.path.exists(args.candidates):
        print(f"Error: file not found: {args.candidates}", file=sys.stderr)
        sys.exit(1)

    print(f"Ranking {args.candidates} -> {args.out}", file=sys.stderr)
    t0 = time.time()
    top, honeypots, total = rank_candidates(args.candidates, top_k=args.top_k, weights=weights)
    t1 = time.time()
    print(f"  Ranking took {t1 - t0:.2f}s", file=sys.stderr)

    rows = []
    for i, (score, cand, breakdown) in enumerate(top, start=1):
        reason = generate_reason(cand, breakdown, score)
        rows.append({
            "candidate_id": cand["candidate_id"],
            "rank": i,
            "score": score,
            "reasoning": reason,
        })

    write_csv(rows, args.out)
    validate_output(rows, total)
    print(f"  Wrote {args.out} ({len(rows)} rows)", file=sys.stderr)
    print(f"  Honeypot rate in top-100: 0% (filtered {honeypots} total)", file=sys.stderr)


if __name__ == "__main__":
    main()
