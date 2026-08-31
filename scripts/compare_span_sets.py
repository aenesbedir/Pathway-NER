#!/usr/bin/env python3
"""Set-compare the pathway names two annotators found in the same documents.

For a corpus with no span-level ground truth — PMC full texts, say — the only
available question is where two annotators agree. Character offsets cannot answer
it: an LLM asked to list what it found reports surface forms and counts, not
positions. So the comparison is over *normalized distinct names per document*,
the convention `opus_vs_model_fulltext_50.md` established:

    lowercase -> strip punctuation -> collapse spaces -> drop a trailing "pathway(s)"

Two record shapes are read, told apart by their keys:
  * span source   {"pmid", "spans": [{"text", ...}]}   — run_silver.py output,
                  data/processed/pathway-10k/matches.jsonl, the silver files
  * name listing  {"pmid", "pathways": [{"text", "count"}]} — an LLM asked to
                  enumerate rather than to locate

Reports agreement, each side's exclusives, Jaccard, and document-level
positive/negative agreement. Nothing here is a precision or a recall: neither side
is ground truth, and the exclusives are the interesting part — they say what one
annotator systematically sees and the other does not.

    venv310/bin/python3 scripts/compare_span_sets.py \\
        --a data/processed/kegg_recon3d/opus_prediction_fulltext_50_revised.jsonl \\
        --b data/processed/kegg_recon3d/pathway-10k-biom-electra-large-seed7_fulltext_50.jsonl \\
        --label-a opus_revised --label-b pipeline_ner
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def normalize(text: str) -> str:
    t = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\s*pathways?$", "", t).strip()


def load(path: Path) -> dict[str, set[str]]:
    """pmid -> set of normalized names, from either record shape."""
    out: dict[str, set[str]] = defaultdict(set)
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        items = rec.get("spans") or rec.get("pathways") or []
        names = {normalize(i["text"]) for i in items}
        out[str(rec["pmid"])] |= {n for n in names if n}
    return dict(out)


def compare(a: dict[str, set[str]], b: dict[str, set[str]]) -> dict:
    agreed = a_only = b_only = 0
    a_ex: Counter = Counter()
    b_ex: Counter = Counter()
    doc_agree = 0
    pmids = set(a) | set(b)
    for pmid in pmids:
        sa, sb = a.get(pmid, set()), b.get(pmid, set())
        agreed += len(sa & sb)
        a_only += len(sa - sb)
        b_only += len(sb - sa)
        a_ex.update(sa - sb)
        b_ex.update(sb - sa)
        doc_agree += bool(sa) == bool(sb)
    total = agreed + a_only + b_only
    return {
        "n_docs": len(pmids),
        "docs_with_any": {"a": sum(1 for v in a.values() if v),
                          "b": sum(1 for v in b.values() if v)},
        "distinct_names": {"a": len({n for v in a.values() for n in v}),
                           "b": len({n for v in b.values() for n in v})},
        "agreed": agreed, "a_only": a_only, "b_only": b_only,
        "jaccard": round(agreed / total, 4) if total else 0.0,
        "doc_level_agreement": f"{doc_agree}/{len(pmids)}",
        "top_a_only": a_ex.most_common(15),
        "top_b_only": b_ex.most_common(15),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--label-a", default=None)
    ap.add_argument("--label-b", default=None)
    args = ap.parse_args()

    result = compare(load(Path(args.a)), load(Path(args.b)))
    print(json.dumps({"a": args.label_a or args.a, "b": args.label_b or args.b,
                      "a_file": args.a, "b_file": args.b, **result},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
