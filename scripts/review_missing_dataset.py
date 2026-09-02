"""LLM review of the missing-pathway staged spans.

Each sampled abstract is sent to a raw Claude session (the `rawclaude` shell
function from ~/.zshrc: no system prompt, no CLAUDE.md, no tools, no MCP) with
the prompt held in REVIEW_PROMPT below. The judge sees the title, the abstract
and the numbered spans produced by the three stages (ner / boost / dict) and
returns a verdict per span plus any pathway mention the pipeline missed.

The PATHWAY definition in the prompt is not written from scratch: it is read off
the human-annotated gold set (doccano/golden_dataset/gt_100.jsonl, 279 PATHWAY
spans) so that the judge applies the project's own annotation convention. In
particular gt_100 labels qualified generic terms ("energy metabolism" 9x, "lipid
metabolism" 10x) and never labels apoptosis, oxidative stress, inflammation or
bare metabolites; an earlier version of this prompt got both of those wrong.

Usage:
    python scripts/review_missing_dataset.py --limit 120 --workers 4

Writes data/processed/missing_pathways/llm_review.jsonl (one record per
abstract, verbatim judge JSON) and llm_review.json (aggregate counts).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = ROOT / "data/processed/missing_pathways/paironly_stages.jsonl"
ARTICLES = ROOT / "data/raw/missing_pathways/articles.json"
OUT_JSONL = ROOT / "data/processed/missing_pathways/llm_review.jsonl"
OUT_JSON = ROOT / "data/processed/missing_pathways/llm_review.json"

REVIEW_PROMPT = """You are auditing the output of a biomedical named-entity \
recognition pipeline. The entity type is PATHWAY. The definition below is not \
generic: it is read off the project's human-annotated gold set (gt_100, 279 \
PATHWAY spans over 100 abstracts). Follow it even where it disagrees with your \
own intuition about what deserves to be called a pathway.

WHAT COUNTS AS A PATHWAY

A named metabolic or biochemical route, or a named handling/turnover process for \
a class of compounds. Real gold spans include:

    glycolysis / tricarboxylic acid cycle / pentose phosphate pathway (PPP)
    de novo purine synthesis (DNPS) / heme synthesis / CoA biosynthesis
    cholesterol metabolism / cholesterol production / purine catabolism pathway
    sphingolipid (SL) metabolism / heparan sulfate degradation
    ROS detoxification / production of reactive oxygen species / reactive oxygen
        species handling
    oxidative phosphorylation (OXPHOS) / prostanoid synthesis
    valine/leucine/isoleucine biosynthesis
    pyrimidine, fatty acid, and amino acid metabolism   (one span, not three)

A generic process noun becomes a pathway once it carries a qualifier naming what \
is metabolised or where. These are all gold spans, so mark them correct:

    energy metabolism (9x) / lipid metabolism (10x) / glucose metabolism (3x)
    oxidative metabolism / mitochondrial metabolism / glycolytic metabolism
    mitochondrial energy metabolism

WHAT DOES NOT COUNT

The gold annotators saw all of the following in the same abstracts and left every
occurrence unlabelled, so they are wrong spans, not near-misses:

  - the bare process noun with no qualifier: "metabolism", "synthesis",
    "activity", "biosynthesis" standing alone
  - single metabolites, genes, proteins, enzymes: "cholesterol" (9 occurrences,
    0 labelled), "estradiol", "HMG-CoA reductase"
  - cell-fate and stress processes that are not compound turnover: "apoptosis"
    (5 occurrences, 0 labelled), "oxidative stress" (9, 0), "autophagy" (1, 0),
    "inflammation" (19, 0), "proliferation" (8, 0), "signal transduction",
    "ferroptosis"
  - diseases and phenotypes, including ones named after a pathway: "urea cycle
    disorders", "insulin resistance" (5, 0)
  - chemical damage events such as adduct formation
  - experimental methods, tissues, cell types, and modelling artefacts

BOUNDARIES

The gold set takes the whole phrase. Concretely:

  - a trailing "pathway"/"cascade" is inside the span (21 gold spans end this
    way: "purine catabolism pathway", "arachidonic acid (AA) cascade")
  - a leading "de novo" or other qualifier is inside the span ("de novo
    lipogenesis", "de novo fatty acid synthesis pathway")
  - a parenthesised abbreviation right after the phrase is inside the span
    ("pentose phosphate pathway (PPP)", "glutathione (GSH) metabolism")
  - an "X of Y" phrase keeps Y and any "to Z" continuation: "metabolism of
    arachidonic acid", "conversion of phenylalanine to tyrosine", "hepatic
    conversion of vitamin D to 25-OHD"
  - a coordinated list under one head is a single span
  - a span must never start or end mid-word

THE TASK

Below is one PubMed abstract and the spans the pipeline predicted in it. Each \
span carries the stage that produced it: "ner" (the trained model), "booster" (a \
deterministic pattern rule) or "dict" (a curated surface-form dictionary, which \
also assigns a canonical Recon3D pathway name).

For every span decide:
  - verdict: "correct" if the span is a pathway mention under the definition
    above AND its offsets match the boundary rules; "boundary" if it is a genuine
    pathway mention but the offsets cut it short or include extra words; "wrong"
    if it is not a pathway mention at all.
  - canonical_ok: true/false/null - only for spans that carry a canonical,
    whether that canonical name is a fair normalisation of the span text. Mark
    false when the canonical is broader or narrower than what the span says.
    Use null when there is no canonical.
  - reason: at most 15 words.

Then list any pathway mention in the abstract that the pipeline missed entirely. \
Apply the same definition - do not list apoptosis, oxidative stress, inflammation \
or other excluded categories as missed.

Reply with JSON only, no prose, no markdown fence:
{"spans": [{"i": <index>, "verdict": "...", "canonical_ok": <bool|null>, \
"reason": "..."}], "missed": ["<exact substring>", ...]}

TITLE: {title}

ABSTRACT:
{abstract}

SPANS:
{spans}
"""


def build_prompt(rec: dict, art: dict) -> str:
    lines = []
    for i, s in enumerate(rec["spans"]):
        canon = s.get("canonical") or "-"
        lines.append(
            f'[{i}] "{s["text"]}" (chars {s["start"]}-{s["end"]}, '
            f'stage={s["source"]}, canonical={canon})'
        )
    return (
        REVIEW_PROMPT.replace("{title}", art.get("title") or "")
        .replace("{abstract}", art.get("abstract") or "")
        .replace("{spans}", "\n".join(lines))
    )


def rawclaude(prompt: str) -> str:
    """Call the zshrc `rawclaude` function with the prompt as its argument."""
    proc = subprocess.run(
        ["zsh", "-c", 'source ~/.zshrc >/dev/null 2>&1; rawclaude "$1"', "_", prompt],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:400] or "rawclaude failed")
    return proc.stdout.strip()


def parse(out: str) -> dict:
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise ValueError("no JSON in reply")
    return json.loads(m.group(0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=120, help="abstracts to sample")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    arts = {a["pmid"]: a for a in json.loads(ARTICLES.read_text())}
    recs = [json.loads(line) for line in STAGES.read_text().splitlines() if line.strip()]
    recs = [r for r in recs if r["spans"] and r["pmid"] in arts]

    # Keep every abstract that carries a dict or boost span - those are the
    # layers under evaluation - and fill the rest of the budget at random.
    special = [r for r in recs if any(s["source"] != "ner" for s in r["spans"])]
    rest = [r for r in recs if r not in special]
    random.Random(args.seed).shuffle(rest)
    sample = (special + rest)[: args.limit]

    def work(rec: dict) -> dict:
        art = arts[rec["pmid"]]
        try:
            verdict = parse(rawclaude(build_prompt(rec, art)))
            err = None
        except Exception as exc:  # noqa: BLE001 - recorded, not raised
            verdict, err = {"spans": [], "missed": []}, f"{type(exc).__name__}: {exc}"
        return {
            "pmid": rec["pmid"],
            "pathways": rec["pathways"],
            "route": rec["route"],
            "spans": rec["spans"],
            "review": verdict,
            "error": err,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        out = list(pool.map(work, sample))

    with OUT_JSONL.open("w") as fh:
        for rec in out:
            fh.write(json.dumps(rec) + "\n")

    by_stage: dict[str, Counter] = {}
    canon = Counter()
    missed = 0
    failed = 0
    for rec in out:
        if rec["error"]:
            failed += 1
            continue
        missed += len(rec["review"].get("missed") or [])
        for v in rec["review"].get("spans") or []:
            i = v.get("i")
            if not isinstance(i, int) or i >= len(rec["spans"]):
                continue
            stage = rec["spans"][i]["source"]
            by_stage.setdefault(stage, Counter())[v.get("verdict", "?")] += 1
            if v.get("canonical_ok") is not None:
                canon[bool(v["canonical_ok"])] += 1

    summary = {
        "sampled": len(out),
        "failed": failed,
        "by_stage": {k: dict(v) for k, v in by_stage.items()},
        "canonical_ok": {"true": canon[True], "false": canon[False]},
        "missed_mentions": missed,
    }
    OUT_JSON.write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
