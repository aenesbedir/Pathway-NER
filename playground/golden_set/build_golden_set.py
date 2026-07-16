#!/usr/bin/env python3
"""
build_golden_set.py

Human-curated gold annotation of the 5 abstracts that contain the most distinct
Recon pathways (by exact-match count in data/processed/exact_matches.jsonl).

Purpose: a *variation-aware* evaluation set. Unlike the training labels (which
come from exact string matching of 98 canonical Recon names + a few synonyms),
this set marks EVERY surface form of an in-vocabulary pathway, including the
variations exact matching misses:
  - word-order        : "metabolism of androgens"      -> androgen ... metabolism
  - chemical synonym  : "cholecalciferol metabolism"   -> vitamin d metabolism
  - order + separator : "cysteine/methionine metabolism" -> methionine and cysteine metabolism
  - abbreviation      : "BCAA metabolism"              -> valine, leucine, and isoleucine metabolism
  - shared-head enum. : "histidine and glutathione metabolism" -> {histidine, glutathione} metabolism

Annotations are hand-authored below as (surface, occurrence) so exact character
offsets are recomputed from the source text and verified — no hand-typed
offsets to drift.

match_type:
  exact     - surface == a canonical Recon name (case-insensitive); exact-match catches it
  synonym   - surface is a current RECON_SYNONYMS entry; exact-match catches it
  variation - a real in-vocab pathway mention exact-match MISSES; resolves to >=1
              of the 98 Recon subsystems (the primary eval target)
  umbrella  - a genuine metabolic-process mention that does NOT resolve to any of
              the 98 Recon subsystems (e.g. 'energy metabolism', 'amino acid
              metabolism'); positive for a binary tagger, but not Recon-scored

Scope rule for what counts as an in-scope Pathway span:
  A span is in scope if it denotes a metabolic process AND either
   (a) maps to >=1 Recon subsystem  (specific process -> parent pathway,
       umbrella term -> its Recon children)         -> match_type exact/synonym/variation
   (b) is a generic metabolic-process umbrella term  -> match_type umbrella
  Excluded (-> out_of_vocab_pathways): non-metabolic cellular processes
  ('aminoacyl-tRNA biosynthesis' = translation, 'mitochondrial metabolism' =
  compartment) and narrow subtype specifications whose subtype word is absent from
  the parent Recon name ('biosynthesis of unsaturated fatty acids' vs the generic
  Recon 'fatty acid synthesis').

Buckets besides `spans`:
  shared_head_enumerations - factored "X, Y and Z metabolism" phrases OR umbrella
                             terms that fan out to several Recon children; lists the
                             intended pathway decomposition
  out_of_vocab_pathways    - mentions that are NOT in-scope Pathway spans at all
                             (non-metabolic processes, excluded subtypes); recorded
                             for transparency, not scored
  metabolites_not_pathways - salient metabolite names that must NOT be tagged
                             (precision negatives)

Inputs:
  - data/raw/articles.json               (abstract text)
  - unique_pathways_from_recon.json      (98-name vocabulary, for validation)
Output:
  - playground/golden_set/golden_set.json
  - playground/golden_set/golden_set.md   (human-readable review copy)

Run from repo root:
  /home/enes/sci-usage/venv310/bin/python3 playground/golden_set/build_golden_set.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARTICLES = ROOT / "data/raw/articles.json"
RECON = ROOT / "unique_pathways_from_recon.json"

PMIDS = ["11469814", "39934780", "40225847", "29615816", "36294866"]

# Surface forms exact matching already covers (canonical names are added
# separately from the Recon vocab). Used only to sanity-check match_type labels.
RECON_SYNONYMS_FLAT = {
    "tca cycle", "tricarboxylic acid cycle", "krebs cycle",
    "glycolysis", "gluconeogenesis", "warburg effect",
    "ppp", "hexose monophosphate shunt", "pentose phosphate shunt",
    "beta-oxidation", "β-oxidation", "fao", "fatty acid β-oxidation",
    "fatty acid beta-oxidation", "oxphos", "electron transport chain", "etc",
    "de novo lipogenesis", "dnl", "fatty acid biosynthesis", "lipogenesis",
    "bile acid biosynthesis", "primary bile acid biosynthesis", "bile acid production",
    "nad+ metabolism", "nadh metabolism", "nicotinamide metabolism", "nad metabolism",
    "keratan-sulfate degradation", "riboflavin metabolism",
}

# ---------------------------------------------------------------------------
# Hand annotations. surface strings are verbatim substrings of the abstract;
# `occ` is the 0-based occurrence index when a surface appears more than once.
# ---------------------------------------------------------------------------
ANN = {
    "11469814": {
        "spans": [
            ("steroid metabolism", 0, "steroid metabolism", "exact",
             "'deranged steroid metabolism'"),
            ("steroid metabolism", 1, "steroid metabolism", "exact",
             "'changes in steroid metabolism'"),
            ("metabolism of androgens", 0, "androgen and estrogen synthesis and metabolism",
             "variation", "word-order reversal of 'androgen metabolism'; also plural"),
        ],
        "shared_head_enumerations": [
            ("steroid synthesis and metabolism",
             [("steroid metabolism", "variation", "synthesis+metabolism factored; core is steroid metabolism")],
             "'enzymes involved in steroid synthesis and metabolism' — umbrella phrase"),
        ],
        "out_of_vocab_pathways": [],
        "metabolites_not_pathways": [
            ("cortisol", 0, "hormone, not a pathway"),
            ("glucocorticoids", 0, "hormone class"),
        ],
    },

    "39934780": {
        "spans": [
            ("arachidonic acid metabolism", 0, "arachidonic acid metabolism", "exact",
             "'These include arachidonic acid metabolism'"),
            ("arachidonic acid metabolism", 1, "arachidonic acid metabolism", "exact",
             "'particularly involving arachidonic acid metabolism'"),
            ("cholecalciferol metabolism", 0, "vitamin d metabolism", "variation",
             "cholecalciferol = vitamin D3; chemical-synonym of 'vitamin d metabolism'"),
            ("glycine, serine, alanine, and threonine metabolism", 0,
             "glycine, serine, alanine, and threonine metabolism", "exact",
             "verbatim canonical Recon name"),
            ("formation of prostaglandin", 0, "eicosanoid metabolism", "variation",
             "prostaglandins are eicosanoids; specific product-formation -> Recon 'eicosanoid metabolism'"),
        ],
        "shared_head_enumerations": [
            ("lipid and amino acid metabolism",
             [("lipid metabolism", "umbrella", "umbrella category; no single Recon subsystem"),
              ("amino acid metabolism", "umbrella", "umbrella category; no single Recon subsystem")],
             "shared-head umbrella; both halves included as non-Recon metabolic processes"),
            ("purine metabolism",
             [("purine synthesis", "variation", "umbrella 'purine metabolism' -> Recon child"),
              ("purine catabolism", "variation", "umbrella 'purine metabolism' -> Recon child")],
             "umbrella term spanning both Recon purine subsystems"),
        ],
        "out_of_vocab_pathways": [],
        "metabolites_not_pathways": [],
    },

    "40225847": {
        "spans": [
            ("Arginine and proline metabolism", 0, "arginine and proline metabolism", "exact",
             "verbatim canonical (capitalized)"),
            ("Butanoate metabolism", 0, "butanoate metabolism", "exact",
             "verbatim canonical (capitalized)"),
            ("arginine biosynthesis", 0, "arginine and proline metabolism", "variation",
             "KEGG 'arginine biosynthesis'; Recon folds it into 'arginine and proline metabolism'"),
        ],
        "shared_head_enumerations": [],
        "out_of_vocab_pathways": [
            ("Biosynthesis of unsaturated fatty acids", 0,
             "excluded: subtype 'unsaturated' absent from Recon's generic 'fatty acid synthesis'"),
        ],
        "metabolites_not_pathways": [
            ("arachidonic acid", 0, "metabolite (not 'arachidonic acid metabolism')"),
            ("arginine", 0, "amino acid metabolite"),
            ("glucose 6-phosphate", 0, "metabolite"),
            ("carnitine", 0, "metabolite"),
            ("creatine", 0, "metabolite"),
        ],
    },

    "29615816": {
        "spans": [
            ("tryptophan metabolism", 0, "tryptophan metabolism", "exact",
             "verbatim canonical"),
            ("fatty acid oxidation", 0, "fatty acid oxidation", "exact",
             "core term inside 'carnitine mediated fatty acid oxidation'"),
            ("cysteine/methionine metabolism", 0, "methionine and cysteine metabolism", "variation",
             "order swapped + '/' separator vs canonical 'methionine and cysteine metabolism'"),
            ("lysophospholipid metabolism", 0, "glycerophospholipid metabolism", "variation",
             "specific lipid subtype -> Recon parent 'glycerophospholipid metabolism'"),
        ],
        "shared_head_enumerations": [
            ("purine metabolism and biosynthesis",
             [("purine synthesis", "variation",
               "'purine metabolism' umbrella + 'purine biosynthesis' both cover purine synthesis"),
              ("purine catabolism", "variation",
               "'purine metabolism' umbrella also covers purine catabolism")],
             "'involvement in purine metabolism and biosynthesis'"),
        ],
        "out_of_vocab_pathways": [],
        "metabolites_not_pathways": [
            ("carnitine", 0, "metabolite (modifier in 'carnitine mediated fatty acid oxidation')"),
        ],
    },

    "36294866": {
        "spans": [
            ("glutathione metabolism", 0, "glutathione metabolism", "exact",
             "contiguous tail of 'histidine and glutathione metabolism'"),
            ("glutathione metabolism", 1, "glutathione metabolism", "exact",
             "'Alterations in glutathione metabolism'"),
            ("nicotinamide metabolism", 0, "nad metabolism", "synonym",
             "'BCAA and nicotinamide metabolism' — 'nicotinamide metabolism' is a current RECON_SYNONYM"),
            ("neurotransmitter metabolism", 0, "neurotransmitter metabolism", "umbrella",
             "umbrella metabolic-process term; no single Recon subsystem"),
        ],
        "shared_head_enumerations": [
            ("histidine and glutathione metabolism",
             [("histidine metabolism", "variation",
               "head 'histidine' factored from shared 'metabolism' — exact-match misses"),
              ("glutathione metabolism", "exact", "contiguous; already a span")],
             "'Differences in histidine and glutathione metabolism'"),
            ("nicotinamide and energy metabolism",
             [("nad metabolism", "variation",
               "'nicotinamide' split from 'metabolism' by 'and energy' — synonym form broken by shared head"),
              ("energy metabolism", "umbrella", "umbrella metabolic-process term; no single Recon subsystem")],
             "'NDR was associated with disruption in nicotinamide and energy metabolism'"),
            ("branched chain amino acid (BCAA) and nicotinamide metabolism",
             [("valine, leucine, and isoleucine metabolism", "variation",
               "BCAA = valine/leucine/isoleucine; 'BCAA metabolism' shared-head + abbreviation"),
              ("nad metabolism", "synonym", "'nicotinamide metabolism' contiguous; already a span")],
             "'BCAA and nicotinamide metabolism'"),
            ("glycine, serine and threonine, BCAA and AAA metabolism",
             [("glycine, serine, alanine, and threonine metabolism", "variation",
               "subset (no alanine) + shared 'metabolism' factored across the list"),
              ("valine, leucine, and isoleucine metabolism", "variation",
               "'BCAA metabolism' via shared head"),
              ("phenylalanine metabolism", "variation", "'AAA metabolism' -> Recon child (aromatic aa)"),
              ("tyrosine metabolism", "variation", "'AAA metabolism' -> Recon child (aromatic aa)"),
              ("tryptophan metabolism", "variation", "'AAA metabolism' -> Recon child (aromatic aa)")],
             "'changes in glycine, serine and threonine, BCAA and AAA metabolism'"),
            ("aromatic amino acid (AAA) biosynthesis",
             [("phenylalanine metabolism", "variation", "AAA -> Recon child"),
              ("tyrosine metabolism", "variation", "AAA -> Recon child"),
              ("tryptophan metabolism", "variation", "AAA -> Recon child")],
             "umbrella 'aromatic amino acid biosynthesis' -> three Recon aromatic-aa subsystems"),
            ("purine metabolism",
             [("purine synthesis", "variation", "umbrella -> Recon child"),
              ("purine catabolism", "variation", "umbrella -> Recon child")],
             "umbrella term spanning both Recon purine subsystems"),
        ],
        "out_of_vocab_pathways": [
            ("aminoacyl-tRNA biosynthesis", 0, "translation pathway; not a Recon metabolic subsystem"),
            ("mitochondrial metabolism", 0, "compartment term, not a metabolic process"),
        ],
        "metabolites_not_pathways": [
            ("L-glutamine", 0, "amino acid metabolite (not 'glutamate metabolism')"),
        ],
    },
}


def find_nth(hay: str, needle: str, n: int) -> int:
    idx = -1
    for _ in range(n + 1):
        idx = hay.find(needle, idx + 1)
        if idx == -1:
            return -1
    return idx


def resolve(text, surface, occ):
    start = find_nth(text, surface, occ)
    if start == -1:
        raise ValueError(f"NOT FOUND (occ {occ}): {surface!r}")
    return start, start + len(surface)


def write_markdown(out):
    L = ["# Golden Set — variation-aware pathway annotations",
         "",
         "Hand-curated over the 5 abstracts richest in distinct Recon pathways "
         "(most-distinct-pathway PMIDs from `data/processed/exact_matches.jsonl`). "
         "Abstract text from `data/raw/articles.json`. Vocabulary: the 98 canonical "
         "Recon subsystems (`unique_pathways_from_recon.json`).",
         "",
         "`match_type`: **exact**/**synonym** = exact matching already catches it; "
         "**variation** = a real in-vocab pathway mention exact matching MISSES "
         "(the whole point of this set).",
         ""]
    for a in out:
        c = a["counts"]
        L += [f"## PMID {a['pmid']} — {a['title']}",
              "",
              f"> {a['abstract']}",
              "",
              f"**Counts:** {c['spans']} spans "
              f"({c['spans_exact']} exact, {c['spans_synonym']} synonym, "
              f"**{c['spans_variation']} variation**), "
              f"{c['shared_head_enumerations']} shared-head enumerations, "
              f"{c['out_of_vocab_pathways']} out-of-vocab, "
              f"{c['metabolites_not_pathways']} metabolite negatives.",
              "",
              "### Contiguous spans",
              "",
              "| span text | offsets | canonical pathway | match_type | note |",
              "|---|---|---|---|---|"]
        for s in a["spans"]:
            L.append(f"| `{s['text']}` | {s['start']}–{s['end']} | {s['canonical']} "
                     f"| {s['match_type']} | {s['note']} |")
        if a["shared_head_enumerations"]:
            L += ["", "### Shared-head enumerations", ""]
            for en in a["shared_head_enumerations"]:
                L.append(f"- **`{en['text']}`** ({en['start']}–{en['end']}) — {en['note']}")
                for p in en["pathways"]:
                    L.append(f"    - → `{p['canonical']}` ({p['match_type']}): {p['note']}")
        if a["out_of_vocab_pathways"]:
            L += ["", "### Out-of-vocab pathway mentions (not scored in-scope)", ""]
            for o in a["out_of_vocab_pathways"]:
                L.append(f"- `{o['text']}` ({o['start']}–{o['end']}) — {o['note']}")
        if a["metabolites_not_pathways"]:
            L += ["", "### Metabolite negatives (must NOT be tagged)", ""]
            for m in a["metabolites_not_pathways"]:
                L.append(f"- `{m['text']}` ({m['start']}–{m['end']}) — {m['note']}")
        L.append("")
    (HERE / "golden_set.md").write_text("\n".join(L), encoding="utf-8")


def main():
    arts = {a["pmid"]: a for a in json.load(ARTICLES.open())}
    recon = set(json.load(RECON.open()))

    problems = []
    out = []
    for pmid in PMIDS:
        text = arts[pmid]["abstract"]
        title = arts[pmid]["title"]
        a = ANN[pmid]

        spans = []
        for surface, occ, canonical, mtype, note in a["spans"]:
            s, e = resolve(text, surface, occ)
            # umbrella spans deliberately carry a non-Recon canonical (the umbrella term)
            if mtype != "umbrella" and canonical not in recon:
                problems.append(f"{pmid}: canonical not in Recon vocab: {canonical!r}")
            # sanity: exact/synonym labels should agree with the vocab/synonym sets
            low = surface.lower()
            if mtype == "exact" and low not in recon:
                problems.append(f"{pmid}: marked 'exact' but not a canonical name: {surface!r}")
            if mtype == "synonym" and low not in RECON_SYNONYMS_FLAT:
                problems.append(f"{pmid}: marked 'synonym' but not in RECON_SYNONYMS: {surface!r}")
            spans.append({"start": s, "end": e, "text": surface,
                          "canonical": canonical, "match_type": mtype, "note": note})

        enums = []
        for surface, parts, note in a["shared_head_enumerations"]:
            s, e = resolve(text, surface, 0)
            enums.append({
                "start": s, "end": e, "text": surface, "note": note,
                "pathways": [{"canonical": c, "match_type": mt, "note": pn}
                             for c, mt, pn in parts],
            })

        oov = []
        for surface, occ, note in a["out_of_vocab_pathways"]:
            s, e = resolve(text, surface, occ)
            oov.append({"start": s, "end": e, "text": surface, "note": note})

        negs = []
        for surface, occ, note in a["metabolites_not_pathways"]:
            s, e = resolve(text, surface, occ)
            negs.append({"start": s, "end": e, "text": surface, "note": note})

        n_var = sum(1 for x in spans if x["match_type"] == "variation")
        out.append({
            "pmid": pmid, "title": title, "abstract": text,
            "counts": {
                "spans": len(spans),
                "spans_exact": sum(1 for x in spans if x["match_type"] == "exact"),
                "spans_synonym": sum(1 for x in spans if x["match_type"] == "synonym"),
                "spans_variation": n_var,
                "spans_umbrella": sum(1 for x in spans if x["match_type"] == "umbrella"),
                "shared_head_enumerations": len(enums),
                "out_of_vocab_pathways": len(oov),
                "metabolites_not_pathways": len(negs),
            },
            "spans": spans,
            "shared_head_enumerations": enums,
            "out_of_vocab_pathways": oov,
            "metabolites_not_pathways": negs,
        })

    payload = {
        "description": "Human-curated variation-aware gold annotations for the 5 "
                       "abstracts richest in distinct Recon pathways.",
        "vocabulary": "unique_pathways_from_recon.json (98 canonical Recon subsystems)",
        "source_text": "data/raw/articles.json (abstract field)",
        "articles": out,
    }
    (HERE / "golden_set.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    write_markdown(out)

    # aggregate
    tot = {k: 0 for k in out[0]["counts"]}
    for a in out:
        for k, v in a["counts"].items():
            tot[k] += v

    # headline: pool every mention (contiguous spans + enumeration parts) and
    # classify by match_type. Recon-resolvable = exact/synonym/variation.
    by_type = {"exact": 0, "synonym": 0, "variation": 0, "umbrella": 0}
    for a in out:
        for x in a["spans"]:
            by_type[x["match_type"]] = by_type.get(x["match_type"], 0) + 1
        for en in a["shared_head_enumerations"]:
            for p in en["pathways"]:
                by_type[p["match_type"]] = by_type.get(p["match_type"], 0) + 1
    recon_resolvable = by_type["exact"] + by_type["synonym"] + by_type["variation"]
    catches = by_type["exact"] + by_type["synonym"]
    misses = by_type["variation"]

    print("Wrote golden_set.json + golden_set.md")
    print("Aggregate:", json.dumps(tot, indent=2))
    print("\nMentions by match_type (spans + enum parts):", json.dumps(by_type, indent=2))
    if recon_resolvable:
        print(f"\nRecon-resolvable mentions: {recon_resolvable}")
        print(f"  exact-match CATCHES (exact+synonym): {catches} ({catches/recon_resolvable:.0%})")
        print(f"  exact-match MISSES  (variation)    : {misses} ({misses/recon_resolvable:.0%})")
    print(f"Umbrella (non-Recon, positive for tagger only): {by_type['umbrella']}")
    if problems:
        print("\n!! VALIDATION PROBLEMS:")
        for p in problems:
            print("  -", p)
    else:
        print("\nAll offsets resolved and match_type labels validated OK.")


if __name__ == "__main__":
    main()
