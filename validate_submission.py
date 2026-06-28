#!/usr/bin/env python3
"""
Redrob Submission Validator
Mirrors the competition's auto-validator checks from submission_spec.md
"""
import csv, sys, gzip, json, argparse, re

def validate(csv_path, candidates_path=None):
    errors = []
    warnings = []

    # Load CSV
    try:
        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        errors.append(f"Cannot read CSV: {e}")
        print_report(errors, warnings)
        return False

    # Check columns
    required_cols = {"candidate_id", "rank", "score", "reasoning"}
    actual_cols = set(rows[0].keys()) if rows else set()
    missing = required_cols - actual_cols
    if missing:
        errors.append(f"Missing columns: {missing}")

    # Check row count
    if len(rows) != 100:
        errors.append(f"Expected 100 rows, got {len(rows)}")

    # Check ranks 1..100 exactly once
    ranks = [int(r["rank"]) for r in rows]
    if sorted(ranks) != list(range(1, 101)):
        errors.append(f"Ranks are not exactly 1..100 unique. Got: {sorted(ranks)[:5]}...")

    # Check candidate_id format
    bad_ids = [r["candidate_id"] for r in rows if not re.match(r"^CAND_\d{7}$", r["candidate_id"])]
    if bad_ids:
        errors.append(f"Invalid candidate_id format: {bad_ids[:3]}")

    # Check unique candidate_ids
    cids = [r["candidate_id"] for r in rows]
    if len(set(cids)) != len(cids):
        errors.append("Duplicate candidate_ids found")

    # Check scores: must be non-increasing
    scores = [float(r["score"]) for r in rows]
    violations = [(i, scores[i], scores[i+1]) for i in range(len(scores)-1) if scores[i+1] > scores[i] + 1e-9]
    if violations:
        errors.append(f"Scores not monotonically non-increasing at ranks {[v[0]+1 for v in violations[:3]]}")

    # Check scores not all identical
    if len(set(scores)) == 1:
        errors.append("All scores are identical — model is not differentiating candidates")

    # Check reasoning not all identical
    reasonings = [r["reasoning"] for r in rows]
    if len(set(reasonings)) < 5:
        warnings.append("Fewer than 5 unique reasoning strings — may fail Stage 4 review")

    # Check empty reasoning
    empty_r = sum(1 for r in reasonings if not r.strip())
    if empty_r > 0:
        warnings.append(f"{empty_r} rows have empty reasoning")

    # Validate against candidate pool if provided
    if candidates_path:
        valid_ids = set()
        opener = gzip.open if candidates_path.endswith(".gz") else open
        with opener(candidates_path, "rt") as f:
            for line in f:
                if line.strip():
                    try:
                        c = json.loads(line)
                        valid_ids.add(c["candidate_id"])
                    except Exception:
                        pass
        unknown = [cid for cid in cids if cid not in valid_ids]
        if unknown:
            errors.append(f"candidate_ids not in dataset: {unknown[:3]}")
        print(f"  Validated {len(cids)} IDs against {len(valid_ids):,} candidates")

    print_report(errors, warnings)
    return len(errors) == 0

def print_report(errors, warnings):
    print("\n══════════════════════════════════════")
    print("  Redrob Submission Validator")
    print("══════════════════════════════════════")
    if not errors and not warnings:
        print("  ✓ All checks passed. Ready to submit.")
    if errors:
        print(f"\n  ✗ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"    • {e}")
    if warnings:
        print(f"\n  ⚠ WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    • {w}")
    print("══════════════════════════════════════\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="Path to submission CSV")
    parser.add_argument("--candidates", help="Path to candidates.jsonl (optional, for ID validation)")
    args = parser.parse_args()
    ok = validate(args.csv_path, args.candidates)
    sys.exit(0 if ok else 1)
