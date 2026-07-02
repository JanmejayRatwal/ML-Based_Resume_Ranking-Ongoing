"""
rule_based_judge.py — Detailed candidate reason generation based on Job Description

This module generates 1-2 sentence explanations for each candidate based on:
  1. Matched skills from JD keywords
  2. Years of experience and company background
  3. Location fit
  4. Notice period
  5. Behavioral signals (GitHub, publications, patents, etc.)

Public API:
    generate_explanations(top100_clean) -> list[str]
        Returns a list of reason strings, one per candidate
"""

import logging

logger = logging.getLogger(__name__)

# Preferred locations from JD
PREFERRED_LOCATIONS = {
    "pune", "noida", "delhi", "hyderabad", "mumbai", "bangalore", "bengaluru",
    "gurgaon", "gurugram", "remote", "anywhere", "india",
}

# JD Key Skills & Requirements
JD_KEYWORDS = {
    "python", "pytorch", "tensorflow", "jax", "llm", "large language model",
    "machine learning", "deep learning", "nlp", "natural language processing",
    "embeddings", "retrieval", "ranking", "vector", "rag",
    "evaluation", "ndcg", "mrr", "map", "metrics", "benchmark",
    "pinecone", "weaviate", "qdrant", "milvus", "opensearch", "elasticsearch",
    "faiss", "chromadb", "pgvector", "transformer", "agent", "agents",
    "reinforcement learning", "cuda", "kubernetes", "docker",
}

# Tier 1 companies (high value)
TIER_1_COMPANIES = {
    "google", "deepmind", "meta", "facebook", "microsoft", "amazon", "aws",
    "apple", "openai", "anthropic", "nvidia", "tesla",
}

# Tier 2 companies (AI/ML focused)
TIER_2_COMPANIES = {
    "scale ai", "huggingface", "weights & biases", "cohere", "mistral",
    "stability ai", "pinecone", "weaviate", "langchain", "perplexity",
}


# Vector DB & Retrieval Systems
VECTOR_DBS = {
    "pinecone", "weaviate", "qdrant", "milvus", "opensearch",
    "elasticsearch", "faiss", "vector", "chromadb", "pgvector",
}

EMBEDDING_MODELS = {
    "sentence-transformers", "openai", "bge", "e5", "embeddings",
}

# Red flags from JD (what to avoid)
RED_FLAGS = {
    "langchain", "marketing", "consultant", "academic", "research-only",
}

# Company Tiers (from score_computer.py)
TIER_1_COMPANIES = {
    "google", "deepmind", "meta", "facebook", "microsoft", "amazon", "aws",
    "apple", "openai", "anthropic", "nvidia", "tesla", "uber", "airbnb",
}

TIER_2_COMPANIES = {
    "scale ai", "huggingface", "weights & biases", "cohere", "mistral",
    "stability ai", "pinecone", "weaviate", "langchain", "perplexity",
}


def _extract_skills(candidate: dict) -> set:
    """Extract all skills from candidate profile."""
    skills = set()
    for s in candidate.get("skills", []) or []:
        skill_name = (s.get("skill_name") or s.get("name") or "").strip().lower()
        if skill_name:
            skills.add(skill_name)
    return skills


def _extract_companies(candidate: dict) -> list:
    """Extract company names from career history."""
    companies = []
    for job in candidate.get("career_history", []) or []:
        company = (job.get("company") or "").strip().lower()
        if company:
            companies.append(company)
    return companies


def _get_matched_skills(skills: set) -> list:
    """Get matched skills that align with JD keywords."""
    matched = []
    for skill in skills:
        if any(kw in skill for kw in JD_KEYWORDS):
            matched.append(skill.replace("_", " ").title())
    return matched[:5]  # Return top 5


def _get_top_companies(companies: list) -> list:
    """Get top tier companies from career history."""
    tier1 = [c for c in companies if c in TIER_1_COMPANIES]
    tier2 = [c for c in companies if c in TIER_2_COMPANIES]
    
    top = tier1 if tier1 else tier2
    return [c.replace("_", " ").title() for c in top[:2]]


def _get_behavioral_badges(candidate: dict) -> list:
    """Extract behavioral signal badges."""
    badges = []
    signals = candidate.get("redrob_signals", {}) or {}
    
    github = signals.get("github", {}) or {}
    if github.get("contributions_last_year", 0) and github.get("contributions_last_year") >= 50:
        badges.append("active-gh")
    
    if signals.get("publications"):
        badges.append("published")
    
    if signals.get("patents"):
        badges.append("patents")
    
    kaggle = signals.get("kaggle", {}) or {}
    if kaggle.get("medals", 0):
        badges.append("kaggle")
    
    return badges


def generate_reason(candidate: dict, breakdown: dict, score: float) -> str:
    """
    Generate 1-2 non-templated sentences describing why this candidate fits.
    
    Args:
        candidate: Candidate dictionary
        breakdown: Dictionary with 'matched_skills', 'top_companies', 'badges'
        score: Numerical score (0-1)
    
    Returns:
        1-2 sentence explanation
    """
    profile = candidate.get("profile", {}) or {}
    name = profile.get("anonymized_name") or "Candidate"
    parts = []

    # Matched skills
    matched = breakdown.get("matched_skills", [])
    if matched:
        sample = ", ".join(matched[:4])
        parts.append(f"Strong skill match on {sample}")

    # Years of experience
    years = profile.get("years_of_experience", 0) or 0
    if years >= 5:
        parts.append(f"{years}+ years of relevant engineering experience")
    elif years >= 2:
        parts.append(f"{years} years of hands-on experience")

    # Top companies
    top_comps = breakdown.get("top_companies", [])
    if top_comps:
        parts.append(f"background at {', '.join(top_comps[:2])}")

    # Location
    loc = profile.get("location")
    if loc and any(p in loc.lower() for p in PREFERRED_LOCATIONS):
        parts.append(f"based in {loc}")

    # Notice period
    np_days = profile.get("notice_period_days")
    if np_days is not None and np_days <= 30:
        parts.append(f"{np_days}-day notice period enables fast onboarding")

    # Behavioral badges
    badges = breakdown.get("badges", [])
    if badges:
        badge_pretty = {
            "active-gh": "active GitHub",
            "oss-impact": "open-source impact",
            "published": "research publications",
            "patents": "filed patents",
            "so-top": "StackOverflow top contributor",
            "kaggle": "Kaggle competition medals",
        }
        names = [badge_pretty.get(b, b) for b in badges[:2]]
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


def build_breakdown(candidate: dict) -> dict:
    """Build detailed breakdown data for a candidate."""
    skills = _extract_skills(candidate)
    companies = _extract_companies(candidate)
    
    return {
        "matched_skills": _get_matched_skills(skills),
        "top_companies": _get_top_companies(companies),
        "badges": _get_behavioral_badges(candidate),
    }


def generate_explanations(top100: list) -> list:
    """
    Generate reasons for all top 100 candidates.
    
    Args:
        top100: List of (score, candidate_dict) tuples from merge_results()
    
    Returns:
        List of (reason_str, breakdown_dict) tuples, one per candidate
    """
    explanations = []
    
    for rank, (score, candidate) in enumerate(top100, start=1):
        breakdown = build_breakdown(candidate)
        reason = generate_reason(candidate, breakdown, score)
        explanations.append((reason, breakdown))
        
        if rank % 20 == 0:
            logger.info(f"Generated reasons for {rank}/{len(top100)} candidates")
    
    logger.info(f"Completed generating reasons for all {len(top100)} candidates")
    return explanations
