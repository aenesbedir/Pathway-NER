#!/usr/bin/env python3
"""
synth_prompts.py

Generation prompts for the KG-seeded synthetic probe. Separate from `prompts.py`
on purpose: that module's text is hashed into the teacher cache fingerprint, and
adding a generation prompt to it would invalidate every cached annotation for a
change that has nothing to do with annotating.

The generator is asked for one abstract-like paragraph expressing a *named*
relation between a *named* pair. Naming the target class is what makes the method
worth probing at all: the silver corpus is dominated by `association` and `none`,
and a generator that can be steered to `no_association_stated` produces the
examples that sampling from real abstracts does not.

The target class is a request, not a label. What the paragraph actually says is
decided afterwards by `run_teacher.py` reading it blind.
"""

from __future__ import annotations

SYSTEM = (
    "You write biomedical text. You reply with one JSON object and nothing else: "
    "no prose before or after it, no code fence."
)

#: What each class must be made true by the generated paragraph. The wording is
#: kept close to the annotation guide in `prompts.py` so the generator and the
#: re-labelling teacher are working from the same definitions.
TARGETS = {
    "upregulation": (
        "The abstract must state that the disease is accompanied by, or causes, an "
        "INCREASE in the pathway - higher flux, accumulation, activation, or "
        "upregulation. The direction must be explicit."
    ),
    "downregulation": (
        "The abstract must state that the disease is accompanied by, or causes, a "
        "DECREASE in the pathway - reduced flux, depletion, impairment, deficiency, "
        "or downregulation. The direction must be explicit."
    ),
    "association": (
        "The abstract must link the disease and the pathway without giving a "
        "direction: 'perturbed', 'dysregulated', 'altered', 'implicated in', or a "
        "claim that targeting the pathway treats the disease. It must NOT say "
        "whether the pathway goes up or down."
    ),
    "no_association_stated": (
        "The abstract must explicitly deny a link: the study looked for a relation "
        "between the disease and the pathway and found none, or reports the pathway "
        "unchanged in the disease. The denial must be stated, not merely absent."
    ),
    "none": (
        "The abstract must mention both the disease and the pathway but make NO "
        "claim connecting them to each other. Each appears in a different context - "
        "for example the pathway in a methods or background sentence about another "
        "condition entirely."
    ),
}

GUIDE = """Write one abstract-like paragraph of biomedical text, 4 to 7 sentences, in the register of a PubMed abstract.

Disease: {disease}
Pathway: {pathway}
Relation to express: {label}

{target}

Constraints:
- The exact string "{disease_surface}" must appear in the paragraph at least once, character for character.
- The exact string "{pathway_surface}" must appear in the paragraph at least once, character for character.
- Do not name any other disease or metabolic pathway.
- Invent plausible but unattributed findings. Do not cite authors, journals, PMIDs, accession numbers, or specific cohorts by name.
- Do not state the relation label itself anywhere in the text.

Reply with one JSON object:

{{"abstract": "<the paragraph>", "evidence": "<the single sentence from the paragraph that carries the relation, copied verbatim; empty string if the relation is none>"}}"""


def render(disease: str, pathway: str, label: str, disease_surface: str, pathway_surface: str) -> str:
    return GUIDE.format(
        disease=disease,
        pathway=pathway,
        label=label,
        target=TARGETS[label],
        disease_surface=disease_surface,
        pathway_surface=pathway_surface,
    )
