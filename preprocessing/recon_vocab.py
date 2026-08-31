"""
recon_vocab.py

Single source of truth for the Recon pathway vocabulary: the raw 98 subsystem
names, the blocklist of non-literary model artifacts, and the extra surface forms
commonly used in the literature.

Kept dependency-free (no spacy/torch) so both the matching pipeline
(preprocessing/match_exact.py) and the LLM-side code (llm/booster.py,
llm/canonicalize.py) can import it cheaply.
"""

import json
from pathlib import Path

RECON_FILE = Path(__file__).resolve().parents[1] / "unique_pathways_from_recon.json"

# Recon3D subsystem labels that name a modelling construct rather than a metabolic
# pathway. Not a judgement call: each is selected by a structural test over the
# Recon3D reaction set, and the six tests together pick exactly these eight out of
# 98 subsystems with no false positive. Re-check with
# `scripts/audit_recon_subsystems.py`; the reason per name is:
#
#   miscellaneous                      non-specific label — 139 real enzymes
#                                      (catalase, pyrophosphatases) sharing no
#                                      biochemistry, 118 of them with a GPR
#   protein formation                  one gene-less reaction, PROTEIN_BS, 21
#                                      metabolites — a biomass-style summary
#   intracellular demand               151 reactions, all DM_/SK_, all a single
#                                      metabolite, no GPR
#   intracellular source/sink          95 reactions, same shape
#   r group synthesis                  6 reactions named "R group artificial flux"
#                                      and "R group to palmitate conversion"
#   biomass and maintenance functions  BIOMASS_reaction, two maintenance variants
#                                      and ATPM — the FBA objective
#   exchange/demand reaction           label/content mismatch: 3 reactions, none of
#                                      them EX_/DM_/SK_ (two are ceramidases with
#                                      genes, one a transporter). The real EX_
#                                      reactions live in Extracellular exchange
#   dietary fiber binding              12 gene-less reactions, every name "Binding
#                                      of <fiber> with <bile acid>" — adsorption,
#                                      not enzymatic conversion
#
# Corroborated downstream: across 777 abstracts retrieved for these names the 10k
# NER checkpoint predicts none of them as a pathway, and gt_100's 279 human spans
# contain none either.
RECON_BLOCKLIST: set[str] = {
    "miscellaneous",
    "protein formation",
    "intracellular demand",
    "intracellular source/sink",
    "r group synthesis",
    "biomass and maintenance functions",
    "exchange/demand reaction",
    "dietary fiber binding",
}

# Additional surface forms for Recon pathways that are commonly written differently
RECON_SYNONYMS: dict[str, list[str]] = {
    "citric acid cycle": [
        "TCA cycle", "tricarboxylic acid cycle", "Krebs cycle",
    ],
    "glycolysis/gluconeogenesis": [
        "glycolysis", "gluconeogenesis", "Warburg effect",
    ],
    "pentose phosphate pathway": [
        "PPP", "hexose monophosphate shunt", "pentose phosphate shunt",
    ],
    "fatty acid oxidation": [
        "beta-oxidation", "β-oxidation", "FAO", "fatty acid β-oxidation",
        "fatty acid beta-oxidation",
    ],
    "oxidative phosphorylation": [
        "OXPHOS", "electron transport chain", "ETC",
    ],
    "fatty acid synthesis": [
        "de novo lipogenesis", "DNL", "fatty acid biosynthesis",
        "lipogenesis",
    ],
    "bile acid synthesis": [
        "bile acid biosynthesis", "primary bile acid biosynthesis",
        "bile acid production",
    ],
    "nad metabolism": [
        "NAD+ metabolism", "NADH metabolism", "nicotinamide metabolism",
        "NAD metabolism",
    ],
    "keratan sulfate degradation": [
        "keratan-sulfate degradation",
    ],
    "vitamin b2 metabolism": [
        "riboflavin metabolism",
    ],
}


def load_recon_names(apply_blocklist: bool = True) -> list[str]:
    """The Recon subsystem names (98 raw, 90 after the blocklist)."""
    names = json.loads(RECON_FILE.read_text(encoding="utf-8"))
    if apply_blocklist:
        names = [n for n in names if n not in RECON_BLOCKLIST]
    return names
