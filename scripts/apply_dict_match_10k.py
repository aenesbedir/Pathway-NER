#!/usr/bin/env python3
"""
apply_dict_match_10k.py

Apply the pathway surface-form dictionary (preprocessing/pathway_surface_forms.py,
scanned by llm/booster.py::boost_surface) to the 10,125-document combined corpus
and write an augmented doccano file plus a summary.

Motivation: section 6.3 of the progress report measured that 627 documents
contain their pathway query term verbatim in the abstract yet carry no annotated
PATHWAY span. The dictionary exists to close that gap; this script measures how
much of it actually closes and produces the corpus a re-review would start from.

Overlap policy (``--overlap``):

  keep     (default) existing spans are never touched. A dictionary hit is added
           only when it overlaps no existing span of any label. Overlaps are
           counted and reported, not applied. Use this when the output is going
           back to human review: it never silently rewrites an annotation.
  longest  the merge rule llm/booster.py already uses inside the silver
           pipeline: on overlap the longer span wins, so a dictionary hit can
           replace a shorter existing PATHWAY span ("androgen synthesis and
           metabolism" over a bare "androgen synthesis"). Use this for parity
           with what a re-run of run_silver.py would produce.

A dictionary hit that overlaps a DISEASE span is never applied under either
policy — the two label sets come from different models and resolving that
conflict is a review decision, not a scripted one. Such cases are reported as
``cross_label_conflicts``.

Provenance goes into ``meta["dict_match"]`` per document: the added spans with
their canonical name and the rule that produced them (``surface:<origin>``), so
the additions stay separable from the original annotations after the fact.

Inputs:
  data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl
  preprocessing/pathway_surface_forms.py  (via llm/booster.py)

Outputs:
  data/doccano/10k_dict_match.jsonl          augmented corpus, doccano format
  analysis/10k_dict_match_summary.json       counts, per-origin and per-form breakdown

Run from the repository root:
    venv310/bin/python3 scripts/apply_dict_match_10k.py
    venv310/bin/python3 scripts/apply_dict_match_10k.py --overlap longest
    venv310/bin/python3 scripts/apply_dict_match_10k.py --limit 50 --dry-run
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "llm"))
sys.path.insert(0, str(REPO_ROOT / "preprocessing"))

from booster import boost_surface  # noqa: E402
from pathway_surface_forms import build_surface_forms  # noqa: E402

DEFAULT_INPUT = REPO_ROOT / "data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "data/doccano/10k_dict_match.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "analysis/10k_dict_match_summary.json"

PATHWAY = "PATHWAY"


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def apply_to_document(doc: dict, policy: str) -> dict:
    """Return per-document result: new labels, added spans, and counters."""
    text = doc["text"]
    labels = [list(l) for l in doc.get("label", [])]
    pathway_labels = [l for l in labels if l[2] == PATHWAY]
    other_labels = [l for l in labels if l[2] != PATHWAY]

    added: list[dict] = []
    replaced: list[list] = []
    skipped_overlap = 0
    cross_label = 0

    for hit in boost_surface(text):
        s, e = hit["start"], hit["end"]

        # A dictionary hit inside a DISEASE (or any non-PATHWAY) span is a
        # conflict between two annotation sources; leave it for a human.
        if any(overlaps(s, e, o[0], o[1]) for o in other_labels):
            cross_label += 1
            continue

        clashing = [l for l in pathway_labels if overlaps(s, e, l[0], l[1])]
        if clashing:
            if policy == "keep":
                skipped_overlap += 1
                continue
            # longest wins; a tie keeps the existing span
            if max(l[1] - l[0] for l in clashing) >= e - s:
                skipped_overlap += 1
                continue
            for l in clashing:
                pathway_labels.remove(l)
                replaced.append(l)

        pathway_labels.append([s, e, PATHWAY])
        added.append(
            {
                "start": s,
                "end": e,
                "text": hit["surface"],
                "canonical": hit["canonical"],
                "rule": hit["rule"],
            }
        )

    new_labels = sorted(other_labels + pathway_labels, key=lambda l: (l[0], l[1]))
    return {
        "labels": new_labels,
        "added": added,
        "replaced": replaced,
        "skipped_overlap": skipped_overlap,
        "cross_label": cross_label,
        "had_pathway_before": bool([l for l in labels if l[2] == PATHWAY]),
        "has_pathway_after": bool(pathway_labels),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    ap.add_argument("--overlap", choices=("keep", "longest"), default="keep")
    ap.add_argument("--limit", type=int, help="process only the first N documents")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    docs = []
    with args.input.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if args.limit is not None and i >= args.limit:
                break
            docs.append(json.loads(line))

    stats = collections.Counter()
    by_origin = collections.Counter()
    by_form = collections.Counter()
    by_canonical = collections.Counter()
    out_lines = []

    for doc in docs:
        res = apply_to_document(doc, args.overlap)
        stats["documents"] += 1
        stats["spans_added"] += len(res["added"])
        stats["spans_replaced"] += len(res["replaced"])
        stats["skipped_overlap"] += res["skipped_overlap"]
        stats["cross_label_conflicts"] += res["cross_label"]
        if res["added"]:
            stats["documents_changed"] += 1
        if not res["had_pathway_before"]:
            stats["zero_pathway_before"] += 1
            if res["has_pathway_after"]:
                stats["zero_pathway_recovered"] += 1
        if not res["has_pathway_after"]:
            stats["zero_pathway_after"] += 1

        for a in res["added"]:
            by_origin[a["rule"]] += 1
            by_form[a["text"].lower()] += 1
            by_canonical[a["canonical"]] += 1

        doc = dict(doc)
        doc["label"] = res["labels"]
        meta = dict(doc.get("meta", {}))
        meta["dict_match"] = {
            "source": "preprocessing/pathway_surface_forms.py",
            "overlap_policy": args.overlap,
            "added": res["added"],
            "replaced": [{"start": r[0], "end": r[1], "label": r[2]} for r in res["replaced"]],
            "skipped_overlap": res["skipped_overlap"],
            "cross_label_conflicts": res["cross_label"],
        }
        doc["meta"] = meta
        out_lines.append(json.dumps(doc, ensure_ascii=False))

    dictionary = build_surface_forms()
    summary = {
        "input": str(args.input.relative_to(REPO_ROOT)),
        "output": str(args.output.relative_to(REPO_ROOT)),
        "overlap_policy": args.overlap,
        "dictionary": {
            "canonicals": len(dictionary),
            "surface_forms": sum(len(v) for v in dictionary.values()),
        },
        "counts": dict(sorted(stats.items())),
        "spans_by_origin": dict(by_origin.most_common()),
        "spans_by_canonical": dict(by_canonical.most_common()),
        "spans_by_form": dict(by_form.most_common()),
    }

    if not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: v for k, v in summary.items() if k != "spans_by_form"}, indent=2))
    print(f"\ntop forms: {list(by_form.most_common(15))}")
    if args.dry_run:
        print("\n(dry run - nothing written)")
    else:
        print(f"\nwrote {args.output}\nwrote {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
