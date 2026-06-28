#!/usr/bin/env python3
"""
Redrob Intelligent Candidate Ranking System
============================================
Built for: Senior AI Engineer — Founding Team @ Redrob AI
Location:  Pune / Noida, India (Hybrid)
YOE Band:  5–9 years (flexible for strong signals)

CPU-only | No network | < 5 min | < 16 GB RAM
Zero external dependencies — stdlib only.
"""

import gzip, json, csv, sys, time, argparse, re
from datetime import date, datetime
from collections import defaultdict

# ─── REAL JOB DESCRIPTION (from job_description.docx) ────────────────────────
JD = {
    "title": "Senior AI Engineer — Founding Team",
    "company": "Redrob AI (Series A)",
    "locations": ["pune", "noida", "hyderabad", "mumbai", "delhi", "bangalore",
                  "bengaluru", "gurgaon", "gurugram", "ncr"],
    "yoe_min": 5, "yoe_max": 9,

    # MUST-HAVE from JD — embeddings retrieval, vector DBs, Python, eval frameworks
    "required_skills": [
        "embeddings", "vector database", "vector databases", "vector db",
        "pinecone", "weaviate", "qdrant", "milvus", "faiss", "opensearch",
        "elasticsearch", "hybrid search", "dense retrieval", "semantic search",
        "sentence transformers", "sentence-transformers", "bge", "e5",
        "python", "retrieval", "information retrieval",
        "ranking", "learning to rank", "ndcg", "mrr", "map", "a/b testing",
        "recommendation", "recommendation systems", "search",
    ],

    # PREFERRED — nice to have
    "preferred_skills": [
        "llm", "large language model", "fine-tuning", "lora", "qlora", "peft",
        "rag", "transformers", "nlp", "pytorch", "tensorflow",
        "xgboost", "lightgbm", "machine learning", "deep learning",
        "mlops", "docker", "kubernetes", "spark", "kafka",
        "distributed systems", "inference optimization",
    ],

    # STRONG POSITIVE title signals
    "strong_titles": [
        "machine learning engineer", "ml engineer", "ai engineer",
        "applied scientist", "research engineer", "nlp engineer",
        "search engineer", "recommendation", "ranking engineer",
        "data scientist", "senior engineer", "staff engineer", "principal engineer",
    ],

    # WEAK titles — adjacent but not core
    "adjacent_titles": [
        "data engineer", "software engineer", "backend engineer",
        "full stack", "platform engineer", "mlops engineer",
    ],

    # DISQUALIFIER titles — JD explicitly says no
    "disqualified_titles": [
        "marketing", "accountant", "hr ", "civil engineer", "mechanical engineer",
        "operations manager", "customer support", "graphic designer",
        "project manager", "sales", "finance", "recruiter",
        "frontend engineer", "mobile developer", ".net developer",
        "java developer", "qa engineer",
    ],

    # Companies JD says are bad fits (pure consulting)
    "bad_companies": [
        "tcs", "tata consultancy", "infosys", "wipro", "accenture",
        "cognizant", "capgemini", "hcl", "tech mahindra", "mindtree",
        "mphasis", "hexaware", "l&t infotech",
    ],

    "preferred_work_modes": ["hybrid", "remote", "flexible"],
    "preferred_notice_days": 30,
    "salary_budget_lpa": 60,
}

# ─── COMPONENT WEIGHTS  (must sum to 1.0) ─────────────────────────────────────
W = {
    "title_fit":       0.26,   # Is the title actually ML/AI/Search?
    "skill_depth":     0.28,   # JD required + preferred skills with trust
    "experience_fit":  0.12,   # YOE in 5–9 band
    "career_quality":  0.14,   # Company quality, trajectory, not pure consulting
    "availability":    0.12,   # Engagement signals — active, responsive, open
    "education":       0.05,   # Tier + field
    "location":        0.03,   # Pune/Noida/Delhi NCR preferred
}

# ─── SKILL NORMALISATION ──────────────────────────────────────────────────────
SKILL_ALIASES = {
    "vector db": "vector database", "vector dbs": "vector database",
    "sentence transformer": "sentence transformers",
    "llms": "llm", "large language models": "llm", "gpt": "llm", "chatgpt": "llm",
    "bert": "transformers", "nlp": "nlp",
    "sklearn": "machine learning", "scikit-learn": "machine learning",
    "pytorch": "pytorch", "tensorflow": "tensorflow",
    "rag": "rag", "retrieval augmented generation": "rag",
    "embedding": "embeddings", "text embeddings": "embeddings",
    "semantic search": "semantic search", "dense retrieval": "dense retrieval",
    "learning to rank": "learning to rank", "ltr": "learning to rank",
    "a/b testing": "a/b testing", "ab testing": "a/b testing",
    "recommendation system": "recommendation systems",
    "recsys": "recommendation systems",
}

def norm_skill(name: str) -> str:
    n = name.lower().strip()
    return SKILL_ALIASES.get(n, n)

JD_REQ_SET  = {norm_skill(s) for s in JD["required_skills"]}
JD_PREF_SET = {norm_skill(s) for s in JD["preferred_skills"]}

# ─── HONEYPOT DETECTION ───────────────────────────────────────────────────────
def is_honeypot(cand: dict) -> bool:
    """Detect subtly impossible profiles."""
    profile = cand.get("profile", {})
    skills  = cand.get("skills", [])
    career  = cand.get("career_history", [])
    yoe     = profile.get("years_of_experience", 0)
    signals = cand.get("redrob_signals", {})

    # Flag 1: Expert in many skills with 0 duration
    expert_zero = sum(1 for s in skills
                      if s.get("proficiency") == "expert"
                      and s.get("duration_months", 1) == 0)
    if expert_zero >= 4:
        return True

    # Flag 2: Total career months << claimed YOE
    total_months = sum(c.get("duration_months", 0) for c in career)
    if yoe > 4 and total_months < yoe * 12 * 0.5:
        return True

    # Flag 3: 10+ expert skills with very low total endorsements
    expert_count = sum(1 for s in skills if s.get("proficiency") == "expert")
    total_end    = sum(s.get("endorsements", 0) for s in skills)
    if expert_count >= 10 and total_end < 15:
        return True

    # Flag 4: Company name has year and start_date predates it
    for job in career:
        m = re.search(r"(20\d\d)", job.get("company", ""))
        if m:
            try:
                if int(job.get("start_date", "2099")[:4]) < int(m.group(1)):
                    return True
            except Exception:
                pass

    return False

# ─── TITLE FIT SCORE ─────────────────────────────────────────────────────────
def score_title(cand: dict) -> tuple[float, str]:
    """Score how well the current title fits an AI/ML/Search engineering role."""
    title = cand.get("profile", {}).get("current_title", "").lower()

    # Hard disqualifiers from JD
    for bad in JD["disqualified_titles"]:
        if bad in title:
            return 0.05, f"title '{title}' is disqualified per JD"

    # Strong ML/AI/Search titles
    for good in JD["strong_titles"]:
        if good in title:
            return 1.0, f"strong title match: {title}"

    # Adjacent engineering titles
    for adj in JD["adjacent_titles"]:
        if adj in title:
            return 0.45, f"adjacent title: {title}"

    # Generic engineer / developer
    if any(t in title for t in ["engineer", "developer", "architect", "scientist"]):
        return 0.3, f"generic engineering title: {title}"

    return 0.1, f"non-engineering title: {title}"

# ─── SKILL DEPTH SCORE ───────────────────────────────────────────────────────
def score_skills(cand: dict) -> tuple[float, list]:
    """
    Score skill match with trust weighting.
    Trust = f(proficiency, endorsements, duration_months).
    Penalises keyword stuffing (expert + 0 months).
    JD explicitly warns about 'framework enthusiasts' — LangChain-only profiles score low.
    """
    skills = cand.get("skills", [])
    if not skills:
        return 0.0, []

    PROF = {"beginner": 0.25, "intermediate": 0.55, "advanced": 0.82, "expert": 1.0}
    matched_req, matched_pref = [], []

    for sk in skills:
        raw  = norm_skill(sk.get("name", ""))
        prof = PROF.get(sk.get("proficiency", "beginner"), 0.25)
        end  = sk.get("endorsements", 0)
        dur  = sk.get("duration_months", 0)

        # Honeypot trap: expert with 0 months = deflate hard
        if sk.get("proficiency") == "expert" and dur == 0:
            prof = 0.15

        trust = prof * 0.55 + min(1.0, end / 25) * 0.25 + min(1.0, dur / 24) * 0.20

        if raw in JD_REQ_SET:
            matched_req.append((sk.get("name",""), trust))
        elif raw in JD_PREF_SET:
            matched_pref.append((sk.get("name",""), trust))

    # Required: coverage × quality
    req_score = 0.0
    if matched_req:
        coverage = len(matched_req) / len(JD_REQ_SET)
        quality  = sum(t for _, t in matched_req) / len(matched_req)
        req_score = coverage * 0.55 + quality * 0.45

    # Preferred: bonus (capped)
    pref_score = min(0.35, len(matched_pref) / 10) if matched_pref else 0.0

    total = min(1.0, req_score * 0.78 + pref_score * 0.22)
    names = [n for n, _ in matched_req[:5]] + [n for n, _ in matched_pref[:2]]
    return round(total, 4), names

# ─── EXPERIENCE FIT ──────────────────────────────────────────────────────────
def score_experience(cand: dict) -> float:
    """Bell-curve centred on midpoint of 5–9 band (6–7yr sweet spot)."""
    yoe = cand.get("profile", {}).get("years_of_experience", 0)
    lo, hi = JD["yoe_min"], JD["yoe_max"]

    if lo <= yoe <= hi:
        mid  = (lo + hi) / 2
        dist = abs(yoe - mid) / ((hi - lo) / 2)
        return round(1.0 - dist * 0.12, 4)
    elif yoe > hi:
        # JD says overqualified researchers don't fit — gentle penalty
        return round(max(0.35, 1.0 - (yoe - hi) * 0.09), 4)
    else:
        return round(max(0.0, 1.0 - (lo - yoe) * 0.28), 4)

# ─── CAREER QUALITY ──────────────────────────────────────────────────────────
def score_career(cand: dict) -> tuple[float, str]:
    """
    Score company quality and career trajectory.
    JD explicitly penalises pure consulting (TCS, Infosys, Wipro, etc.)
    and values product-company experience with production ML.
    """
    career  = cand.get("career_history", [])
    profile = cand.get("profile", {})
    if not career:
        return 0.2, "no career history"

    # Product company signals — well-known product/startup brands
    product_cos = {
        "google", "meta", "microsoft", "amazon", "flipkart", "swiggy",
        "zomato", "razorpay", "phonepe", "cred", "meesho", "ola", "byju",
        "freshworks", "zoho", "postman", "groww", "zepto", "dunzo",
        "urban company", "sharechat", "dailyhunt", "dream11", "mpl",
        "ninjacart", "moglix", "lenskart", "policybazaar", "paytm",
        "instamojo", "cleartax", "khatabook", "slice", "fi money",
        "unacademy", "vedantu", "upgrad", "openai", "anthropic",
        "deepmind", "nvidia", "samsung", "qualcomm", "adobe", "salesforce",
        "uber", "airbnb", "linkedin", "twitter", "x.com", "netflix",
    }

    bad_cos = set(JD["bad_companies"])

    # Count pure-consulting stints
    total_months    = 0
    bad_months      = 0
    product_hits    = 0
    tenure_ok       = 0  # stints >= 12 months

    for job in career:
        company  = job.get("company", "").lower()
        dur      = job.get("duration_months", 0)
        total_months += dur

        if any(b in company for b in bad_cos):
            bad_months += dur
        if any(p in company for p in product_cos):
            product_hits += 1
        if dur >= 12:
            tenure_ok += 1

    # Penalise if >60% of career at consulting firms
    consulting_ratio = bad_months / max(total_months, 1)
    consult_penalty  = max(0.0, consulting_ratio - 0.3) * 1.5  # steep after 30%

    product_boost = min(0.5, product_hits * 0.2)
    tenure_score  = min(1.0, tenure_ok / max(len(career), 1))

    # Check current company
    current_co = profile.get("current_company", "").lower()
    if any(b in current_co for b in bad_cos):
        consult_penalty += 0.15

    score = max(0.0, min(1.0, 0.4 + product_boost + tenure_score * 0.3 - consult_penalty))
    note  = f"{product_hits} product-co stints; {int(consulting_ratio*100)}% consulting"
    return round(score, 4), note

# ─── AVAILABILITY SIGNALS ─────────────────────────────────────────────────────
def score_availability(cand: dict) -> tuple[float, str]:
    """
    Behavioral signals — JD explicitly says: weight these heavily.
    A perfect-on-paper candidate inactive for 6 months is not actually available.
    """
    s = cand.get("redrob_signals", {})
    notes = []
    subs  = []

    # 1. Open to work
    otw = s.get("open_to_work_flag", False)
    subs.append(1.0 if otw else 0.2)
    if otw: notes.append("open to work")

    # 2. Recency — last active date
    try:
        last = datetime.strptime(s.get("last_active_date", "2020-01-01"), "%Y-%m-%d").date()
        days_stale = (date(2025, 6, 1) - last).days
        recency = max(0.0, 1.0 - days_stale / 180)  # decay over 6 months
    except Exception:
        recency = 0.3
    subs.append(recency)
    if recency > 0.7: notes.append("recently active")

    # 3. Recruiter responsiveness
    rr = s.get("recruiter_response_rate", 0.0)
    rt = s.get("avg_response_time_hours", 48)
    speed = max(0.0, 1.0 - rt / 72)
    subs.append(rr * 0.65 + speed * 0.35)

    # 4. Saved by recruiters (external validation)
    saves = min(1.0, s.get("saved_by_recruiters_30d", 0) / 10)
    subs.append(saves)

    # 5. GitHub activity — important for AI engineering role
    gh = s.get("github_activity_score", -1)
    gh_score = 0.35 if gh == -1 else gh / 100
    subs.append(gh_score)
    if gh > 50: notes.append(f"GitHub {gh:.0f}")

    # 6. Interview completion (reliability signal)
    subs.append(s.get("interview_completion_rate", 0.5))

    # 7. Profile completeness
    subs.append(s.get("profile_completeness_score", 50) / 100)

    # 8. Assessment scores
    assess = s.get("skill_assessment_scores", {})
    subs.append(sum(assess.values()) / len(assess) / 100 if assess else 0.4)

    final = sum(subs) / len(subs)

    # Notice period adjustment
    notice = s.get("notice_period_days", 60)
    if notice == 0 or notice <= 30:
        notes.append(f"notice {notice}d ✓")
    elif notice <= 60:
        final *= 0.92
        notes.append(f"notice {notice}d")
    elif notice > 90:
        final *= 0.80
        notes.append(f"notice {notice}d (high)")

    return round(final, 4), "; ".join(notes) if notes else "moderate engagement"

# ─── EDUCATION ───────────────────────────────────────────────────────────────
def score_education(cand: dict) -> float:
    edu = cand.get("education", [])
    if not edu: return 0.3

    TIER = {"tier_1": 1.0, "tier_2": 0.75, "tier_3": 0.5, "tier_4": 0.3, "unknown": 0.35}
    CS_FIELDS = {"computer science", "information technology", "data science",
                 "artificial intelligence", "machine learning", "statistics",
                 "mathematics", "electronics", "computer engineering", "electrical"}
    DEG_BOOST = {"m.tech": 1.1, "m.e.": 1.1, "m.sc": 1.08, "phd": 1.15,
                 "ms": 1.1, "mtech": 1.1}

    best = 0.0
    for e in edu:
        tv  = TIER.get(e.get("tier", "unknown"), 0.35)
        fld = e.get("field_of_study", "").lower()
        fm  = 1.0 if any(f in fld for f in CS_FIELDS) else 0.55
        db  = DEG_BOOST.get(e.get("degree", "").lower(), 1.0)
        best = max(best, min(1.0, tv * fm * db))
    return round(best, 4)

# ─── LOCATION ────────────────────────────────────────────────────────────────
def score_location(cand: dict) -> float:
    loc      = cand.get("profile", {}).get("location", "").lower()
    relocate = cand.get("redrob_signals", {}).get("willing_to_relocate", False)
    country  = cand.get("profile", {}).get("country", "").lower()

    # JD says: Pune, Noida preferred; Hyd, Mumbai, Delhi NCR welcome
    preferred = ["pune", "noida", "hyderabad", "mumbai", "delhi", "gurgaon",
                 "gurugram", "bangalore", "bengaluru", "ncr"]
    other_india = ["chennai", "kolkata", "ahmedabad", "jaipur", "kochi",
                   "chandigarh", "indore", "coimbatore", "bhubaneswar",
                   "trivandrum", "vizag", "nagpur", "lucknow", "surat"]

    if any(p in loc for p in preferred):
        return 1.0
    if any(o in loc for o in other_india):
        return 0.75 if relocate else 0.55
    if "india" in country or "india" in loc:
        return 0.6 if relocate else 0.4
    # Outside India — JD says "case-by-case, no visa sponsorship"
    return 0.3 if relocate else 0.15

# ─── COMPOSITE SCORER ────────────────────────────────────────────────────────
def score_candidate(cand: dict) -> dict:
    cid = cand["candidate_id"]

    # Honeypot check first
    if is_honeypot(cand):
        return {"candidate_id": cid, "score": 0.001, "honeypot": True,
                "reasoning": "Impossible profile signals — honeypot excluded."}

    title_s,  title_note  = score_title(cand)
    skill_s,  skill_names = score_skills(cand)
    exp_s                 = score_experience(cand)
    career_s, career_note = score_career(cand)
    avail_s,  avail_note  = score_availability(cand)
    edu_s                 = score_education(cand)
    loc_s                 = score_location(cand)

    composite = (
        title_s  * W["title_fit"]      +
        skill_s  * W["skill_depth"]    +
        exp_s    * W["experience_fit"] +
        career_s * W["career_quality"] +
        avail_s  * W["availability"]   +
        edu_s    * W["education"]      +
        loc_s    * W["location"]
    )
    composite = round(composite, 6)

    # Build honest 1-2 sentence reasoning
    p      = cand.get("profile", {})
    rs     = cand.get("redrob_signals", {})
    yoe    = p.get("years_of_experience", 0)
    notice = rs.get("notice_period_days", "?")
    skills_str = ", ".join(skill_names[:3]) if skill_names else "few JD-aligned skills"
    concern = ""
    if int(notice) > 60:
        concern = f"; notice {notice}d above preferred"
    if title_s < 0.2:
        concern += "; title outside ML/AI scope"

    reasoning = (
        f"{p.get('current_title','N/A')} with {yoe:.1f}yr exp"
        f" at {p.get('current_company','N/A')}"
        f"; matched: {skills_str}"
        f"; {avail_note}{concern}."
    )[:220]

    return {
        "candidate_id": cid,
        "score": composite,
        "honeypot": False,
        "reasoning": reasoning,
    }

# ─── MAIN PIPELINE ────────────────────────────────────────────────────────────
def rank_candidates(candidates_path: str, out_path: str, top_n: int = 100):
    t0 = time.time()
    print(f"[rank.py] Loading candidates from {candidates_path} ...")

    results = []
    count   = 0
    opener  = gzip.open if candidates_path.endswith(".gz") else open

    with opener(candidates_path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cand = json.loads(line)
                results.append(score_candidate(cand))
                count += 1
                if count % 20000 == 0:
                    print(f"  {count:,} scored in {time.time()-t0:.1f}s")
            except json.JSONDecodeError:
                continue

    print(f"[rank.py] Scored {count:,} candidates in {time.time()-t0:.1f}s")

    # Sort descending
    results.sort(key=lambda x: -x["score"])

    # Enforce monotonic non-increasing
    top = results[:top_n]
    for i in range(1, len(top)):
        if top[i]["score"] > top[i-1]["score"]:
            top[i]["score"] = top[i-1]["score"]

    # Write CSV
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for rank_i, r in enumerate(top, 1):
            writer.writerow([
                r["candidate_id"], rank_i,
                round(r["score"], 6), r["reasoning"]
            ])

    elapsed = time.time() - t0
    honeypots_blocked = sum(1 for r in results if r.get("honeypot"))
    print(f"[rank.py] Top-{top_n} written to {out_path}")
    print(f"[rank.py] Total time: {elapsed:.1f}s")
    print(f"[rank.py] Score range: {top[0]['score']:.4f} → {top[-1]['score']:.4f}")
    print(f"[rank.py] Honeypots blocked: {honeypots_blocked}")
    return top

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Redrob Candidate Ranker")
    parser.add_argument("--candidates", required=True,
                        help="Path to candidates.jsonl or candidates.jsonl.gz")
    parser.add_argument("--out", required=True,
                        help="Output CSV path")
    parser.add_argument("--top", type=int, default=100,
                        help="Number of top candidates (default 100)")
    args = parser.parse_args()
    rank_candidates(args.candidates, args.out, args.top)
