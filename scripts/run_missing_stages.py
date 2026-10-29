#!/usr/bin/env python3
"""
run_missing_stages.py

Build the pair-only slice of the missing-pathway corpus and label it with the
three deterministic layers applied one at a time, so each layer's contribution is
a measured number rather than an assumption.

Slice: the eight targets that have curated surface forms; blocklisted Recon names
are excluded, having no forms and no model-predicted span in 777 abstracts.

Per pathway the slice is the pair-only set — PMIDs the disease-paired query
returned and the solo query did not. That set is empty for five of the eight, and
structurally so: pair-only can only fill once the solo cap of 200 overflows, and
`n-glycan metabolism` has 7 hits in total. Those five contribute all of their
PMIDs instead, so every target is represented rather than only the three large
enough to overflow.

Stages, each a superset of the one before:

    1  ner            the checkpoint alone
    2  + boost        pattern scan, llm/booster.py boost()
    3  + boost_surface dictionary scan over preprocessing/pathway_surface_forms.py

Merge order follows run_silver.py's trust ordering: the dictionary knows which
canonical a phrase belongs to, so it precedes the model on equal-length overlap.

Output: data/processed/missing_pathways/paironly_stages.jsonl   (stage-3 spans)
        data/processed/missing_pathways/paironly_stages.json    (metrics)
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "llm"))
sys.path.insert(0, str(ROOT / "preprocessing"))

from annotators import resolve_annotator  # noqa: E402
from booster import boost, boost_surface, merge  # noqa: E402

RAW = ROOT / "data/raw/missing_pathways"
OUT = ROOT / "data/processed/missing_pathways"
MODEL = ("/home/enes/NER-pipeline/runs-truba-checkpoints/pathway-10k/"
         "biom-electra-large/lr3e-05/seed7")


def key(s: dict) -> tuple[int, int]:
    return (s["start"], s["end"])


def main() -> None:
    q = json.loads((RAW / "queries.json").read_text())
    arts = {a["pmid"]: a for a in json.loads((RAW / "articles.json").read_text())}

    owner: dict[str, set[str]] = defaultdict(set)
    route: dict[str, str] = {}
    selected: set[str] = set()
    for path, rec in q.items():
        if rec["blocklisted"]:
            continue
        solo, pair = set(), set()
        for d in rec["forms"].values():
            solo |= set(d["solo_ids"])
            pair |= set(d["pair_pmids"])
        take = pair - solo
        how = "pair_only"
        if not take:
            take = solo | pair
            how = "all"
        print(f"  {path:46} {how:9} {len(take)}")
        for p in take:
            owner[p].add(path)
            route.setdefault(p, how)
        selected |= take

    pmids = sorted(p for p in selected
                   if p in arts and (arts[p].get("abstract") or "").strip())
    print(f"selected pmids: {len(selected)} | with abstract: {len(pmids)}")

    ann = resolve_annotator(MODEL)
    texts = [arts[p]["abstract"] for p in pmids]
    ner_all = ann.spans_batch([(t, []) for t in texts])

    stages = {n: Counter() for n in ("ner", "boost", "dict")}
    docs = {n: set() for n in ("ner", "boost", "dict")}
    added_surface = Counter()
    rows = []
    for pmid, text, ner in zip(pmids, texts, ner_all):
        b = boost(text)
        d = boost_surface(text)

        s1 = ner
        s2 = merge(ner, b)
        s3 = merge(d, ner, b)

        new_b = [s for s in s2 if key(s) not in {key(x) for x in s1}]
        new_d = [s for s in s3 if key(s) not in {key(x) for x in s2}]

        stages["ner"][pmid] = len(s1)
        stages["boost"][pmid] = len(new_b)
        stages["dict"][pmid] = len(new_d)
        if s1:
            docs["ner"].add(pmid)
        if new_b:
            docs["boost"].add(pmid)
        if new_d:
            docs["dict"].add(pmid)
        for s in new_d:
            added_surface[s["surface"].lower()] += 1

        rows.append({
            "pmid": pmid,
            "pathways": sorted(owner[pmid]),
            "route": route[pmid],
            "n_ner": len(s1),
            "n_after_boost": len(s2),
            "n_after_dict": len(s3),
            "spans": [
                {"start": s["start"], "end": s["end"],
                 "text": text[s["start"]:s["end"]],
                 "source": s.get("source", "ner"),
                 "canonical": s.get("canonical")}
                for s in s3
            ],
        })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "paironly_stages.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    tot = {n: sum(c.values()) for n, c in stages.items()}
    cum = tot["ner"], tot["ner"] + tot["boost"], sum(tot.values())
    metrics = {
        "model": MODEL,
        "abstracts": len(pmids),
        "by_route": dict(Counter(route[p] for p in pmids)),
        "spans_stage1_ner": tot["ner"],
        "spans_added_boost": tot["boost"],
        "spans_added_dict": tot["dict"],
        "cumulative": {"ner": cum[0], "ner+boost": cum[1], "ner+boost+dict": cum[2]},
        "docs_with_span": {n: len(v) for n, v in docs.items()},
        "top_dict_additions": added_surface.most_common(25),
    }
    (OUT / "paironly_stages.json").write_text(json.dumps(metrics, indent=1))

    print(f'\nabstracts            : {len(pmids)}')
    print(f'1 ner                : {cum[0]:6}  ({len(docs["ner"])} docs)')
    print(f'2 + boost            : {cum[1]:6}  (+{tot["boost"]}, {len(docs["boost"])} docs)')
    print(f'3 + boost_surface    : {cum[2]:6}  (+{tot["dict"]}, {len(docs["dict"])} docs)')
    print("\ntop dictionary additions:")
    for t, c in added_surface.most_common(20):
        print(f"  {c:5}  {t}")


if __name__ == "__main__":
    main()
