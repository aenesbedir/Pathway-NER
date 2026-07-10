#!/usr/bin/env python3
"""
compare_model.py

Run the Run 005 pathway-NER model on the ground-truth articles and compare the
pathways it detects against the curated evidence pathways from the Excel.

Ground truth (per article): the set of Recon pathways the article is cited as
evidence for. We check whether the model, reading the article text, detects
those pathways by name.

Metric is recall-oriented: "did the model detect the pathway this article is
evidence for?" Precision against this GT is not meaningful because the GT is a
per-pathway evidence bibliography, not an exhaustive per-article annotation —
so a detected pathway not in the GT set is reported as an "extra", not an error.

Detected pathway = a model span whose (lowercased) text maps to a Recon
canonical name or one of its RECON_SYNONYMS (same vocabulary as match_exact.py).

Inputs:
  - models/pathway-ner-005/
  - ground_truth_articles.json   (from build_ground_truth.py)

Output:
  - model_005_vs_ground_truth.json
  - prints an aggregate summary

Run from repo root:
  /home/enes/sci-usage/venv310/bin/python3 \\
      playground/model_005_ground_truth_compare/compare_model.py
"""

import json
import sys
from pathlib import Path

import torch
from transformers import AutoTokenizer, BertForTokenClassification

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models/pathway-ner-005"
GT = HERE / "ground_truth_articles.json"
OUT = HERE / "model_005_vs_ground_truth.json"

# Reuse the sliding-window / word-level span reconstruction from the sibling script
sys.path.insert(0, str(ROOT / "playground/model_005_analysis"))
from predict_abstracts import predict  # noqa: E402

# ---- Recon term -> canonical pathway map (mirror of match_exact.py) ----
RECON_BLOCKLIST = {
    "miscellaneous", "protein formation", "intracellular demand",
    "intracellular source/sink", "r group synthesis",
    "biomass and maintenance functions", "exchange/demand reaction",
    "dietary fiber binding",
}
RECON_SYNONYMS = {
    "citric acid cycle": ["TCA cycle", "tricarboxylic acid cycle", "Krebs cycle"],
    "glycolysis/gluconeogenesis": ["glycolysis", "gluconeogenesis", "Warburg effect"],
    "pentose phosphate pathway": ["PPP", "hexose monophosphate shunt", "pentose phosphate shunt"],
    "fatty acid oxidation": ["beta-oxidation", "β-oxidation", "FAO", "fatty acid β-oxidation", "fatty acid beta-oxidation"],
    "oxidative phosphorylation": ["OXPHOS", "electron transport chain", "ETC"],
    "fatty acid synthesis": ["de novo lipogenesis", "DNL", "fatty acid biosynthesis", "lipogenesis"],
    "bile acid synthesis": ["bile acid biosynthesis", "primary bile acid biosynthesis", "bile acid production"],
    "nad metabolism": ["NAD+ metabolism", "NADH metabolism", "nicotinamide metabolism", "NAD metabolism"],
    "keratan sulfate degradation": ["keratan-sulfate degradation"],
    "vitamin b2 metabolism": ["riboflavin metabolism"],
}


def build_term_map() -> tuple[dict[str, str], dict[str, list[str]]]:
    recon = json.loads((ROOT / "unique_pathways_from_recon.json").read_text())
    term2pid = {}
    pid2terms = {}
    for name in recon:
        if name in RECON_BLOCKLIST:
            continue
        terms = [name] + RECON_SYNONYMS.get(name, [])
        pid2terms[name] = terms
        for t in terms:
            term2pid[t.lower()] = name
    return term2pid, pid2terms


def gt_present_in_text(gt: set[str], text: str, pid2terms: dict[str, list[str]]) -> set[str]:
    """GT pathways whose canonical name or any synonym literally appears in the
    text — i.e. the pathways a name-based NER model could *possibly* detect."""
    low = text.lower()
    present = set()
    for p in gt:
        for t in pid2terms.get(p, [p]):
            if t.lower() in low:
                present.add(p)
                break
    return present


def detect_pathways(text, tokenizer, model, device, term2pid):
    """Return {canonical_pathway: [surface forms]} detected in text."""
    hits = {}
    for span in predict(text, tokenizer, model, device):
        pid = term2pid.get(span["text"].lower().strip())
        if pid:
            hits.setdefault(pid, set()).add(span["text"])
    return {k: sorted(v) for k, v in hits.items()}


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = BertForTokenClassification.from_pretrained(str(MODEL_DIR)).to(device).eval()
    term2pid, pid2terms = build_term_map()

    articles = json.loads(GT.read_text(encoding="utf-8"))
    results = []
    tot_gt = tot_present = tot_tp_ft = 0

    for a in articles:
        gt = set(a["gt_inscope"])
        full = (a["abstract"] + "\n" + a["full_text"]).strip()
        det_ft = detect_pathways(full, tokenizer, model, device, term2pid)

        present = gt_present_in_text(gt, full, pid2terms)   # nameable GT subset
        tp_ft = gt & set(det_ft)

        tot_gt += len(gt)
        tot_present += len(present)
        tot_tp_ft += len(tp_ft)

        results.append({
            "pmid": a["pmid"],
            "pmcid": a["pmcid"],
            "title": a.get("title", ""),
            "gt_inscope": sorted(gt),
            "gt_present_in_text": sorted(present),
            "detected": sorted(det_ft),
            "matched": sorted(tp_ft),
            "missed_but_named": sorted(present - set(det_ft)),
            "missed_not_named": sorted(gt - present),
            "extra": sorted(set(det_ft) - gt),
            "detected_surface_forms": det_ft,
        })
        print(f"{a['pmid']:>9} | GT {len(gt):>2} | named {len(present):>2} | "
              f"detected {len(det_ft):>2} | matched {len(tp_ft):>2} | "
              f"extra {len(set(det_ft) - gt):>2}")

    summary = {
        "articles": len(articles),
        "total_gt_inscope": tot_gt,
        "total_gt_named_in_text": tot_present,
        "matched": tot_tp_ft,
        "recall_vs_all_gt": round(tot_tp_ft / tot_gt, 4) if tot_gt else 0,
        "recall_vs_named_gt": round(tot_tp_ft / tot_present, 4) if tot_present else 0,
        "note": ("recall_vs_named_gt is the true model metric: of GT pathways "
                 "actually written by name in the article, how many the model "
                 "detected. recall_vs_all_gt is dragged down by blanket-citation "
                 "articles (genome-scale metabolic-model papers) whose GT "
                 "subsystem labels never appear as prose."),
    }
    OUT.write_text(json.dumps({"summary": summary, "per_article": results},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print("─" * 60)
    print(json.dumps(summary, indent=2))
    print(f"Output: {OUT}")


if __name__ == "__main__":
    main()
