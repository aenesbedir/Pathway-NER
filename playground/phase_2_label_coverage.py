#!/usr/bin/env python3
"""
phase_2_label_coverage.py

Full-corpus label coverage analysis for the Phase 2 exact-match dataset.

Answers:
  1. Which of the 98 Recon pathways are unlabeled (blocklisted vs zero-match)?
  2. Which pathways got labeled, with span / PMID counts (synonym-deduped —
     every pathway_id is already a canonical Recon name).
  3. Which surface forms (synonyms) matched, grouped by canonical pathway.

Inputs:
  - unique_pathways_from_recon.json          (98 canonical Recon pathways)
  - preprocessing/match_exact.py             (RECON_BLOCKLIST, RECON_SYNONYMS)
  - data/processed/exact_matches.jsonl       (matched spans, 22,017 records)

Output:
  - prints a human summary
  - with --markdown, prints ready-to-embed markdown tables for
    playground/exact_match_analysis.md

Run from repo root:
  python3 playground/phase_2_label_coverage.py
  python3 playground/phase_2_label_coverage.py --markdown
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Mirror of the config applied in preprocessing/match_exact.py
RECON_BLOCKLIST = {
    "miscellaneous", "protein formation", "intracellular demand",
    "intracellular source/sink", "r group synthesis",
    "biomass and maintenance functions", "exchange/demand reaction",
    "dietary fiber binding",
}


def load_recon() -> set[str]:
    return set(json.loads((ROOT / "unique_pathways_from_recon.json").read_text()))


def load_matches():
    labeled = set()
    span_count = Counter()
    surface_forms = defaultdict(Counter)   # pid -> Counter(original-case text)
    pmids = defaultdict(set)

    path = ROOT / "data/processed/exact_matches.jsonl"
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        pid = r.get("pathway_id")
        if pid is None or not r.get("spans"):
            continue
        labeled.add(pid)
        for s in r["spans"]:
            span_count[pid] += 1
            surface_forms[pid][s["text"].strip()] += 1
            pmids[pid].add(r["pmid"])
    return labeled, span_count, surface_forms, pmids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true",
                    help="Emit markdown tables instead of the plain summary")
    args = ap.parse_args()

    recon = load_recon()
    labeled, span_count, surface_forms, pmids = load_matches()

    eligible = recon - RECON_BLOCKLIST
    unlabeled = sorted(eligible - labeled)
    blocklisted = sorted(recon & RECON_BLOCKLIST)
    extra = sorted(labeled - recon)

    if args.markdown:
        emit_markdown(labeled, span_count, surface_forms, pmids)
        return

    print(f"Recon total        : {len(recon)}")
    print(f"Blocklisted        : {len(blocklisted)}")
    print(f"Eligible           : {len(eligible)}")
    print(f"Labeled            : {len(labeled)}")
    print(f"Unlabeled eligible : {len(unlabeled)}")
    print(f"Outside Recon      : {len(extra)}  {extra}")
    print("\nUnlabeled eligible (zero match):")
    for u in unlabeled:
        print(f"  - {u}")
    print("\nBlocklisted:")
    for b in blocklisted:
        print(f"  - {b}")


def emit_markdown(labeled, span_count, surface_forms, pmids) -> None:
    # Full 82-pathway table, sorted by span count
    print("### Full labeled pathway table (canonical, span-sorted)\n")
    print("| spans | PMIDs | pathway |")
    print("|---|---|---|")
    for pid in sorted(labeled, key=lambda p: -span_count[p]):
        print(f"| {span_count[pid]:,} | {len(pmids[pid])} | {pid} |")

    # Synonym surface-form table: "surface form (canonical)".
    # Fold case variants (group by lowercase, show the most common casing).
    print("\n### Synonym surface forms (surface → canonical)\n")
    print("| matched surface form (canonical pathway) | spans |")
    print("|---|---|")
    for pid in sorted(labeled):
        folded: dict[str, list] = {}
        for text, cnt in surface_forms[pid].items():
            if text.lower() == pid.lower():
                continue
            key = text.lower()
            if key not in folded:
                folded[key] = [text, 0, Counter()]
            folded[key][1] += cnt
            folded[key][2][text] += cnt
        for key in sorted(folded, key=lambda k: -folded[k][1]):
            _, total, variants = folded[key]
            display = variants.most_common(1)[0][0]
            print(f"| {display} ({pid}) | {total:,} |")


if __name__ == "__main__":
    main()
