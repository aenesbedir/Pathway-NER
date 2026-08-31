#!/usr/bin/env python3
"""
pathway_surface_forms.py

One dictionary of literature surface forms per Recon canonical pathway name.

Why this exists
---------------
Section 6.3 of the progress report measured that 627 documents contain their
pathway query term verbatim in the abstract yet carry no annotated PATHWAY span.
The silver pipeline did have a deterministic component (``llm/booster.py``), but
it was built for a narrower job: recovering word-order reversals
("metabolism of androgens") and dedup losses. It searches
``<content> <process>`` and ``<process> of <content>`` patterns derived from the
canonical name, and it never sees:

  - the canonical name itself as a phrase,
  - the literature abbreviations (TCA cycle, OXPHOS, BCAA metabolism),
  - the KEGG names of the same pathway (retinol metabolism = vitamin A metabolism),
  - the split forms of a multi-substrate canonical ("alanine and aspartate
    metabolism" written as "aspartate metabolism" alone).

This module produces that missing vocabulary. Each canonical maps to a list of
surface forms; ``llm/booster.py`` scans them verbatim, so a match is an exact
phrase hit rather than a pattern guess, which is why these forms need no
``direction_ok`` guard.

Sources, in decreasing order of trust
-------------------------------------
1. ``MESH_ENTRY_FORMS``  — NLM entry terms, derived by
   ``scripts/generate_mesh_forms.py``. The only table whose contents were read
   off an external authority rather than asserted.
2. ``MANUAL_FORMS``      — hand-curated synonyms and abbreviations.
3. Generated forms       — mechanical rewrites of the canonical (see below).
4. ``KEGG_FORMS``        — KEGG pathway names taken from
   ``data/raw/kegg_recon3d/kegg_recon3d_matched_pathways.csv`` (match_score >= 0.8),
   curated: that file's ``kegg_id_crossref`` rows link pathway *identifiers*, not
   names, so several rows pair a Recon name with a much broader KEGG parent map
   ("Citric acid cycle" <- "Carbon metabolism"). Those live in ``KEGG_REJECTED``
   with a reason instead of being used as surface forms.

Generation rules
----------------
``distribute_forms()`` splits a canonical into head components and a process
tail, then recombines them:

    alanine and aspartate metabolism
        -> alanine metabolism, aspartate metabolism
    valine, leucine, and isoleucine metabolism
        -> valine metabolism, leucine metabolism, isoleucine metabolism
    squalene and cholesterol synthesis
        -> squalene synthesis, cholesterol synthesis
    androgen and estrogen synthesis and metabolism
        -> androgen synthesis and metabolism, estrogen synthesis and metabolism
        -> androgen synthesis, androgen metabolism,
           estrogen synthesis, estrogen metabolism
    glycolysis/gluconeogenesis        (no process tail)
        -> glycolysis, gluconeogenesis

``prefix_forms()`` drops a leading one-token qualifier for the canonicals listed
in ``PREFIX_STRIPPABLE`` only:

    n-glycan synthesis -> glycan synthesis

The whitelist matters. Stripping is wrong for stereochemistry and position
prefixes: "d-alanine metabolism" is not "alanine metabolism" (a different
canonical), and "beta-alanine metabolism" is not "alanine metabolism" either.

Score comments
--------------
Every surface form in MANUAL_FORMS, ABBREVIATION_FORMS and KEGG_FORMS carries a
``# <score>`` comment: how completely the form denotes the canonical pathway,
100 for an exact match and 0 for none.

    100  the canonical name itself, or a difference only in spelling,
         punctuation, word order, or an interchangeable process word
         ("fatty acid biosynthesis" for "fatty acid synthesis")
     90  an established full synonym of the same pathway ("Krebs cycle")
     80  the same pathway named after one enzyme, product, or process step
         ("transsulfuration pathway", "drug biotransformation")
     70  a proper sub-process, one branch, or one direction of the canonical
         ("kynurenine pathway" is one branch of tryptophan metabolism)
     60  a substrate-split form of a multi-substrate canonical, or an
         abbreviation that is ambiguous outside a metabolic context ("ETC")
     50  related but with a clearly different scope
     30  weak: the form probably belongs to a different canonical
         ("cholesterol biosynthesis" is closer to "squalene and cholesterol
         synthesis")

Forms scoring below 70 are **commented out**, not deleted: 70 is the cutoff for
a form the pipeline actually scans. The commented lines keep the decision and
its score visible, so re-enabling one is a matter of removing a "#" rather than
re-deriving the judgement.

Two caveats about that cutoff. First, it applies to these three tables only —
``distribute_forms()`` still generates substrate-split forms at runtime
("fructose metabolism" from "fructose and mannose metabolism"), so commenting
out the hand-written duplicate does not remove the generated one. Second,
``RECON_SYNONYMS`` in ``preprocessing/recon_vocab.py`` is folded in unscored, so
a form commented out here can still reach the dictionary from there — check the
``--json`` dump rather than this file when a form's fate matters. ("ETC" is not
such a case: it is in RECON_SYNONYMS but three characters long, and the
case-insensitive path drops anything under _MIN_HEAD_LEN.)

A ``mesh:<verdict>`` suffix records what MeSH says about the form, computed by
``scripts/ground_surface_forms.py`` from ``data/raw/mesh_metabolic_pathways.json``
and ``data/raw/mesh_substances.json``. It exists because the scores above were
written from domain knowledge alone; the tag says whether NLM agrees.

    desc_confirmed  form and canonical are the same MeSH descriptor
    desc_conflict   both are descriptors, but different ones
    desc_form_only  the form is a descriptor, the canonical is not
    sub_confirmed   the substance halves resolve to one descriptor
    sub_narrower    the form's substance is a descendant of the canonical's
    sub_broader     the form's substance is an ancestor — it over-matches
    sub_conflict    different substances, no ancestry between them
    sub_unresolved  a substance has no MeSH descriptor (every abbreviation)
    ungrounded      MeSH says nothing about this string either way

The tag is evidence, not a verdict on the form. MeSH models concepts while Recon
models metabolic subsystems, and they do not partition the space alike: MeSH has
no "electron transport chain" string at all, and it files Kynurenine apart from
Tryptophan though the kynurenine pathway is a branch of tryptophan metabolism.
A ``sub_broader`` tag is the one worth acting on — it means the form denotes a
superset of the canonical and will pull in mentions that belong elsewhere.

A ``gold:N`` suffix means the form occurs in N PATHWAY spans of the reviewed
golden set (``doccano/golden_dataset/gt_100.jsonl``), counting both whole-span
matches and occurrences inside a longer annotated span. 106 of the 393 forms are
attested there; the rest are unattested, which is not evidence against them —
gt_100 is 100 abstracts and contains 188 distinct pathway strings in total.
Scores without a ``gold:`` suffix rest on the canonical name and on standard
biochemical nomenclature, not on measurement in this corpus.

Matching contract for consumers
-------------------------------
``build_surface_forms()`` returns ``{canonical: [SurfaceForm, ...]}``.
``SurfaceForm.case_sensitive`` is True for acronyms (PPP, ETC, FAO): lowercased
they collide with ordinary English, and "etc" would match every third abstract.
Everything else is matched case-insensitively.

Review and use
--------------
    venv310/bin/python3 preprocessing/pathway_surface_forms.py            # table
    venv310/bin/python3 preprocessing/pathway_surface_forms.py --json     # dump
    venv310/bin/python3 preprocessing/pathway_surface_forms.py --conflicts

Kept dependency-free (no spacy/torch) like ``recon_vocab.py``, so the LLM-side
code can import it cheaply.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from recon_vocab import RECON_SYNONYMS, load_recon_names

REPO_ROOT = Path(__file__).resolve().parents[1]

# The KEGG/Recon3D crossmatch table produced in the kegg-abstracts worktree.
KEGG_MATCH_FILE = (
    REPO_ROOT
    / ".claude/worktrees/kegg-abstracts/data/raw/kegg_recon3d"
    / "kegg_recon3d_matched_pathways.csv"
)
KEGG_MIN_SCORE = 0.8


# ---------------------------------------------------------------------------
# Process vocabulary
# ---------------------------------------------------------------------------

# Trailing words that name the process rather than the substrate. Longest first
# so the alternation prefers the longer form. Kept in sync with the list in
# llm/booster.py; this module owns the phrase-level view of it.
PROCESS_WORDS = [
    "metabolic pathway",
    "biosynthesis",
    "degradation",
    "catabolism",
    "metabolism",
    "production",
    "formation",
    "oxidation",
    "synthesis",
    "pathway",
    "cycle",
]
_PROCESS_RE = "|".join(re.escape(p) for p in PROCESS_WORDS)
_CONNECTOR_SPLIT = re.compile(r"\s+and\s+|\s*,\s*|\s*/\s*")

# A generated head component shorter than this is dropped: "coa", "nad" and "ros"
# are handled through MANUAL_FORMS instead, where the surrounding phrase is known.
_MIN_HEAD_LEN = 4

# Acronyms are matched case-sensitively, so three characters is safe enough.
_MIN_ACRONYM_LEN = 3


# ---------------------------------------------------------------------------
# Manual vocabulary
# ---------------------------------------------------------------------------

# Literature synonyms. RECON_SYNONYMS (preprocessing/recon_vocab.py) is folded in
# automatically at build time; this table extends it. Written lowercase, matched
# case-insensitively.
MANUAL_FORMS: dict[str, list[str]] = {
    "glycolysis/gluconeogenesis": [
        "glycolytic pathway",  # 90  mesh:ungrounded
        "glycolytic flux",  # 70  mesh:ungrounded
        "aerobic glycolysis",  # 80  mesh:ungrounded
        "anaerobic glycolysis",  # 80  mesh:ungrounded
        "embden-meyerhof pathway",  # 95  mesh:desc_form_only
        "embden-meyerhof-parnas pathway",  # 95  mesh:desc_form_only
    ],
    "citric acid cycle": [
        "tca cycle",  # 100  gold:1  mesh:sub_unresolved
        "tricarboxylic acid cycle",  # 100  gold:1  mesh:desc_confirmed
        "krebs cycle",  # 100  mesh:desc_confirmed
        "citrate cycle",  # 95  mesh:sub_confirmed
    ],
    "oxidative phosphorylation": [
        "electron transport chain",  # 70  mesh:ungrounded
        "respiratory chain",  # 70  mesh:desc_conflict
        "mitochondrial respiratory chain",  # 70  mesh:ungrounded
        # "electron transfer chain",  # 60  mesh:not_in_dictionary
    ],
    "pentose phosphate pathway": [
        "hexose monophosphate shunt",  # 95  mesh:desc_confirmed
        "hexose monophosphate pathway",  # 95  mesh:sub_unresolved
        "pentose phosphate shunt",  # 95  mesh:desc_confirmed
        "phosphogluconate pathway",  # 90  mesh:sub_unresolved
    ],
    "fatty acid oxidation": [
        "beta-oxidation",  # 90  mesh:ungrounded
        "beta oxidation",  # 90  mesh:sub_unresolved
        "fatty acid beta-oxidation",  # 95  mesh:ungrounded
        "fatty acid β-oxidation",  # 95  gold:2  mesh:ungrounded
        "β-oxidation",  # 90  mesh:ungrounded
        "mitochondrial fatty acid oxidation",  # 90  mesh:sub_unresolved
        "peroxisomal beta-oxidation",  # 80  mesh:ungrounded
    ],
    "fatty acid synthesis": [
        "de novo lipogenesis",  # 85  gold:1  mesh:ungrounded
        "lipogenesis",  # 75  mesh:desc_form_only
        "de novo fatty acid synthesis",  # 95  mesh:sub_unresolved
        "fatty acid biosynthesis",  # 100  gold:1  mesh:sub_confirmed
    ],
    "bile acid synthesis": [
        "bile acid biosynthesis",  # 100  mesh:sub_confirmed
        "primary bile acid biosynthesis",  # 90  mesh:sub_unresolved
        "bile acid production",  # 90  mesh:sub_confirmed
        "bile acid formation",  # 90  mesh:sub_confirmed
    ],
    "nad metabolism": [
        "nad+ metabolism",  # 100  gold:1  mesh:sub_confirmed
        "nadh metabolism",  # 90  mesh:sub_confirmed
        "nicotinamide metabolism",  # 80  mesh:sub_conflict
        "nad biosynthesis",  # 80  gold:1  mesh:sub_confirmed
        "nad+ biosynthesis",  # 80  mesh:sub_confirmed
        "nad salvage pathway",  # 70  mesh:sub_unresolved
        "nicotinate and nicotinamide metabolism",  # 90  mesh:sub_unresolved
    ],
    "coa synthesis": [
        "coenzyme a synthesis",  # 100  mesh:sub_confirmed
        "coenzyme a biosynthesis",  # 100  mesh:sub_confirmed
        "coa biosynthesis",  # 100  gold:1  mesh:sub_confirmed
        "pantothenate and coa biosynthesis",  # 85  mesh:sub_unresolved
    ],
    "coa catabolism": [
        "coenzyme a catabolism",  # 100  mesh:sub_confirmed
        "coenzyme a degradation",  # 95  mesh:sub_confirmed
        "coa degradation",  # 95  mesh:sub_confirmed
    ],
    "ros detoxification": [
        "reactive oxygen species detoxification",  # 100  mesh:ungrounded
        "ros scavenging",  # 90  mesh:ungrounded
        # "antioxidant defense",  # 60  mesh:not_in_dictionary
        # "antioxidant defence",  # 60  mesh:not_in_dictionary
    ],
    "urea cycle": [
        "ornithine cycle",  # 95  mesh:sub_conflict
        # "urea cycle disorder",  # 40  mesh:not_in_dictionary
        "ureagenesis",  # 85  mesh:ungrounded
    ],
    "valine, leucine, and isoleucine metabolism": [
        "branched-chain amino acid metabolism",  # 95  mesh:sub_broader
        "branched chain amino acid metabolism",  # 95  mesh:sub_broader
        "bcaa metabolism",  # 95  mesh:sub_unresolved
        "branched-chain amino acid catabolism",  # 85  mesh:sub_broader
        "bcaa catabolism",  # 85  mesh:sub_unresolved
    ],
    "tryptophan metabolism": [
        "trp metabolism",  # 100  gold:2  mesh:sub_unresolved
        "kynurenine pathway",  # 75  gold:4  mesh:sub_conflict
        "tryptophan-kynurenine pathway",  # 85  mesh:sub_unresolved
    ],
    "vitamin a metabolism": [
        "retinol metabolism",  # 95  gold:1  mesh:sub_confirmed
        "retinoid metabolism",  # 85  mesh:sub_broader
        "retinoic acid metabolism",  # 75  mesh:sub_narrower
    ],
    "vitamin b2 metabolism": [
        "riboflavin metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "vitamin b6 metabolism": [
        "pyridoxine metabolism",  # 90  mesh:sub_narrower
        "pyridoxal phosphate metabolism",  # 85  mesh:sub_narrower
    ],
    "vitamin b12 metabolism": [
        "cobalamin metabolism",  # 100  mesh:sub_confirmed
    ],
    "vitamin c metabolism": [
        "ascorbate metabolism",  # 95  mesh:sub_confirmed
        "ascorbic acid metabolism",  # 95  mesh:sub_confirmed
        "ascorbate and aldarate metabolism",  # 80  mesh:sub_unresolved
    ],
    "vitamin d metabolism": [
        "calciferol metabolism",  # 90  mesh:sub_narrower
        "cholecalciferol metabolism",  # 85  mesh:sub_narrower
        "25-hydroxyvitamin d metabolism",  # 70  mesh:sub_unresolved
    ],
    "vitamin e metabolism": [
        "tocopherol metabolism",  # 95  mesh:sub_narrower
        "alpha-tocopherol metabolism",  # 90  mesh:sub_narrower
    ],
    "folate metabolism": [
        "one carbon pool by folate",  # 85  mesh:ungrounded
        "one-carbon metabolism",  # 75  gold:3  mesh:sub_unresolved
        "folate cycle",  # 90  mesh:sub_confirmed
        "folic acid metabolism",  # 95  mesh:sub_confirmed
    ],
    "tetrahydrobiopterin metabolism": [
        "bh4 metabolism",  # 100  mesh:sub_unresolved
        "tetrahydrobiopterin biosynthesis",  # 85  mesh:sub_unresolved
        "bh4 biosynthesis",  # 85  mesh:sub_unresolved
    ],
    "glutathione metabolism": [
        "gsh metabolism",  # 100  gold:6  mesh:sub_unresolved
        "glutathione synthesis",  # 80  mesh:sub_confirmed
        "glutathione biosynthesis",  # 80  mesh:sub_confirmed
        "glutathione redox cycle",  # 70  mesh:sub_unresolved
    ],
    "heme synthesis": [
        "heme biosynthesis",  # 100  mesh:sub_confirmed
        "haem biosynthesis",  # 95  mesh:sub_confirmed
        "haem synthesis",  # 95  mesh:sub_confirmed
        "porphyrin biosynthesis",  # 85  mesh:sub_broader
    ],
    "heme degradation": [
        "haem degradation",  # 95  mesh:sub_confirmed
        "heme catabolism",  # 100  mesh:sub_confirmed
        "heme breakdown",  # 95  mesh:ungrounded
        "bilirubin metabolism",  # 70  mesh:sub_conflict
    ],
    "arachidonic acid metabolism": [
        "arachidonate metabolism",  # 95  mesh:sub_confirmed
        # "aa metabolism",  # 40  mesh:not_in_dictionary
    ],
    "eicosanoid metabolism": [
        "prostaglandin metabolism",  # 70  mesh:sub_narrower
        "prostanoid metabolism",  # 70  mesh:sub_narrower
    ],
    "leukotriene metabolism": [
        "leukotriene biosynthesis",  # 90  mesh:sub_confirmed
        "lipoxygenase pathway",  # 75  mesh:sub_conflict
    ],
    "linoleate metabolism": [
        "linoleic acid metabolism",  # 100  gold:2  mesh:sub_confirmed
    ],
    "sphingolipid metabolism": [
        "ceramide metabolism",  # 70  mesh:sub_narrower
        "sphingolipid biosynthesis",  # 85  mesh:sub_confirmed
        "de novo sphingolipid synthesis",  # 80  mesh:sub_unresolved
    ],
    "glycerophospholipid metabolism": [
        "phospholipid metabolism",  # 80  gold:1  mesh:sub_broader
        "glycerophospholipid biosynthesis",  # 90  mesh:sub_confirmed
    ],
    "phosphatidylinositol phosphate metabolism": [
        "phosphoinositide metabolism",  # 90  mesh:sub_broader
        # "pi3k pathway",  # 40  mesh:not_in_dictionary
        # "phosphatidylinositol signaling",  # 60  mesh:not_in_dictionary
        # "phosphatidylinositol signalling",  # 60  mesh:not_in_dictionary
    ],
    "triacylglycerol synthesis": [
        "triglyceride synthesis",  # 100  mesh:sub_confirmed
        "triacylglycerol biosynthesis",  # 100  mesh:sub_confirmed
        "triglyceride biosynthesis",  # 100  mesh:sub_confirmed
    ],
    "cholesterol metabolism": [
        "cholesterol homeostasis",  # 70  mesh:ungrounded
        # "cholesterol biosynthesis",  # 30  mesh:not_in_dictionary
        "sterol metabolism",  # 70  mesh:sub_broader
    ],
    "squalene and cholesterol synthesis": [
        "mevalonate pathway",  # 85  mesh:sub_conflict
        "cholesterol biosynthetic pathway",  # 90  mesh:sub_unresolved
        "isoprenoid biosynthesis",  # 70  mesh:sub_broader
        "terpenoid backbone biosynthesis",  # 70  mesh:sub_unresolved
    ],
    "steroid metabolism": [
        "steroidogenesis",  # 90  mesh:ungrounded
        "steroid hormone biosynthesis",  # 85  gold:2  mesh:sub_unresolved
        "steroid biosynthesis",  # 85  mesh:sub_confirmed
    ],
    "androgen and estrogen synthesis and metabolism": [
        "sex steroid metabolism",  # 85  mesh:sub_unresolved
        "estrogen biosynthesis",  # 70  mesh:sub_confirmed
        "androgen biosynthesis",  # 70  mesh:sub_confirmed
        # "aromatase pathway",  # 60  mesh:not_in_dictionary
    ],
    "purine synthesis": [
        "purine biosynthesis",  # 100  mesh:sub_confirmed
        "de novo purine synthesis",  # 90  gold:1  mesh:sub_unresolved
        "de novo purine biosynthesis",  # 90  mesh:sub_unresolved
    ],
    "purine catabolism": [
        "purine degradation",  # 100  mesh:sub_confirmed
        "purine breakdown",  # 95  mesh:ungrounded
    ],
    "pyrimidine synthesis": [
        "pyrimidine biosynthesis",  # 100  mesh:sub_confirmed
        "de novo pyrimidine synthesis",  # 90  mesh:sub_unresolved
        "de novo pyrimidine biosynthesis",  # 90  mesh:sub_unresolved
    ],
    "pyrimidine catabolism": [
        "pyrimidine degradation",  # 100  mesh:sub_confirmed
        "pyrimidine breakdown",  # 95  mesh:ungrounded
    ],
    "nucleotide salvage pathway": [
        "purine salvage pathway",  # 80  mesh:sub_unresolved
        "pyrimidine salvage pathway",  # 80  mesh:sub_unresolved
        "nucleotide salvage",  # 95  mesh:ungrounded
        # "salvage pathway",  # 30  mesh:not_in_dictionary
    ],
    "nucleotide interconversion": [
        "nucleotide interconversions",  # 100  mesh:ungrounded
    ],
    "aminosugar metabolism": [
        "amino sugar metabolism",  # 100  mesh:sub_unresolved
        "hexosamine biosynthetic pathway",  # 80  mesh:sub_unresolved
        "hexosamine pathway",  # 75  mesh:sub_unresolved
    ],
    "nucleotide sugar metabolism": [
        "nucleotide sugar biosynthesis",  # 90  mesh:sub_unresolved
    ],
    "hyaluronan metabolism": [
        "hyaluronic acid metabolism",  # 100  mesh:sub_confirmed
        "hyaluronan synthesis",  # 80  mesh:sub_confirmed
    ],
    "chondroitin sulfate degradation": [
        "chondroitin sulphate degradation",  # 100  mesh:sub_unresolved
        "chondroitin sulfate catabolism",  # 100  mesh:sub_confirmed
    ],
    "chondroitin synthesis": [
        "chondroitin sulfate biosynthesis",  # 90  mesh:sub_narrower
        "chondroitin sulphate biosynthesis",  # 90  mesh:sub_unresolved
        "chondroitin sulfate synthesis",  # 90  mesh:sub_narrower
    ],
    "keratan sulfate synthesis": [
        "keratan sulphate synthesis",  # 100  mesh:sub_unresolved
        "keratan-sulfate synthesis",  # 100  mesh:sub_confirmed
        "keratan sulfate biosynthesis",  # 100  mesh:sub_confirmed
    ],
    "keratan sulfate degradation": [
        "keratan-sulfate degradation",  # 100  mesh:sub_confirmed
        "keratan sulphate degradation",  # 100  mesh:sub_unresolved
    ],
    "heparan sulfate degradation": [
        "heparan sulphate degradation",  # 100  mesh:sub_unresolved
        "heparan sulfate catabolism",  # 100  mesh:sub_confirmed
    ],
    "n-glycan synthesis": [
        "n-linked glycosylation",  # 85  mesh:desc_form_only
        "n-glycosylation",  # 85  mesh:ungrounded
        "n-glycan biosynthesis",  # 100  mesh:sub_unresolved
    ],
    "o-glycan metabolism": [
        "o-linked glycosylation",  # 80  mesh:desc_form_only
        "o-glycosylation",  # 80  mesh:ungrounded
        "mucin type o-glycan biosynthesis",  # 75  mesh:sub_unresolved
    ],
    "n-glycan degradation": [
        "n-glycan catabolism",  # 100  mesh:sub_unresolved
    ],
    "glycosphingolipid metabolism": [
        "glycosphingolipid biosynthesis",  # 85  mesh:sub_confirmed
        "ganglioside metabolism",  # 70  mesh:sub_narrower
    ],
    "blood group synthesis": [
        "abo blood group biosynthesis",  # 90  mesh:sub_narrower
        "blood group biosynthesis",  # 95  mesh:sub_confirmed
    ],
    "drug metabolism": [
        "xenobiotic metabolism",  # 85  mesh:sub_narrower
        "metabolism of xenobiotics by cytochrome p450",  # 80  mesh:ungrounded
        "drug biotransformation",  # 90  mesh:ungrounded
    ],
    "cytochrome metabolism": [
        "cytochrome p450 metabolism",  # 90  mesh:sub_narrower
        "cyp450 metabolism",  # 85  mesh:sub_unresolved
    ],
    "glutamate metabolism": [
        "glutamine metabolism",  # 70  mesh:sub_conflict
        # "glutaminolysis",  # 65  mesh:not_in_dictionary
        "glutamate-glutamine cycle",  # 75  mesh:sub_unresolved
    ],
    "methionine and cysteine metabolism": [
        "cysteine and methionine metabolism",  # 100  gold:1  mesh:sub_unresolved
        "transsulfuration pathway",  # 80  mesh:sub_unresolved
        "trans-sulfuration pathway",  # 80  mesh:sub_unresolved
        "methionine cycle",  # 75  mesh:sub_confirmed
    ],
    "glycine, serine, alanine, and threonine metabolism": [
        "glycine, serine and threonine metabolism",  # 90  gold:1  mesh:sub_unresolved
        # "serine-glycine one-carbon pathway",  # 60  mesh:not_in_dictionary
        # "serine biosynthesis",  # 60  mesh:not_in_dictionary
    ],
    "alanine and aspartate metabolism": [
        "alanine, aspartate and glutamate metabolism",  # 90  gold:1  mesh:sub_unresolved
        # "aspartate-malate shuttle",  # 50  mesh:not_in_dictionary
    ],
    "beta-alanine metabolism": [
        "β-alanine metabolism",  # 100  mesh:sub_broader
    ],
    "d-alanine metabolism": [
        # "d-amino acid metabolism",  # 60  mesh:not_in_dictionary
    ],
    "taurine and hypotaurine metabolism": [
        "taurine biosynthesis",  # 80  mesh:sub_confirmed
    ],
    "glyoxylate and dicarboxylate metabolism": [
        "glyoxylate cycle",  # 75  mesh:sub_confirmed
        # "oxalate metabolism",  # 65  mesh:not_in_dictionary
    ],
    "propanoate metabolism": [
        "propionate metabolism",  # 100  mesh:sub_confirmed
        "propionyl-coa metabolism",  # 80  mesh:sub_unresolved
    ],
    "butanoate metabolism": [
        "butyrate metabolism",  # 100  mesh:sub_broader
        # "short-chain fatty acid metabolism",  # 65  mesh:not_in_dictionary
    ],
    "starch and sucrose metabolism": [
        "glycogen metabolism",  # 75  mesh:sub_conflict
        "glycogenolysis",  # 70  mesh:desc_form_only
        "glycogenesis",  # 70  mesh:ungrounded
    ],
    "inositol phosphate metabolism": [
        "inositol metabolism",  # 85  mesh:sub_broader
        "myo-inositol metabolism",  # 80  mesh:sub_unresolved
    ],
    "ubiquinone synthesis": [
        "coenzyme q10 biosynthesis",  # 90  mesh:sub_unresolved
        "coenzyme q biosynthesis",  # 95  mesh:sub_confirmed
        "ubiquinone biosynthesis",  # 100  mesh:sub_confirmed
        "ubiquinone and other terpenoid-quinone biosynthesis",  # 80  mesh:sub_unresolved
    ],
    "lipoate metabolism": [
        "lipoic acid metabolism",  # 100  mesh:sub_confirmed
        "alpha-lipoic acid metabolism",  # 95  mesh:sub_confirmed
    ],
    "biotin metabolism": [
        "vitamin b7 metabolism",  # 100  mesh:sub_unresolved
    ],
    "thiamine metabolism": [
        "vitamin b1 metabolism",  # 100  mesh:sub_confirmed
        "thiamin metabolism",  # 100  mesh:sub_confirmed
    ],
    "hippurate metabolism": [
        "hippuric acid metabolism",  # 100  mesh:sub_unresolved
    ],
    "peptide metabolism": [
        "peptide degradation",  # 80  mesh:sub_confirmed
    ],
    "nucleotide metabolism": [
        "nucleoside metabolism",  # 80  mesh:sub_conflict
    ],
    "fructose and mannose metabolism": [
        # "fructose metabolism",  # 60  mesh:sub_confirmed
        # "mannose metabolism",  # 60  mesh:sub_confirmed
        # "fructolysis",  # 60  mesh:not_in_dictionary
    ],
    "galactose metabolism": [
        "galactose pathway",  # 90  mesh:sub_confirmed
        "leloir pathway",  # 85  mesh:sub_unresolved
    ],
    "pyruvate metabolism": [
        "pyruvate oxidation",  # 75  mesh:sub_confirmed
        "pyruvate dehydrogenase pathway",  # 70  mesh:sub_unresolved
    ],
    "lysine metabolism": [
        "lysine degradation",  # 80  mesh:sub_confirmed
        "lysine catabolism",  # 80  mesh:sub_confirmed
        "saccharopine pathway",  # 75  mesh:sub_unresolved
    ],
    "limonene and pinene degradation": [
        "monoterpene degradation",  # 80  mesh:sub_broader
    ],
    "c5-branched dibasic acid metabolism": [
        "c5 branched dibasic acid metabolism",  # 100  mesh:sub_unresolved
    ],
    "alkaloid synthesis": [
        "alkaloid biosynthesis",  # 100  mesh:sub_confirmed
    ],
    "arginine and proline metabolism": [
        # "arginine metabolism",  # 60  mesh:sub_confirmed
        # "proline metabolism",  # 60  mesh:sub_confirmed
        "arginine biosynthesis",  # 70  gold:2  mesh:sub_confirmed
        # "polyamine metabolism",  # 60  mesh:not_in_dictionary
    ],
    "histidine metabolism": [
        "histidine catabolism",  # 80  mesh:sub_confirmed
    ],
    "phenylalanine metabolism": [
        "phenylalanine catabolism",  # 80  mesh:sub_confirmed
        "phenylalanine hydroxylation",  # 70  mesh:ungrounded
    ],
    "tyrosine metabolism": [
        "tyrosine catabolism",  # 80  mesh:sub_confirmed
        # "catecholamine biosynthesis",  # 60  mesh:not_in_dictionary
    ],
}

# Acronyms, matched case-sensitively and verbatim. A bare cofactor or metabolite
# acronym is not a pathway mention: scanning the 10k corpus, "NAD+" alone hit 410
# documents and "BCAA" 68, almost all of them concentration statements rather than
# pathway statements. Such acronyms only enter with their process word attached. Lowercasing these is unsafe:
# "etc" is an English abbreviation, "ppp" and "fao" appear as ordinary
# lowercase substrings, and "aa" means amino acid far more often than
# arachidonic acid.
ABBREVIATION_FORMS: dict[str, list[str]] = {
    "citric acid cycle": [
        "TCA cycle",  # 100  gold:1  mesh:sub_unresolved
        "TCA-cycle",  # 100  gold:1  mesh:ungrounded
    ],
    "oxidative phosphorylation": [
        "OXPHOS",  # 100  mesh:ungrounded
        "OxPhos",  # 100  mesh:ungrounded
        # "ETC",  # 60  mesh:not_in_dictionary
    ],
    "pentose phosphate pathway": [
        "PPP",  # 90  mesh:ungrounded
        "HMP shunt",  # 95  mesh:ungrounded
    ],
    "fatty acid oxidation": [
        "FAO",  # 85  mesh:ungrounded
        "FAO pathway",  # 90  mesh:sub_unresolved
    ],
    "fatty acid synthesis": [
        "DNL",  # 85  mesh:ungrounded
    ],
    "valine, leucine, and isoleucine metabolism": [
        "BCAA metabolism",  # 95  mesh:sub_unresolved
        "BCAA catabolism",  # 85  mesh:sub_unresolved
    ],
    "coa synthesis": [
        "CoA biosynthesis",  # 100  gold:1  mesh:sub_confirmed
    ],
    "tetrahydrobiopterin metabolism": [
        "BH4 metabolism",  # 100  mesh:sub_unresolved
        "BH4 biosynthesis",  # 85  mesh:sub_unresolved
    ],
    "glutathione metabolism": [
        "GSH metabolism",  # 100  gold:6  mesh:sub_unresolved
    ],
    "ros detoxification": [
        "ROS detoxification",  # 100  gold:2  mesh:ungrounded
        "ROS scavenging",  # 90  mesh:ungrounded
    ],
    "phosphatidylinositol phosphate metabolism": [
        "PIP2 metabolism",  # 70  mesh:sub_unresolved
        # "PIP3 signaling",  # 50  mesh:not_in_dictionary
    ],
    "cytochrome metabolism": [
        # "CYP450",  # 60  mesh:not_in_dictionary
    ],
    "n-glycan synthesis": [
        "N-glycosylation",  # 85  mesh:ungrounded
    ],
    "o-glycan metabolism": [
        "O-glycosylation",  # 80  mesh:ungrounded
    ],
}

# Canonicals whose leading one-token qualifier may be dropped. Whitelisted rather
# than derived: "d-alanine" and "beta-alanine" are distinct pathways from
# "alanine", so blind prefix stripping would merge three canonicals into one.
PREFIX_STRIPPABLE: set[str] = {
    "n-glycan synthesis",
    "n-glycan metabolism",
    "n-glycan degradation",
    "o-glycan metabolism",
}

# Surface forms two canonicals both have a claim to. Recon splits the amino acids
# across "alanine and aspartate metabolism" and "glycine, serine, alanine, and
# threonine metabolism", so "alanine metabolism" alone is genuinely ambiguous.
# The span is a PATHWAY either way; only the canonical assignment needs a rule,
# and it has to be deterministic or the same phrase gets two labels across runs.
AMBIGUOUS_OWNER: dict[str, str] = {
    "alanine metabolism": "alanine and aspartate metabolism",
}


# Surface forms that must never be emitted no matter which rule generates them:
# they are either a different canonical's name or too generic to carry meaning.
FORM_BLOCKLIST: set[str] = {
    "acid",
    "acid metabolism",
    "amino acid metabolism",
    "carbon metabolism",
    "cycle",
    "demand",
    "drug",
    "energy metabolism",
    "fatty acid metabolism",
    "glycan metabolism",
    "group synthesis",
    "lipid metabolism",
    "metabolic pathway",
    "metabolism",
    "nucleotide metabolism",
    "pathway",
    "protein metabolism",
    "salvage pathway",
    "sugar metabolism",
    "synthesis",
}


# Forms derived from MeSH entry terms by scripts/generate_mesh_forms.py, rather
# than checked against them. Two generators: the entry terms of a descriptor that
# is itself one of our canonicals, and the entry terms of a canonical's substance
# composed with its process word ("Retinol" + metabolism). Only candidates that
# actually occur in the 10,125-document corpus are kept; the occurrence count and
# the vouching descriptor are on each line.
#
# MeSH provenance is not a correctness proof. NLM files stereoisomers under one
# descriptor for indexing purposes, so "D-Glutamate" and "L-Glutamate" are both
# entry terms of Glutamic Acid though they are different compounds — see the
# commented line below.
MESH_ENTRY_FORMS: dict[str, list[str]] = {
    "pentose phosphate pathway": [
        "pentose-phosphate pathway",  # 14x  mesh:Pentose Phosphate Pathway
        "pentose phosphate pathways",  # 8x  mesh:Pentose Phosphate Pathway
        "pentosephosphate pathway",  # 1x  mesh:Pentose Phosphate Pathway
    ],
    "glutamate metabolism": [
        "l-glutamate metabolism",  # 3x  mesh:Glutamic Acid
        # "d-glutamate metabolism" is rejected although MeSH vouches for it: the
        # D-isomer is a distinct, bacterial pathway, and this corpus writes it as
        # "D-glutamine and D-glutamate metabolism" (33 occurrences, a KEGG map of
        # its own). Folding it into glutamate metabolism would merge two pathways.
        # "d-glutamate metabolism",  # 41x  mesh:Glutamic Acid
    ],
    "tryptophan metabolism": [
        "l-tryptophan metabolism",  # 5x  mesh:Tryptophan
    ],
    "phenylalanine metabolism": [
        "l-phenylalanine metabolism",  # 3x  mesh:Phenylalanine
    ],
    "tyrosine metabolism": [
        "l-tyrosine metabolism",  # 1x  mesh:Tyrosine
    ],
    "lysine metabolism": [
        "l-lysine metabolism",  # 1x  mesh:Lysine
    ],
    "arginine and proline metabolism": [
        "l-arginine metabolism",  # 1x  mesh:Arginine
    ],
    "valine, leucine, and isoleucine metabolism": [
        "l-valine metabolism",  # 1x  mesh:Valine
    ],
    "galactose metabolism": [
        "d-galactose metabolism",  # 1x  mesh:Galactose
    ],
    "glutathione metabolism": [
        "reduced glutathione metabolism",  # 1x  mesh:Glutathione
    ],
    "bile acid synthesis": [
        "bile salts synthesis",  # 1x  mesh:Bile Acids and Salts
    ],
    "butanoate metabolism": [
        "butanoic acid metabolism",  # 1x  mesh:Butyric Acid
    ],
}

# ---------------------------------------------------------------------------
# KEGG crossmatch vocabulary
# ---------------------------------------------------------------------------

# KEGG names accepted as surface forms for the Recon canonical. Kept explicit
# instead of reading the CSV blindly, because the CSV's match_score is 1.0 for
# every kegg_id_crossref row regardless of how close the two names are.
KEGG_FORMS: dict[str, list[str]] = {
    "alanine and aspartate metabolism": [
        "alanine, aspartate and glutamate metabolism",  # 90  gold:1  mesh:sub_unresolved
    ],
    "arginine and proline metabolism": [
        "arginine and proline metabolism",  # 100  gold:3  mesh:sub_unresolved
    ],
    "beta-alanine metabolism": [
        "beta-alanine metabolism",  # 100  gold:2  mesh:sub_confirmed
    ],
    "bile acid synthesis": [
        "primary bile acid biosynthesis",  # 90  mesh:sub_unresolved
    ],
    "biotin metabolism": [
        "biotin metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "butanoate metabolism": [
        "butanoate metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "cholesterol metabolism": [
        "cholesterol metabolism",  # 100  gold:2  mesh:sub_confirmed
    ],
    "citric acid cycle": [
        "citrate cycle (tca cycle)",  # 100  mesh:ungrounded
        "citrate cycle",  # 95  mesh:sub_confirmed
    ],
    "coa synthesis": [
        "pantothenate and coa biosynthesis",  # 85  mesh:sub_unresolved
    ],
    "drug metabolism": [
        "metabolism of xenobiotics by cytochrome p450",  # 80  mesh:ungrounded
    ],
    "fatty acid oxidation": [
        "fatty acid degradation",  # 90  mesh:sub_confirmed
        # "fatty acid elongation",  # 50  mesh:not_in_dictionary
    ],
    "fatty acid synthesis": [
        "fatty acid biosynthesis",  # 100  gold:1  mesh:sub_confirmed
        "biosynthesis of unsaturated fatty acids",  # 75  gold:1  mesh:ungrounded
    ],
    "folate metabolism": [
        "one carbon pool by folate",  # 85  mesh:ungrounded
    ],
    "fructose and mannose metabolism": [
        "fructose and mannose metabolism",  # 100  gold:1  mesh:sub_unresolved
    ],
    "galactose metabolism": [
        "galactose metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "glutathione metabolism": [
        "glutathione metabolism",  # 100  gold:2  mesh:sub_confirmed
    ],
    "glycine, serine, alanine, and threonine metabolism": [
        "glycine, serine and threonine metabolism"
    ],
    "glycolysis/gluconeogenesis": [
        "glycolysis / gluconeogenesis",  # 100  gold:2  mesh:ungrounded
    ],
    "heme degradation": [
        "porphyrin metabolism",  # 70  mesh:sub_broader
    ],
    "histidine metabolism": [
        "histidine metabolism",  # 100  gold:2  mesh:sub_confirmed
    ],
    "inositol phosphate metabolism": [
        "inositol phosphate metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "linoleate metabolism": [
        "linoleic acid metabolism",  # 100  gold:2  mesh:sub_confirmed
    ],
    "lysine metabolism": [
        "lysine degradation",  # 80  mesh:sub_confirmed
    ],
    "methionine and cysteine metabolism": [
        "cysteine and methionine metabolism",  # 100  gold:1  mesh:sub_unresolved
    ],
    "nad metabolism": [
        "nicotinate and nicotinamide metabolism",  # 90  mesh:sub_unresolved
    ],
    "nucleotide sugar metabolism": [
        "amino sugar and nucleotide sugar metabolism",  # 85  mesh:sub_unresolved
    ],
    "o-glycan metabolism": [
        "mucin type o-glycan biosynthesis",  # 75  mesh:sub_unresolved
    ],
    "oxidative phosphorylation": [
        "oxidative phosphorylation",  # 100  gold:3  mesh:desc_confirmed
    ],
    "pentose phosphate pathway": [
        "pentose phosphate pathway",  # 100  gold:2  mesh:desc_confirmed
    ],
    "propanoate metabolism": [
        "propanoate metabolism",  # 100  gold:2  mesh:sub_confirmed
    ],
    "purine catabolism": [
        "purine metabolism",  # 70  gold:1  mesh:sub_confirmed
    ],
    "pyrimidine synthesis": [
        "pyrimidine metabolism",  # 70  gold:1  mesh:sub_confirmed
    ],
    "pyruvate metabolism": [
        "pyruvate metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "sphingolipid metabolism": [
        "sphingolipid metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "squalene and cholesterol synthesis": [
        "terpenoid backbone biosynthesis",  # 70  mesh:sub_unresolved
    ],
    "starch and sucrose metabolism": [
        "starch and sucrose metabolism",  # 100  gold:1  mesh:sub_unresolved
    ],
    "steroid metabolism": [
        "steroid hormone biosynthesis",  # 85  gold:2  mesh:sub_unresolved
        "steroid biosynthesis",  # 85  mesh:sub_confirmed
    ],
    "thiamine metabolism": [
        "thiamine metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "tryptophan metabolism": [
        "tryptophan metabolism",  # 100  mesh:sub_confirmed
    ],
    "tyrosine metabolism": [
        "tyrosine metabolism",  # 100  gold:4  mesh:sub_confirmed
    ],
    "ubiquinone synthesis": [
        "ubiquinone and other terpenoid-quinone biosynthesis",  # 80  mesh:sub_unresolved
    ],
    "valine, leucine, and isoleucine metabolism": [
        "valine, leucine and isoleucine biosynthesis",  # 80  gold:1  mesh:sub_unresolved
        "valine, leucine and isoleucine degradation",  # 80  mesh:sub_unresolved
    ],
    "vitamin a metabolism": [
        "retinol metabolism",  # 95  gold:1  mesh:sub_confirmed
    ],
    "vitamin b2 metabolism": [
        "riboflavin metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
    "vitamin b6 metabolism": [
        "vitamin b6 metabolism",  # 100  gold:1  mesh:sub_confirmed
    ],
}

# CSV rows deliberately not used, with the reason. Flip an entry into KEGG_FORMS
# if the reason turns out to be wrong.
KEGG_REJECTED: dict[tuple[str, str], str] = {
    ("citric acid cycle", "carbon metabolism"): "KEGG parent map, not a synonym",
    ("citric acid cycle", "biosynthesis of amino acids"): "unrelated parent map",
    ("citric acid cycle", "2-oxocarboxylic acid metabolism"): "broader superset map",
    ("oxidative phosphorylation", "glycerophospholipid metabolism"): (
        "id crossref artifact; glycerophospholipid metabolism is its own canonical"
    ),
    ("ros detoxification", "glyoxylate and dicarboxylate metabolism"): (
        "id crossref artifact; the KEGG name is another Recon canonical"
    ),
    ("heme synthesis", "biosynthesis of cofactors"): "KEGG parent map",
    ("glutamate metabolism", "arginine biosynthesis"): (
        "belongs to arginine and proline metabolism"
    ),
    ("nucleotide salvage pathway", "nucleotide metabolism"): (
        "the KEGG name is another Recon canonical"
    ),
    ("chondroitin synthesis", "glycosaminoglycan biosynthesis - heparan sulfate / heparin"): (
        "heparan sulfate is a different Recon canonical"
    ),
    ("chondroitin synthesis", "glycosaminoglycan biosynthesis - chondroitin sulfate / dermatan sulfate"): (
        "covered by the curated chondroitin sulfate biosynthesis form"
    ),
    ("cholesterol metabolism", "steroid biosynthesis"): (
        "assigned to steroid metabolism instead"
    ),
    ("pentose phosphate pathway", "pentose and glucuronate interconversions"): (
        "different KEGG map, not a synonym"
    ),
    ("tetrahydrobiopterin metabolism", "folate biosynthesis"): (
        "folate is its own canonical"
    ),
    ("fatty acid oxidation", "fatty acid metabolism"): (
        "too generic; covers synthesis as well"
    ),
    ("chondroitin sulfate degradation", "glycosaminoglycan degradation"): (
        "covers keratan and heparan degradation too"
    ),
    ("eicosanoid metabolism", "arachidonic acid metabolism"): (
        "the KEGG name is another Recon canonical"
    ),
}


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SurfaceForm:
    """One searchable phrase for a canonical pathway."""

    text: str
    origin: str  # canonical | manual | recon_synonym | abbreviation | split | prefix | kegg
    case_sensitive: bool = False

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "origin": self.origin,
            "case_sensitive": self.case_sensitive,
        }


def _strip_process_tail(name: str) -> tuple[str, list[str]]:
    """Peel trailing process words off a canonical.

    Returns (head, processes) with processes in written order.

        "androgen and estrogen synthesis and metabolism"
            -> ("androgen and estrogen", ["synthesis", "metabolism"])
        "glycolysis/gluconeogenesis" -> ("glycolysis/gluconeogenesis", [])
    """
    head = name.lower().strip()
    processes: list[str] = []
    while True:
        m = re.search(rf"\s+({_PROCESS_RE})\s*$", head)
        if m:
            processes.insert(0, m.group(1))
            head = head[: m.start()].strip()
            continue
        stripped = re.sub(r"\s*(?:and|or|,|/)\s*$", "", head)
        if stripped != head:
            head = stripped
            continue
        break
    return head, processes


def _split_heads(head: str) -> list[str]:
    """Split a head phrase on connectors: "glycine, serine, and threonine"."""
    parts = []
    for part in _CONNECTOR_SPLIT.split(head):
        part = re.sub(r"^(?:and|or)\s+", "", part.strip()).strip()
        if part and part not in PROCESS_WORDS:
            parts.append(part)
    return parts


def distribute_forms(canonical: str) -> list[str]:
    """Head x process recombinations of a multi-substrate canonical name."""
    head, processes = _strip_process_tail(canonical)
    heads = _split_heads(head)
    if len(heads) < 2 and not (len(heads) == 1 and len(processes) > 1):
        return []

    forms: list[str] = []
    if not processes:
        # "glycolysis/gluconeogenesis": each component stands on its own.
        forms.extend(h for h in heads if len(h) >= _MIN_HEAD_LEN)
        return forms

    tail = " and ".join(processes)
    for h in heads:
        if len(h) < _MIN_HEAD_LEN:
            continue
        if len(processes) > 1:
            # Step 1: keep the full process tail with a single substrate.
            forms.append(f"{h} {tail}")
        # Step 2: one substrate, one process.
        for p in processes:
            forms.append(f"{h} {p}")
    return forms


def prefix_forms(canonical: str) -> list[str]:
    """Drop a leading one-token qualifier for whitelisted canonicals."""
    if canonical not in PREFIX_STRIPPABLE:
        return []
    m = re.match(r"^[a-z0-9]{1,2}-(?=[a-z])", canonical)
    return [canonical[m.end():]] if m else []


def _greek_variants(text: str) -> list[str]:
    """ASCII/greek spelling pairs: beta-alanine <-> β-alanine."""
    table = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "omega": "ω"}
    out = []
    for word, letter in table.items():
        if word in text:
            out.append(text.replace(word, letter))
        if letter in text:
            out.append(text.replace(letter, word))
    return out


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def load_kegg_rows(path: Path = KEGG_MATCH_FILE) -> list[tuple[str, str, float]]:
    """(recon_name, kegg_name, score) rows above KEGG_MIN_SCORE, deduplicated.

    Returns an empty list when the crossmatch file is absent — it lives in a
    worktree and the dictionary must still build without it.
    """
    if not path.exists():
        return []
    seen: dict[tuple[str, str], float] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                score = float(row["match_score"])
            except (KeyError, TypeError, ValueError):
                continue
            if score < KEGG_MIN_SCORE:
                continue
            key = (_normalize(row["matched_recon3d_pathway"]), _normalize(row["pathway_name"]))
            seen[key] = max(seen.get(key, 0.0), score)
    return [(a, b, s) for (a, b), s in sorted(seen.items())]


def build_surface_forms(include_canonical: bool = True) -> dict[str, list[SurfaceForm]]:
    """The full dictionary: canonical -> ordered, deduplicated surface forms."""
    result: dict[str, list[SurfaceForm]] = {}

    for canonical in load_recon_names():
        forms: list[SurfaceForm] = []

        def add(text: str, origin: str, case_sensitive: bool = False) -> None:
            t = text.strip() if case_sensitive else _normalize(text)
            # Case-sensitive acronyms are allowed to be shorter: "ETC", "PPP" and
            # "FAO" are three characters and are the whole point of that table.
            floor = _MIN_ACRONYM_LEN if case_sensitive else _MIN_HEAD_LEN
            if not t or len(t) < floor:
                return
            if _normalize(t) in FORM_BLOCKLIST:
                return
            forms.append(SurfaceForm(t, origin, case_sensitive))

        if include_canonical:
            add(canonical, "canonical")

        for text in RECON_SYNONYMS.get(canonical, []):
            add(text, "recon_synonym")
        for text in MANUAL_FORMS.get(canonical, []):
            add(text, "manual")
        for text in distribute_forms(canonical):
            add(text, "split")
        for text in prefix_forms(canonical):
            add(text, "prefix")
        for text in KEGG_FORMS.get(canonical, []):
            add(text, "kegg")
        for text in MESH_ENTRY_FORMS.get(canonical, []):
            add(text, "mesh_entry")
        for text in ABBREVIATION_FORMS.get(canonical, []):
            add(text, "abbreviation", case_sensitive=True)

        # Greek/ASCII spellings of everything collected so far.
        for form in list(forms):
            for variant in _greek_variants(form.text):
                add(variant, form.origin, form.case_sensitive)

        # Deduplicate on the matched string, keeping the first (highest-trust) origin.
        deduped: dict[tuple[str, bool], SurfaceForm] = {}
        for f in forms:
            owner = AMBIGUOUS_OWNER.get(f.text.lower())
            if owner is not None and owner != canonical:
                continue
            deduped.setdefault((f.text, f.case_sensitive), f)
        result[canonical] = list(deduped.values())

    return result


def unknown_keys() -> dict[str, list[str]]:
    """Table keys that are not Recon canonicals (typo guard)."""
    known = set(load_recon_names(apply_blocklist=False))
    tables = {
        "MESH_ENTRY_FORMS": MESH_ENTRY_FORMS,
        "MANUAL_FORMS": MANUAL_FORMS,
        "ABBREVIATION_FORMS": ABBREVIATION_FORMS,
        "KEGG_FORMS": KEGG_FORMS,
    }
    out = {name: sorted(k for k in t if k not in known) for name, t in tables.items()}
    out["PREFIX_STRIPPABLE"] = sorted(k for k in PREFIX_STRIPPABLE if k not in known)
    return {k: v for k, v in out.items() if v}


def find_conflicts(
    forms: dict[str, list[SurfaceForm]] | None = None,
) -> dict[str, list[str]]:
    """Surface forms claimed by more than one canonical."""
    forms = forms if forms is not None else build_surface_forms()
    owners: dict[str, list[str]] = {}
    for canonical, items in forms.items():
        for f in items:
            owners.setdefault(f.text.lower(), []).append(canonical)
    return {t: sorted(set(c)) for t, c in owners.items() if len(set(c)) > 1}


def unused_kegg_rows() -> list[tuple[str, str, str]]:
    """CSV rows above the score threshold that are neither accepted nor rejected."""
    accepted = {
        (_normalize(c), _normalize(t)) for c, ts in KEGG_FORMS.items() for t in ts
    }
    rejected = {(_normalize(a), _normalize(b)) for a, b in KEGG_REJECTED}
    out = []
    for recon, kegg, _ in load_kegg_rows():
        key = (recon, kegg)
        if key in accepted or key in rejected:
            continue
        out.append((recon, kegg, "unreviewed"))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--json", action="store_true", help="dump the dictionary as JSON")
    ap.add_argument("--conflicts", action="store_true", help="show ambiguous forms only")
    ap.add_argument("--kegg-unreviewed", action="store_true", help="CSV rows not yet triaged")
    args = ap.parse_args()

    forms = build_surface_forms()

    if args.json:
        print(
            json.dumps(
                {c: [f.as_dict() for f in items] for c, items in forms.items()},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.conflicts:
        conflicts = find_conflicts(forms)
        for text, owners in sorted(conflicts.items()):
            print(f"{text!r} -> {', '.join(owners)}")
        print(f"\n{len(conflicts)} ambiguous surface form(s)")
        return 0

    if args.kegg_unreviewed:
        rows = unused_kegg_rows()
        for recon, kegg, _ in rows:
            print(f"{recon:45s} <- {kegg}")
        print(f"\n{len(rows)} unreviewed row(s)")
        return 0

    total = 0
    for canonical, items in forms.items():
        total += len(items)
        print(f"\n{canonical}  ({len(items)})")
        for f in items:
            flag = " [case-sensitive]" if f.case_sensitive else ""
            print(f"    {f.text}   <{f.origin}>{flag}")
    print(f"\n{len(forms)} canonicals, {total} surface forms")
    conflicts = find_conflicts(forms)
    if conflicts:
        print(f"WARNING: {len(conflicts)} ambiguous form(s); run --conflicts")
    for table, keys in unknown_keys().items():
        print(f"WARNING: {table} has non-canonical key(s): {', '.join(keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
