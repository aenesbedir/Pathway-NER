"""Trial prompts for the LLM audit, scored against the 25 curated abstracts.

Companion to scripts/compare_review_vs_curation.py. That script shows where the
production audit prompt fell short of the curator; this one tests whether the
shortfalls are properties of the prompt or of the model, by running alternative
prompts over the same 25 abstracts and scoring them the same way.

Two channels are tested separately, because the curator's additions split into
two kinds: 16 spans with no pipeline counterpart (discovery) and 4 that widen a
pipeline span (boundary).

  discovery  A  the production prompt's own "missed" instruction, isolated
             B  recall-first: a positive definition, a short exclusion list,
                verbatim quoting required
             C  B followed by a filter call that keeps only noun phrases with a
                process head and a named compound
  boundary   D  every pipeline span is shown; the judge returns the span an
                annotator would draw. No constraint on what may be added.
             E  D plus an explicit list of what must not be added (location,
                agent nouns, a second coordinated process, results)

Scores: discovery recall = curator additions found / 20; precision counts a
proposal wrong when it is neither a curator addition nor an existing span.
Boundary: real boundary errors fixed / 4, and correct spans broken / 49.

The judge model is whatever `rawclaude` resolves to unless --model is given;
the id that answered is recorded per call.

Usage:
    python scripts/review_prompt_trials.py [--model opus] [--workers 8]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT125 = ROOT / "doccano/golden_dataset/gt_125/gt_125.jsonl"
SILVER = ROOT / "doccano/curation/missing_test_sample_25_import.jsonl"
OUT = ROOT / "doccano/golden_dataset/gt_125/review_prompt_trials.json"

PROMPT_A = """You are auditing a biomedical NER pipeline. Entity type is PATHWAY: a named
metabolic or biochemical route, or a named handling process for a class of
compounds. Not pathways: bare process nouns, single metabolites, genes, enzymes,
diseases, cell-fate and stress processes (apoptosis, oxidative stress,
inflammation), experimental methods.

The pipeline already found these spans: {found}

List any pathway mention in the abstract it missed entirely. Reply with JSON
only: {{"missed": ["<exact substring>", ...]}}

ABSTRACT:
{text}
"""

PROMPT_B = """Read this biomedical abstract and list every phrase that names a biological
process involving the transformation, movement, or turnover of a chemical
compound or class of compounds. Include: metabolic routes, biosynthesis and
degradation, uptake/transport/absorption/efflux, homeostasis of a named
substance, enzymatic modification of a substrate, and named cycles or pathways.

Exclude phrases naming only: a substance, a gene, a protein or enzyme, a disease,
a measurement or method, or a cell-level outcome such as apoptosis or
proliferation with no compound named.

Quote each phrase exactly as it appears, including qualifiers such as "de novo",
a trailing "pathway", and any parenthesised abbreviation.

Reply with JSON only: {{"missed": ["<exact substring>", ...]}}

Some phrases are already recorded, do not repeat them: {found}

ABSTRACT:
{text}
"""

PROMPT_FILTER = """These phrases were proposed as PATHWAY entities in the abstract below. Decide
which ones an annotator would actually mark.

Keep a phrase when it is a noun phrase naming a process, with a process head noun
(metabolism, synthesis, biosynthesis, degradation, catabolism, oxidation,
hydrolysis, uptake, absorption, transport, homeostasis, turnover, utilization,
formation, lipoylation, glycosylation, cycle, pathway ...) and a named compound
or compound class attached to it.

Drop a phrase when it is:
  - a clause describing one reaction rather than naming a process
    ("dephosphorylating X to Y", "transforms androgens to estrogens")
  - the release, secretion, trafficking or storage of a substance, or its entry
    into a compartment, rather than its chemical turnover
  - headed by genes, enzymes, machinery, proteins, receptors or a measurement
  - a named signalling cascade with no metabolic term in it (Wnt, PPAR, MAPK)
  - a restatement of a phrase already in the list

Reply with JSON only: {{"missed": ["<kept phrase>", ...]}}

CANDIDATES:
{cands}

ABSTRACT:
{text}
"""

PROMPT_D = """A biomedical NER pipeline marked the phrases below in this abstract as PATHWAY
entities. For each one, give the phrase a careful annotator would have marked
instead, if the offsets are wrong.

An annotated pathway phrase keeps the whole noun phrase: leading qualifiers such
as "de novo" or "hepatic", a trailing "pathway" or "cascade", a parenthesised
abbreviation that follows it, the object of an "of"-phrase and any "to X" or
"from X" continuation, and every member of a coordinated list under one head.
It never starts or ends mid-word and never cuts a compound name in half.

Reply with JSON only, one entry per input phrase, in order:
{{"spans": [{{"i": <index>, "corrected": "<exact substring, or the same text>"}}]}}

PHRASES:
{phrases}

ABSTRACT:
{text}
"""

PROMPT_E = """A biomedical NER pipeline marked the phrases below in this abstract as PATHWAY
entities. Most are right. Change one only when its offsets cut the phrase itself,
not when more context could be added.

Extend a phrase only for words that are part of the process name:
  - a leading qualifier that changes which process it is: "de novo", "non-oxidative"
  - a trailing "pathway", "cascade" or "cycle"
  - a parenthesised abbreviation immediately after it
  - the object of an "of"-phrase, with any "to X" / "from X" continuation
  - every member of a coordinated list sharing one head noun,
    as in "glucose and glutamine metabolism"

Never extend a phrase to take in:
  - where it happens: an organ, tissue, cell type, compartment or organism
    ("in the liver", "brain", "testicular", "within the amygdala")
  - what carries it out: "enzymes", "genes", "machinery", "proteins"
  - a second process joined by "and" that has its own head noun
    ("... and secretion", "... and bile secretion")
  - anything after the phrase that describes a result, a rate or a measurement

If a phrase is already correct, repeat it unchanged. Most phrases are correct.

Reply with JSON only, one entry per input phrase, in order:
{{"spans": [{{"i": <index>, "corrected": "<exact substring>"}}]}}

PHRASES:
{phrases}

ABSTRACT:
{text}
"""


def norm(s: str) -> str:
    return str(s).lower().strip(" .")


def call(prompt: str, model: str | None) -> tuple[dict, str | None]:
    extra = ["--output-format", "json"] + (["--model", model] if model else [])
    proc = subprocess.run(
        ["zsh", "-c", 'source ~/.zshrc >/dev/null 2>&1; rawclaude "$@"',
         "_", prompt, *extra], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[:300])
    env = json.loads(proc.stdout)
    usage = env.get("modelUsage") or {}
    top = env.get("usage") or {}
    who = next((m for m, u in usage.items()
                if (u.get("inputTokens"), u.get("cacheCreationInputTokens"))
                == (top.get("input_tokens"), top.get("cache_creation_input_tokens"))),
               None)
    m = re.search(r"\{.*\}", env.get("result", ""), re.S)
    return (json.loads(m.group(0)) if m else {}), who


def load():
    gold, silver = {}, {}
    for line in GT125.open(encoding="utf-8"):
        r = json.loads(line)
        if r["meta"].get("annotation_status") == "human_curated":
            gold[r["meta"]["pmid"]] = (r["text"], [(e["start_offset"], e["end_offset"])
                                                  for e in r["entities"]])
    for line in SILVER.open(encoding="utf-8"):
        r = json.loads(line)
        silver[r["meta"]["pmid"]] = [(s, e) for s, e, _ in r["label"]]
    return gold, silver


def score_discovery(gold, silver, pred: dict) -> dict:
    tp = fp = total = 0
    hits, false = [], []
    for pmid, (text, g) in gold.items():
        sv = set(silver[pmid])
        want = {norm(text[a:b]) for a, b in g if (a, b) not in sv}
        have = {norm(text[a:b]) for a, b in sv}
        total += len(want)
        for x in pred.get(pmid) or []:
            n = norm(x)
            if n in want:
                tp += 1
                hits.append(n)
            elif n not in have:
                fp += 1
                false.append(n)
    return {"tp": tp, "total": total, "fp": fp,
            "recall": round(tp / total, 3) if total else 0,
            "precision": round(tp / (tp + fp), 3) if tp + fp else 0,
            "hits": hits, "false": false}


def score_boundary(gold, silver, corr: dict) -> dict:
    need = fixed = ok = broke = 0
    detail = []
    for pmid, (text, g) in gold.items():
        gset = set(g)
        for i, (a, b) in enumerate(silver[pmid]):
            cur = text[a:b]
            ov = [x for x in g if a < x[1] and x[0] < b]
            target = text[ov[0][0]:ov[0][1]] if ((a, b) not in gset and ov) else None
            c = (corr.get(pmid) or {}).get(i)
            if target:
                need += 1
                if c and norm(c) == norm(target):
                    fixed += 1
                    detail.append(["fixed", cur, c])
                else:
                    detail.append(["missed", cur, c])
            elif c is None or c.strip() == cur.strip():
                ok += 1
            else:
                broke += 1
                detail.append(["broke", cur, c])
    return {"real_boundary_errors": need, "fixed": fixed,
            "correct_spans": ok + broke, "broken": broke, "detail": detail}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    gold, silver = load()
    models = Counter()

    def pool_map(fn):
        with ThreadPoolExecutor(args.workers) as pool:
            return dict(pool.map(fn, gold))

    def discovery(prompt):
        def one(pmid):
            text, _ = gold[pmid]
            found = [text[a:b] for a, b in silver[pmid]]
            try:
                r, who = call(prompt.format(text=text, found=json.dumps(found)), args.model)
                models[who] += 1
                return pmid, r.get("missed") or []
            except Exception:
                return pmid, []
        return pool_map(one)

    def filtered(cands):
        def one(pmid):
            text, _ = gold[pmid]
            c = cands.get(pmid) or []
            if not c:
                return pmid, []
            try:
                r, who = call(PROMPT_FILTER.format(text=text, cands=json.dumps(c)), args.model)
                models[who] += 1
                return pmid, r.get("missed") or []
            except Exception:
                return pmid, c
        return pool_map(one)

    def boundary(prompt):
        def one(pmid):
            text, _ = gold[pmid]
            ph = "\n".join(f"[{i}] {text[a:b]!r}" for i, (a, b) in enumerate(silver[pmid]))
            if not ph:
                return pmid, {}
            try:
                r, who = call(prompt.format(text=text, phrases=ph), args.model)
                models[who] += 1
                return pmid, {v.get("i"): v.get("corrected") for v in (r.get("spans") or [])
                              if isinstance(v, dict)}
            except Exception:
                return pmid, {}
        return pool_map(one)

    a = discovery(PROMPT_A)
    b = discovery(PROMPT_B)
    c = filtered(b)
    d = boundary(PROMPT_D)
    e = boundary(PROMPT_E)

    out = {
        "basis": {"curated_docs": len(gold),
                  "curator_additions": sum(1 for p, (t, g) in gold.items()
                                           for s in g if s not in set(silver[p])),
                  "pipeline_spans": sum(len(v) for v in silver.values()),
                  "judge_model": dict(models),
                  "judge_model_requested": args.model},
        "discovery": {
            "A_audit_prompt_missed": score_discovery(gold, silver, a),
            "B_recall_first": score_discovery(gold, silver, b),
            "C_recall_first_plus_filter": score_discovery(gold, silver, c),
        },
        "boundary": {
            "D_unconstrained": score_boundary(gold, silver, d),
            "E_constrained": score_boundary(gold, silver, e),
        },
        "prompts": {"A": PROMPT_A, "B": PROMPT_B, "filter": PROMPT_FILTER,
                    "D": PROMPT_D, "E": PROMPT_E},
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    print("judge:", dict(models))
    for k, v in out["discovery"].items():
        print(f"{k:28} recall {v['tp']}/{v['total']}={v['recall']:.2f}  "
              f"precision {v['precision']:.2f}  ({v['fp']} not gold)")
    for k, v in out["boundary"].items():
        print(f"{k:28} fixed {v['fixed']}/{v['real_boundary_errors']}  "
              f"broke {v['broken']}/{v['correct_spans']}")


if __name__ == "__main__":
    main()
