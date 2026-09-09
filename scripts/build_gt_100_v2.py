"""Apply the audited corrections to gt_100, writing gt_100_v2.

gt_100.jsonl is left untouched: earlier results are scored against it and must
stay reproducible. This script writes doccano/golden_dataset/gt_100_v2.jsonl,
identical except for the spans declared in ADDITIONS below.

Where the corrections come from
-------------------------------
Two passes over the 100 abstracts, both recorded in the repository:

  * a mechanical audit of the 279 gold spans (punctuation, mid-word offsets,
    bare generic terms, agent and measurement head nouns, nesting, and
    occurrences of an already-annotated string left unmarked). Only the last
    check fired, on three occurrences; one of them turned out to carry a
    shorter span already and became a widening rather than an addition.
  * a concept-level scan, in which each abstract was sent to the judge with its
    own gold spans listed as already recorded, asking what the annotation had
    missed, then filtered by form and required to name a Recon3D pathway
    (scripts/review_prompt_trials.py supplies both prompts). It produced 26
    proposals over 23 abstracts; 8 survived adjudication.

The 18 rejected proposals are kept in REJECTED with the reason, because the
reasons are the annotation rules the guide still lacks. Three of them
(1635807) were rejected only after checking the words around the span: the
abstract is a list of inherited diseases, and "urea cycle", "fatty acid
oxidation" and "glycoprotein degradation" are each followed by "disorders", so
the phrase names the disease, not the pathway.

Usage:
    python scripts/build_gt_100_v2.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "doccano/golden_dataset/gt_100.jsonl"
OUT = ROOT / "doccano/golden_dataset/gt_100_v2.jsonl"
MANIFEST = ROOT / "doccano/golden_dataset/gt_100_v2.manifest.json"

# (pmid, start, end, text, kind, reason)
ADDITIONS = [
    # An expression already annotated elsewhere in the same abstract, with this
    # occurrence left unmarked.
    ("23121637", 1356, 1366, "AA cascade", "unmarked_repeat",
     "annotated twice in this abstract; this third occurrence was skipped"),
    ("30112875", 798, 817, "serotonin synthesis", "unmarked_repeat",
     "annotated earlier in this abstract; this occurrence was skipped"),

    # A pathway the annotation missed. `recon` names the Recon3D subsystem the
    # phrase refers to, which is what makes it a pathway mention rather than a
    # description.
    ("11861404", 741, 753, "visual cycle", "missing_span",
     "the retinoid cycle: the sentence is about regenerating retinol from "
     "retinal; recon=vitamin a metabolism"),
    ("3271614", 1345, 1367, "prostacyclin synthesis", "missing_span",
     "the same process this abstract annotates as 'Prostacyclin production' and "
     "'prostanoid synthesis'; recon=eicosanoid metabolism"),
    ("30740736", 21, 48, "coenzyme A (CoA) metabolism", "missing_span",
     "the spelled-out form of 'CoA metabolism', which this abstract annotates "
     "elsewhere. The surrounding 'inborn errors of' names the disease; the "
     "pathway is the noun phrase after it; recon=coa synthesis"),
    ("30993483", 1280, 1317, "metabolic pathways for MTX and folate", "missing_span",
     "the same pathways this abstract annotates as 'MTX and folate "
     "metabolisms'; recon=folate metabolism"),
    ("856442", 823, 873, "formation of 5alpha-reduced 17beta-hydroxysteroids",
     "missing_span",
     "steroid conversion, the 'formation of <product>' pattern; the abstract "
     "annotates '17beta-hydroxysteroid pathway' for the same chemistry; "
     "recon=androgen and estrogen synthesis and metabolism"),
    ("36531023", 867, 883, "bile acid uptake", "missing_span",
     "last member of a list whose other five members are all annotated "
     "('pentose phosphate pathway, purine and pyrimidine synthesis, "
     "phospholipid metabolism, and bile acid uptake'); uptake counts because "
     "bile acid turnover is in the model; recon=bile acid synthesis"),
    ("41652287", 443, 456, "DNA synthesis", "missing_span",
     "the same process annotated elsewhere as 'DNA and RNA synthesis'; the "
     "span stops before 'and methylation', which has its own head; "
     "recon=nucleotide metabolism"),
    ("22185841", 669, 717, "CYP-mediated formation of endogenous eicosanoids",
     "missing_span",
     "eicosanoid biosynthesis. 'CYP-mediated' is kept inside the span on the "
     "same reading that keeps 'P450-dependent' in the curated half; this "
     "boundary is a judgement call, not a rule the guide settles; "
     "recon=eicosanoid metabolism"),
]

# (pmid, start, end, new_start, new_end, text, reason) - a span that exists but
# whose offsets disagree with how the same abstract annotates the same phrase
# elsewhere.
WIDENED = [
    ("37538846", 1982, 1999, 1968, 1999, "mitochondrial energy metabolism",
     "the abstract annotates 'mitochondrial energy metabolism' in full twice "
     "(at 585 and 1635); this third occurrence kept only 'energy metabolism'"),
]

# Proposals from the same scan that were not accepted, with the rule each one
# breaks. Recorded because these are the distinctions the annotation guide does
# not yet state.
REJECTED = {
    "1635807 urea cycle": "followed by 'disorders' - names the disease group",
    "1635807 fatty acid oxidation": "followed by 'disorders' - names the disease group",
    "1635807 glycoprotein degradation": "followed by 'disorders' - names the disease group",
    "41810983 electron transport chain": "listed among protein subunits (SDHA) - names the complex, not the process",
    "41577073 metabolism toward PPP": "names flux directed at a pathway, not the pathway; PPP itself is annotated",
    "16188953 ROS generation": "the abstract annotates detoxification only; leaving generation out looks deliberate",
    "1898255 vitamin B12 binding and/or transport": "'binding' is not turnover and the phrase cannot be split",
    "23121637 AA incorporation and turnover in brain phospholipid": "'incorporation' plus a location; no core process name survives",
    "23580368 impaired intracellular synthesis of adenosylcobalamin and methylcobalamin": "'impaired' is a pathological qualifier, not part of the process name",
    "23811272 intracellular metabolism": "no substrate named; 'intracellular' is a location",
    "26741399 energetic metabolism": "stylistic variant of 'energy metabolism', already annotated",
    "33663989 glycosylation": "bare, and part of the disease name 'Congenital disorders of glycosylation'",
    "3871414 Malabsorption of vitamin D": "a pathological state, not a pathway",
    "40176362 metabolites of tryptophan (Trp)": "head noun is a substance, not a process",
    "40277908 energy homeostasis": "names no compound",
    "41471909 taurine-hypotaurine": "elliptical: the shared head 'pathways' is dropped, leaving a compound name",
    "41872128 lipid peroxidation": "oxidative damage rather than metabolic turnover",
    "41872128 iron-dependent lipid peroxidation": "oxidative damage rather than metabolic turnover",
}


def main() -> None:
    by_pmid: dict[str, list] = {}
    for pmid, start, end, text, kind, reason in ADDITIONS:
        by_pmid.setdefault(pmid, []).append((start, end, text, kind, reason))

    widen: dict[str, list] = {}
    for pmid, s0, e0, s1, e1, text, reason in WIDENED:
        widen.setdefault(pmid, []).append((s0, e0, s1, e1, text, reason))

    added = 0
    changed = 0
    records = []
    for line in SRC.open(encoding="utf-8"):
        rec = json.loads(line)
        pmid = rec["meta"]["pmid"]
        for start, end, text, _kind, _reason in by_pmid.get(pmid, []):
            actual = rec["text"][start:end]
            if actual != text:
                raise SystemExit(f"{pmid} [{start}:{end}] is {actual!r}, not {text!r}")
            if any(e["start_offset"] < end and start < e["end_offset"]
                   for e in rec["entities"]):
                raise SystemExit(f"{pmid} [{start}:{end}] overlaps an existing span")
            rec["entities"].append({
                "start_offset": start, "end_offset": end, "label": "PATHWAY",
            })
            added += 1
        for s0, e0, s1, e1, text, _reason in widen.get(pmid, []):
            hit = [e for e in rec["entities"]
                   if (e["start_offset"], e["end_offset"]) == (s0, e0)]
            if not hit:
                raise SystemExit(f"{pmid}: no span at [{s0}:{e0}] to widen")
            if rec["text"][s1:e1] != text:
                raise SystemExit(f"{pmid} [{s1}:{e1}] is not {text!r}")
            hit[0]["start_offset"], hit[0]["end_offset"] = s1, e1
            changed += 1

        rec["entities"].sort(key=lambda e: (e["start_offset"], e["end_offset"]))
        records.append(rec)

    if added != len(ADDITIONS) or changed != len(WIDENED):
        raise SystemExit(f"applied {added}/{len(ADDITIONS)} additions, "
                         f"{changed}/{len(WIDENED)} widenings")

    with OUT.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def spans(path: Path) -> int:
        return sum(
            1 for line in path.open(encoding="utf-8")
            for e in json.loads(line).get("entities", [])
            if str(e.get("label", "")).upper().startswith("PATH")
        )

    manifest = {
        "version": "v2",
        "source": str(SRC.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(SRC.read_bytes()).hexdigest(),
        "output": str(OUT.relative_to(ROOT)),
        "output_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "documents": len(records),
        "spans_before": spans(SRC),
        "spans_after": spans(OUT),
        "added": [
            {"pmid": p, "start": s, "end": e, "text": t, "kind": k, "reason": r}
            for p, s, e, t, k, r in ADDITIONS
        ],
        "widened": [
            {"pmid": p, "from": [s0, e0], "to": [s1, e1], "text": t, "reason": r}
            for p, s0, e0, s1, e1, t, r in WIDENED
        ],
        "rejected": REJECTED,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in manifest.items()
                      if k not in ("added", "widened", "rejected")}, indent=1))
    print(f"added {added} spans, widened {changed}, "
          f"rejected {len(REJECTED)} proposals")


if __name__ == "__main__":
    main()
