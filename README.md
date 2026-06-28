# Redrob AI — Intelligent Candidate Discovery & Ranking

**India Data & AI Challenge — Hackathon Submission**

## Role being ranked for
Senior AI Engineer — Founding Team @ Redrob AI (Pune / Noida, Hybrid)

## How to reproduce the submission

**Requirements:** Python 3.8+ — no pip installs needed (stdlib only)

```bash
python rank.py --candidates ./candidates.jsonl --out ./submission.csv
```

Then validate:
```bash
python validate_submission.py submission.csv
# Output: Submission is valid.
```

**Runtime:** ~10 seconds for 100,000 candidates on CPU  
**Memory:** < 500 MB RAM  
**Network:** Not required  
**GPU:** Not used

## Files

| File | Purpose |
|---|---|
| `rank.py` | Main ranker — produces submission CSV from candidates.jsonl |
| `validate_submission.py` | Format validator (mirrors official checker) |
| `submission.csv` | Final Top-100 submission |
| `submission_metadata.yaml` | Team and methodology metadata |
| `requirements.txt` | No external dependencies |

## Architecture

Multi-signal weighted scorer with 7 components:

| Component | Weight | What it measures |
|---|---|---|
| Skill depth | 28% | JD required + preferred skills with trust multiplier |
| Title fit | 26% | ML/AI/Search title vs disqualified titles from JD |
| Career quality | 14% | Product company experience, penalises pure consulting |
| Availability | 12% | Platform signals — active, responsive, GitHub, notice period |
| Experience fit | 12% | YOE in 5–9 band (bell curve, peak at 7yr) |
| Education | 5% | Institution tier × field × degree level |
| Location | 3% | Pune/Noida/Delhi NCR preferred per JD |

**Key design decisions:**
- Skill trust multiplier: `expert` proficiency + `duration_months == 0` → deflated to 0.15 (catches keyword stuffers)
- Title disqualifier: HR Managers, Accountants, Civil Engineers etc. capped at 0.05 title score (per JD explicit disqualifiers)
- Consulting penalty: TCS, Infosys, Wipro etc. career ratio > 30% gets penalised (per JD explicit guidance)
- Honeypot detection: 4 flags — expert skills with 0 duration, career months mismatch, 10+ expert skills with <15 endorsements, impossible company tenure

**Results on real 100K dataset:**
- Runtime: 10.4 seconds
- Score range: 0.8751 → 0.8007
- Honeypots blocked: 37
- Validator: Submission is valid ✓
