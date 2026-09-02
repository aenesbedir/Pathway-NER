"""Apply the LLM audit to the missing-pathway corpus: drop the wrong spans.

Reads paironly_stages.jsonl together with llm_review.jsonl and writes
missing_llm_review.jsonl, identical except that every span the judge marked
"wrong" is removed. Spans marked "boundary" are kept unchanged: the judge
reported that the offsets are off but never returned corrected offsets, so
there is nothing to apply, and dropping a real pathway mention over an imperfect
boundary would cost more recall than the boundary costs precision.

`canonical_ok` is not acted on either. The downstream doccano dataset carries
only [start, end, "PATHWAY"] triples, so a wrong canonical never reaches
training; it matters for the surface-form dictionary, which is fixed in
preprocessing/pathway_surface_forms.py, not here.

Documents whose review call failed, and documents that carry no spans and were
therefore never sent to the judge, pass through untouched.

Usage:
    python scripts/apply_llm_review.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data/processed/missing_pathways"
STAGES = DIR / "paironly_stages.jsonl"
REVIEW = DIR / "llm_review.jsonl"
OUT = DIR / "missing_llm_review.jsonl"
REPORT = DIR / "missing_llm_review.json"


def main() -> None:
    wrong: dict[str, set[tuple[int, int]]] = {}
    reasons = []
    failed = 0
    reviewed = set()

    for line in REVIEW.open(encoding="utf-8"):
        rec = json.loads(line)
        pmid = rec["pmid"]
        if rec.get("error"):
            failed += 1
            continue
        reviewed.add(pmid)
        for v in rec["review"].get("spans") or []:
            i = v.get("i")
            if not isinstance(i, int) or i >= len(rec["spans"]):
                continue
            if v.get("verdict") != "wrong":
                continue
            s = rec["spans"][i]
            wrong.setdefault(pmid, set()).add((s["start"], s["end"]))
            reasons.append({
                "pmid": pmid,
                "text": s["text"],
                "source": s["source"],
                "canonical": s.get("canonical"),
                "reason": v.get("reason"),
            })

    dropped = 0
    by_stage = Counter()
    docs_changed = 0
    emptied = 0
    kept_docs = 0
    kept_spans = 0

    with OUT.open("w", encoding="utf-8") as fh:
        for line in STAGES.open(encoding="utf-8"):
            rec = json.loads(line)
            bad = wrong.get(rec["pmid"], set())
            if bad:
                before = len(rec["spans"])
                rec["spans"] = [
                    s for s in rec["spans"] if (s["start"], s["end"]) not in bad
                ]
                gone = before - len(rec["spans"])
                if gone:
                    docs_changed += 1
                    dropped += gone
                    for s in reasons:
                        if s["pmid"] == rec["pmid"]:
                            by_stage[s["source"]] += 1
                if not rec["spans"]:
                    emptied += 1
            rec["n_after_review"] = len(rec["spans"])
            kept_docs += 1
            kept_spans += len(rec["spans"])
            fh.write(json.dumps(rec) + "\n")

    report = {
        "input": str(STAGES.relative_to(ROOT)),
        "review": str(REVIEW.relative_to(ROOT)),
        "output": str(OUT.relative_to(ROOT)),
        "documents": kept_docs,
        "documents_reviewed": len(reviewed),
        "review_calls_failed": failed,
        "spans_dropped": dropped,
        "spans_dropped_by_stage": dict(by_stage),
        "documents_changed": docs_changed,
        "documents_left_with_no_span": emptied,
        "spans_remaining": kept_spans,
        "dropped_spans": reasons,
    }
    REPORT.write_text(json.dumps(report, indent=1) + "\n")
    summary = {k: v for k, v in report.items() if k != "dropped_spans"}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
