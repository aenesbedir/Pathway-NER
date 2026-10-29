#!/usr/bin/env python3
"""
compare_silver.py

Record, pair by pair, how a rebuilt relation silver differs from the one it
replaces.

Why this exists
---------------
silver_2k_10kplusmissing relabels the silver_2k_full sample after its pathway
spans were swapped for those of pathway_10k_plus_missing. The swap changes few
pairs, but in four different ways, and a later reader comparing two models
trained on the two silvers needs to know which pairs moved and why:

`unchanged`         same candidate id, same stratum, same pathway mentions.
`mentions_changed`  same id, but the pathway now has more mentions. The prompt
                    marks every mention, so the teacher saw a different input.
`stratum_changed`   the pair existed before as doc_level; a new mention puts the
                    pathway in a sentence with the disease.
`new`               the pathway key did not exist before.
`removed`           an old same-sentence pair with no counterpart.

Telling `stratum_changed` from `new` needs the old doc_level candidates, which
were never kept in full, so the old pairs are rebuilt here from the old corpus
with the same builder. The rebuild is checked against the old same-sentence file
and the script stops if the two disagree: a mismatch means the environment
differs (scispacy, spaCy) and every status below would be wrong.

Output: `changes.jsonl` (one row per new same-sentence pair, plus removed ones)
and `changes.summary.json` in the new silver directory.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from build_candidates import build_for_document, load_sentencizer

REPO = Path(__file__).resolve().parents[1]
RELATION = REPO / "data/processed/relation"
DEFAULT_OLD = RELATION / "silver_2k_full"
DEFAULT_NEW = RELATION / "silver_2k_10kplusmissing"
DEFAULT_OLD_CORPUS = REPO / "data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl"
LABELS = "relations_llm_opus48_same_sentence.jsonl"
SAME = "candidates_same_sentence.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    # Not str.splitlines(): it also breaks on U+2029 inside an abstract.
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def mention_offsets(mentions) -> tuple:
    return tuple((m["start"], m["end"]) if isinstance(m, dict) else (m.start, m.end)
                 for m in mentions)


def rebuild_old(corpus: Path, pmids: set[str]) -> dict:
    """Every old candidate, both strata, for the given PMIDs."""
    nlp = load_sentencizer()
    out = {}
    with open(corpus, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            pmid = str(rec["meta"].get("pmid"))
            if pmid not in pmids:
                continue
            for c in build_for_document(nlp, pmid, rec["text"], rec["label"], True):
                out[c.candidate_id] = c
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old", type=Path, default=DEFAULT_OLD)
    ap.add_argument("--new", type=Path, default=DEFAULT_NEW)
    ap.add_argument("--old-corpus", type=Path, default=DEFAULT_OLD_CORPUS)
    args = ap.parse_args()

    old_same = {c["candidate_id"]: c for c in read_jsonl(args.old / SAME)}
    new_same = {c["candidate_id"]: c for c in read_jsonl(args.new / SAME)}
    old_labels = {r["candidate_id"]: r["label"] for r in read_jsonl(args.old / LABELS)}
    new_labels_path = args.new / LABELS
    new_labels = (
        {r["candidate_id"]: r["label"] for r in read_jsonl(new_labels_path)}
        if new_labels_path.exists() else {}
    )

    pmids = {c["pmid"] for c in old_same.values()} | {c["pmid"] for c in new_same.values()}
    old_all = rebuild_old(args.old_corpus, pmids)
    rebuilt_same = {k for k, c in old_all.items() if c.stratum == "same_sentence"}
    if rebuilt_same != set(old_same):
        raise SystemExit(
            f"rebuilt {len(rebuilt_same)} old same-sentence pairs, file has "
            f"{len(old_same)} ({len(rebuilt_same ^ set(old_same))} differ); "
            "the environment does not reproduce the old build"
        )

    rows = []
    for cid, c in sorted(new_same.items(), key=lambda kv: (kv[1]["pmid"], kv[0])):
        if cid in old_same:
            same_mentions = (mention_offsets(old_same[cid]["pathway_mentions"])
                             == mention_offsets(c["pathway_mentions"]))
            status = "unchanged" if same_mentions else "mentions_changed"
        elif cid in old_all:
            status = "stratum_changed"
        else:
            status = "new"
        rows.append((cid, c, status))
    for cid, c in sorted(old_same.items(), key=lambda kv: (kv[1]["pmid"], kv[0])):
        if cid not in new_same:
            rows.append((cid, c, "removed"))

    out_path = args.new / "changes.jsonl"
    status_counts: Counter = Counter()
    transitions: Counter = Counter()
    with open(out_path, "w", encoding="utf-8") as fh:
        for cid, c, status in rows:
            old_label, new_label = old_labels.get(cid), new_labels.get(cid)
            status_counts[status] += 1
            if status != "unchanged":
                transitions[f"{old_label} -> {new_label}"] += 1
            fh.write(json.dumps({
                "candidate_id": cid,
                "pmid": c["pmid"],
                "pathway_key": c["pathway_key"],
                "disease_key": c["disease_key"],
                "status": status,
                "old_label": old_label,
                "new_label": new_label,
                "label_changed": old_label != new_label,
            }, ensure_ascii=False) + "\n")

    unchanged_ids = [cid for cid, _, s in rows if s == "unchanged"]
    summary = {
        "old": str(args.old),
        "new": str(args.new),
        "old_corpus": str(args.old_corpus),
        "n_old_same_sentence": len(old_same),
        "n_new_same_sentence": len(new_same),
        "status": dict(status_counts),
        "new_labels_present": bool(new_labels),
        # Unchanged pairs are answered from the teacher cache, so their labels
        # must agree; a disagreement means the cache was not hit.
        "unchanged_label_disagreements": sum(
            1 for cid in unchanged_ids
            if cid in new_labels and old_labels.get(cid) != new_labels[cid]
        ),
        "label_transitions_outside_unchanged": dict(transitions.most_common()),
        "output": str(out_path),
    }
    (args.new / "changes.summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
