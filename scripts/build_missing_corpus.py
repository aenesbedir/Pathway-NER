#!/usr/bin/env python3
"""
build_missing_corpus.py

Turn the PubMed search results of scripts/fetch_missing_pathways.py into a corpus
and measure how much of it actually contains the pathway it was retrieved for.

A search hit is only a claim that PubMed's index matched the term somewhere in the
record. This script checks the claim against the abstract text itself, per surface
form, so "the query returned N articles" never gets reported as "N abstracts
mention the pathway".

Output:
  data/raw/missing_pathways/articles.json      corpus (pmid, title, abstract)
  data/raw/missing_pathways/pmids.txt          one pmid per line
  data/raw/missing_pathways/provenance.json    pmid -> which pathway/form/route
  data/raw/missing_pathways/text_check.json    per-pathway surface-form presence
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pubmed_api"))
sys.path.insert(0, str(ROOT / "preprocessing"))

from fetch_articles import fetch_pubmed_batch  # noqa: E402

OUT = ROOT / "data/raw/missing_pathways"


def main() -> None:
    q = json.loads((OUT / "queries.json").read_text())

    # pmid -> provenance
    prov: dict[str, dict] = defaultdict(
        lambda: {"pathways": set(), "forms": set(), "routes": set()}
    )
    for path, rec in q.items():
        for form, d in rec["forms"].items():
            for p in d["solo_ids"]:
                prov[p]["pathways"].add(path)
                prov[p]["forms"].add(form)
                prov[p]["routes"].add("solo")
            for p in d["pair_pmids"]:
                prov[p]["pathways"].add(path)
                prov[p]["forms"].add(form)
                prov[p]["routes"].add("pair")

    pmids = sorted(prov)
    print(f"{len(pmids)} unique pmids across {len(q)} pathways")

    meta = fetch_pubmed_batch(pmids)
    arts = []
    for p in pmids:
        m = meta.get(p)
        if not m:
            continue
        arts.append({
            "pmid": p,
            "title": m.get("title") or "",
            "abstract": m.get("abstract") or "",
        })
    with_abs = [a for a in arts if a["abstract"].strip()]
    print(f"fetched {len(arts)} records, {len(with_abs)} with an abstract")

    (OUT / "articles.json").write_text(json.dumps(arts, ensure_ascii=False, indent=1))
    (OUT / "pmids.txt").write_text("\n".join(a["pmid"] for a in with_abs) + "\n")
    (OUT / "provenance.json").write_text(json.dumps(
        {p: {k: sorted(v) for k, v in d.items()} for p, d in prov.items()}, indent=1
    ))

    # --- does the abstract really contain the form it was retrieved for? -------
    text = {a["pmid"]: (a["title"] + " " + a["abstract"]).lower() for a in arts}
    check = {}
    for path, rec in q.items():
        forms = list(rec["forms"])
        per_form = {}
        path_pm = set()
        path_hit = set()
        for form, d in rec["forms"].items():
            ids = set(d["solo_ids"]) | set(d["pair_pmids"])
            path_pm |= ids
            pat = re.compile(r"\b" + re.escape(form.lower()) + r"\b")
            hit = {p for p in ids if p in text and pat.search(text[p])}
            # any form of the same pathway counts too
            per_form[form] = {
                "origin": d["origin"],
                "solo_count": d["solo_count"],
                "solo_returned": len(d["solo_ids"]),
                "pair_hits": d["pair_hits"],
                "pair_pmids": len(d["pair_pmids"]),
                "pmids": len(ids),
                "abstract_has_this_form": len(hit),
            }
        anypat = [re.compile(r"\b" + re.escape(f.lower()) + r"\b") for f in forms]
        for p in path_pm:
            t = text.get(p, "")
            if any(r.search(t) for r in anypat):
                path_hit.add(p)
        check[path] = {
            "blocklisted": rec["blocklisted"],
            "n_forms": len(forms),
            "pmids": len(path_pm),
            "abstract_has_any_form": len(path_hit),
            "forms": per_form,
        }
    (OUT / "text_check.json").write_text(json.dumps(check, indent=1))
    print("wrote", OUT / "text_check.json")


if __name__ == "__main__":
    main()
