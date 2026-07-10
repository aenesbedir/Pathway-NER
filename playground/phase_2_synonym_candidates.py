#!/usr/bin/env python3
"""
phase_2_synonym_candidates.py

For each Recon pathway that got ZERO exact matches, test whether candidate
synonym surface forms actually appear in the article corpus. This decides
whether a pathway can be recovered by adding a synonym (like the existing
RECON_SYNONYMS in preprocessing/match_exact.py) or is genuinely absent.

Key finding: several "zero match" pathways are NOT absent from the corpus —
their canonical Recon name is simply never written verbatim in the literature,
while a common synonym (e.g. "lipoic acid" for "lipoate metabolism") appears
hundreds of times.

Inputs:
  - data/raw/articles.json   (10,329 articles, ~236M chars)

Related:
  - playground/phase_2_label_coverage.py   (produces the zero-match list)
  - playground/exact_match_analysis.md     (findings written up here)

Run from repo root:
  python3 playground/phase_2_synonym_candidates.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Candidate synonyms to probe for each zero-match pathway
CANDIDATES = {
    "androgen and estrogen synthesis and metabolism": [
        "steroidogenesis", "androgen metabolism", "estrogen metabolism",
        "estrogen synthesis", "androgen synthesis", "steroid hormone",
    ],
    "blood group synthesis": [
        "abo blood group", "blood group antigen", "histo-blood group",
    ],
    "hippurate metabolism": [
        "hippurate", "hippuric acid", "benzoate metabolism",
    ],
    "keratan sulfate synthesis": [
        "keratan sulfate biosynthesis", "keratan sulfate synthesis",
        "keratan sulphate",
    ],
    "lipoate metabolism": [
        "lipoic acid", "lipoate", "alpha-lipoic acid", "α-lipoic acid",
        "lipoic acid metabolism",
    ],
    "n-glycan metabolism": [
        "n-glycan", "n-linked glycosylation", "n-glycosylation",
    ],
    "phosphatidylinositol phosphate metabolism": [
        "phosphatidylinositol", "pip2", "pi3k", "phosphoinositide",
    ],
    "squalene and cholesterol synthesis": [
        "cholesterol synthesis", "cholesterol biosynthesis", "squalene",
        "mevalonate pathway", "sterol synthesis",
    ],
}


def main() -> None:
    articles = json.loads((ROOT / "data/raw/articles.json").read_text())
    parts = []
    for a in articles:
        parts.append((a.get("abstract") or "").lower())
        parts.append((a.get("full_text") or "").lower())
    blob = "\n".join(parts)
    print(f"Corpus chars: {len(blob):,}  articles: {len(articles)}\n")

    for pw, terms in CANDIDATES.items():
        print(f"### {pw}")
        for t in terms:
            c = len(re.findall(re.escape(t.lower()), blob))
            flag = "  <-- appears" if c else ""
            print(f"     {c:>6}  \"{t}\"{flag}")
        print()


if __name__ == "__main__":
    main()
