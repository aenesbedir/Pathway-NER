"""Compare the LLM audit of the missing-pathway corpus with human curation.

The 25 abstracts curated for gt_125 are the only part of the missing corpus
where the audit (scripts/review_missing_dataset.py, llm_review.jsonl) can be
held against a human. This script lines the two up span by span and writes
doccano/golden_dataset/gt_125/review_vs_curation.json with:

  verdicts        how each audit verdict (correct / boundary / wrong) fared
                  against what the curator did with that span
  discovery       the audit's "missed" proposals against the spans the curator
                  added, each proposal checked for verbatim presence in the text
  unreviewed      abstracts the audit never saw because the pipeline produced
                  no span there, and what the curator found in them
  curator_added   every span the curator added, with the reason the audit could
                  not have produced it, assigned by rule:
                    unreviewed_doc      the abstract was skipped entirely
                    boundary_of_existing overlaps a pipeline span, so it was a
                                        correction, not a discovery
                    not_proposed        reviewed, no overlap, not in "missed"

Usage:
    python scripts/compare_review_vs_curation.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT125 = ROOT / "doccano/golden_dataset/gt_125/gt_125.jsonl"
REVIEW = ROOT / "data/processed/missing_pathways/llm_review.jsonl"
SILVER = ROOT / "data/processed/missing_pathways/missing_llm_review.jsonl"
OUT = ROOT / "doccano/golden_dataset/gt_125/review_vs_curation.json"


def norm(s: str) -> str:
    return s.lower().strip(" .")


def main() -> None:
    gold = {}
    for line in GT125.open(encoding="utf-8"):
        rec = json.loads(line)
        if rec["meta"].get("annotation_status") != "human_curated":
            continue
        gold[rec["meta"]["pmid"]] = (
            rec["text"],
            [(e["start_offset"], e["end_offset"]) for e in rec["entities"]],
        )

    silver = {}
    for line in SILVER.open(encoding="utf-8"):
        rec = json.loads(line)
        if rec["pmid"] in gold:
            silver[rec["pmid"]] = [(s["start"], s["end"]) for s in rec["spans"]]

    review = {}
    for line in REVIEW.open(encoding="utf-8"):
        rec = json.loads(line)
        if rec["pmid"] in gold and not rec.get("error"):
            review[rec["pmid"]] = rec

    # --- verdicts against the curator ----------------------------------------
    verdicts = Counter()
    for pmid, rec in review.items():
        text, g = gold[pmid]
        gset = set(g)
        for v in rec["review"].get("spans") or []:
            i = v.get("i")
            if not isinstance(i, int) or i >= len(rec["spans"]):
                continue
            s = rec["spans"][i]
            key = (s["start"], s["end"])
            if key in gset:
                fate = "curator_kept"
            elif any(key[0] < b[1] and b[0] < key[1] for b in g):
                fate = "curator_moved_boundary"
            else:
                fate = "curator_removed"
            verdicts[f"{v.get('verdict', '?')} -> {fate}"] += 1

    # --- discovery: "missed" proposals against curator additions --------------
    proposals = []
    for pmid, rec in review.items():
        text, g = gold[pmid]
        added = {norm(text[a:b]) for a, b in g if (a, b) not in set(silver[pmid])}
        have = {norm(text[a:b]) for a, b in silver[pmid]}
        for m in rec["review"].get("missed") or []:
            m = str(m)
            n = norm(m)
            if n in added:
                outcome = "matches_curator_addition"
            elif n in have:
                outcome = "restates_existing_span"
            elif n in text.lower():
                outcome = "in_text_not_gold"
            else:
                outcome = "not_verbatim_in_text"
            proposals.append({"pmid": pmid, "proposal": m, "outcome": outcome})
    discovery = Counter(p["outcome"] for p in proposals)

    # --- curator additions, with the reason the audit could not produce them --
    curator_added = []
    for pmid, (text, g) in gold.items():
        sv = silver.get(pmid, [])
        proposed = {norm(str(m)) for m in
                    (review.get(pmid, {}).get("review", {}).get("missed") or [])}
        for a, b in g:
            if (a, b) in set(sv):
                continue
            span = text[a:b]
            if pmid not in review:
                why = "unreviewed_doc"
            elif any(a < e and s < b for s, e in sv):
                why = "boundary_of_existing"
            elif norm(span) in proposed:
                why = "proposed_by_audit"
            else:
                why = "not_proposed"
            curator_added.append({"pmid": pmid, "span": span, "reason": why})

    unreviewed = [
        {"pmid": p, "curator_spans": [gold[p][0][a:b] for a, b in gold[p][1]]}
        for p in gold if p not in review
    ]

    out = {
        "basis": {
            "curated_docs": len(gold),
            "curated_spans": sum(len(g) for _, g in gold.values()),
            "docs_reviewed_by_audit": len(review),
            "judge_model": dict(Counter(r.get("judge_model") for r in review.values())),
            "silver_spans": sum(len(v) for v in silver.values()),
        },
        "verdicts": dict(verdicts),
        "discovery": {
            "proposals": len(proposals),
            "outcomes": dict(discovery),
            "curator_additions": len(curator_added),
            "curator_additions_by_reason": dict(Counter(c["reason"] for c in curator_added)),
            "detail": proposals,
        },
        "unreviewed": unreviewed,
        "curator_added": curator_added,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    print(json.dumps({k: v for k, v in out.items() if k != "curator_added"}
                     | {"discovery": {k: v for k, v in out["discovery"].items()
                                      if k != "detail"}}, indent=1, ensure_ascii=False))
    print("\ncurator additions:")
    for c in curator_added:
        print(f"  {c['reason']:22} {c['pmid']}  {c['span']!r}")


if __name__ == "__main__":
    main()
