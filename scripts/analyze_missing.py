#!/usr/bin/env python3
"""
analyze_missing.py

Metrics over the "missing pathway" recovery run. Three layers are kept apart
because they answer different questions and disagree:

  query      what PubMed's index returned  (scripts/fetch_missing_pathways.py)
  text       what the abstract actually says  (verbatim surface-form scan)
  model      what the NER checkpoint predicts  (llm/run_silver.py output)

Blocklisted Recon names are reported in their own block: they have no curated
surface forms, so their numbers are not comparable with the rest.

Output: data/processed/missing_pathways/metrics.json  (+ stdout tables)
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/missing_pathways"
OUT = ROOT / "data/processed/missing_pathways"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def main() -> None:
    q = json.loads((RAW / "queries.json").read_text())
    check = json.loads((RAW / "text_check.json").read_text())
    arts = {a["pmid"]: a for a in json.loads((RAW / "articles.json").read_text())}
    prov = json.loads((RAW / "provenance.json").read_text())

    silver_file = OUT / "missing_ner.jsonl"
    preds = defaultdict(list)
    if silver_file.exists():
        for line in silver_file.read_text().splitlines():
            r = json.loads(line)
            for s in r.get("spans", []):
                preds[r["pmid"]].append(s)

    text = {p: norm(a["title"] + " " + a["abstract"]) for p, a in arts.items()}

    rows = []
    for path, rec in q.items():
        forms = rec["forms"]
        blocked = rec["blocklisted"]
        solo_ids, pair_ids = set(), set()
        forms_solo_ok = forms_pair_ok = 0
        for f, d in forms.items():
            solo_ids |= set(d["solo_ids"])
            pair_ids |= set(d["pair_pmids"])
            forms_solo_ok += d["solo_count"] > 0
            forms_pair_ok += d["pair_hits"] > 0
        allp = solo_ids | pair_ids
        pats = [re.compile(r"\b" + re.escape(norm(f)) + r"\b") for f in forms]
        with_text = {p for p in allp if p in text and any(r.search(text[p]) for r in pats)}
        # model side
        model_docs = {p for p in allp if preds.get(p)}
        model_spans = sum(len(preds[p]) for p in allp if p in preds)
        model_form_hit = set()
        for p in allp:
            for s in preds.get(p, []):
                if any(r.search(norm(s.get("text", ""))) for r in pats):
                    model_form_hit.add(p)
                    break
        rows.append({
            "pathway": path,
            "blocklisted": blocked,
            "n_forms": len(forms),
            "forms_solo_ok": forms_solo_ok,
            "forms_pair_ok": forms_pair_ok,
            "pmids_total": len(allp),
            "pmids_solo": len(solo_ids),
            "pmids_pair": len(pair_ids),
            "pmids_pair_only": len(pair_ids - solo_ids),
            "pmids_solo_only": len(solo_ids - pair_ids),
            "abstracts_fetched": len(allp & set(arts)),
            "abstract_has_form": len(with_text),
            "model_docs_with_span": len(model_docs),
            "model_spans": model_spans,
            "model_docs_hitting_form": len(model_form_hit),
        })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(rows, indent=1))

    def table(sel, title):
        rs = [r for r in rows if r["blocklisted"] is sel]
        if not rs:
            return
        print(f"\n### {title} ({len(rs)})")
        hdr = ("pathway", "frm", "solo+", "pair+", "pmid", "solo", "pair", "onlyP",
               "abs", "hasF", "mDoc", "mSpan", "mForm")
        print("| " + " | ".join(hdr) + " |")
        for r in sorted(rs, key=lambda x: -x["pmids_total"]):
            print(f'| {r["pathway"]} | {r["n_forms"]} | {r["forms_solo_ok"]} | '
                  f'{r["forms_pair_ok"]} | {r["pmids_total"]} | {r["pmids_solo"]} | '
                  f'{r["pmids_pair"]} | {r["pmids_pair_only"]} | {r["abstracts_fetched"]} | '
                  f'{r["abstract_has_form"]} | {r["model_docs_with_span"]} | '
                  f'{r["model_spans"]} | {r["model_docs_hitting_form"]} |')

    table(False, "Curated surface forms")
    table(True, "Blocklisted (canonical only)")

    for sel, name in ((False, "curated"), (True, "blocklisted")):
        rs = [r for r in rows if r["blocklisted"] is sel]
        if not rs:
            continue
        tot = lambda k: sum(r[k] for r in rs)
        print(f'\n{name}: pmids={tot("pmids_total")} '
              f'(solo-only {tot("pmids_solo_only")}, pair-only {tot("pmids_pair_only")}) '
              f'abstracts={tot("abstracts_fetched")} '
              f'has-form={tot("abstract_has_form")} '
              f'model-docs={tot("model_docs_with_span")} '
              f'model-spans={tot("model_spans")}')


if __name__ == "__main__":
    main()
