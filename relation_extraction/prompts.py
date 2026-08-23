#!/usr/bin/env python3
"""
prompts.py

The teacher prompt for pathway-disease relation labelling, v3.

Design notes
------------
The entities are given, not searched for. The model receives the abstract with
every target mention already marked and a numbered list of pairs, and decides one
label per pair. This is relation classification with gold entities, the setting in
which frontier models are reported at roughly 0.7-0.85 F1, rather than end-to-end
document-level extraction, where the same models collapse.

Every worked example below is a real sentence from the gt_100 abstracts, chosen
because it was a case the two-label Opus run got wrong or had to force. The
`therapeutic_target`, `no_association_stated` and hedged-`association` examples in
particular exist to stop the model reaching for a signed class when the abstract
does not state a sign.

The model must quote its evidence verbatim. `ground.py` checks the quote against
the abstract and drops the row if it does not match, the same grounding rule the
pathway NER silver pipeline applies to spans.
"""

from __future__ import annotations

SYSTEM = (
    "You are annotating biomedical abstracts for a metabolic pathway-disease "
    "relation database. You follow the annotation guide exactly and never infer a "
    "claim from background knowledge that the abstract itself does not state."
)

GUIDE = """\
# Task

For each numbered (PATHWAY, DISEASE) pair, decide what THIS ABSTRACT claims about
the relation between them. Both entities are already identified for you; do not
re-annotate entities, and do not consider any other pair.

# Labels — exactly one per pair

`upregulation`
    The abstract states the pathway's activity, expression or flux is INCREASED,
    activated, enriched or overexpressed in the disease.
    - "Oncogenic KRAS induces metabolic rewiring in pancreatic ductal
      adenocarcinoma characterized by dependency on de novo pyrimidine
      biosynthesis." -> upregulation
    - "MTHFD2 was overexpressed in glioma tissues" -> upregulation

`downregulation`
    The abstract states it is DECREASED, impaired, suppressed, deficient or
    defective in the disease. Inborn errors of metabolism belong here: a disease
    defined as a defect of a pathway states that pathway is down.
    - "Gaucher disease is an autosomal recessive inborn error of
      glycosphingolipid metabolism caused by the deficient activity of ..."
      -> downregulation
    - "fatty acid oxidation is reduced in SOD1 ALS fibroblasts" -> downregulation

`association`
    The abstract claims the pathway is CHANGED or INVOLVED in the disease but
    states NO direction. This is the most common label. Typical wording: altered,
    dysregulated, perturbed, disturbed, enriched for, associated with, implicated
    in, plays a role in, differed between groups, reprogrammed.
    - "The TCA cycle was significantly affected in both young and middle-aged MDD
      patients" -> association
    - "Alterations in multiple metabolic pathways, including purine, arginine and
      proline metabolism, were also associated with CAC in women with SLE."
      -> association
    Use `association` when a pathway is named in a list of enriched pathways from
    a metabolomics or GSEA analysis and no direction is given for it.

`therapeutic_target`
    The abstract's claim is about INTERVENING on the pathway to treat, prevent or
    sensitize the disease, and it does NOT separately state the pathway's state in
    the disease. The direction of the intervention is not the direction of the
    pathway in the disease, so these must not be labelled up or down.
    - "Inhibiting GTP synthesis radiosensitizes GBM cells and patient-derived
      neurospheres by impairing DNA repair." -> therapeutic_target
    - "Pharmacological and genetic inhibition of serotonin synthesis reduced
      HFD-induced hepatic lipid accumulation." -> therapeutic_target
    If the abstract states BOTH a state in the disease and an intervention, label
    the state (`upregulation` / `downregulation`) and quote the state sentence.

`no_association_stated`
    The abstract reports that it LOOKED and found NO relation. An explicit claim
    of absence is evidence, and it is not the same as silence.
    - "Higher CAP values are associated with low serum 25(OH)D concentrations but
      not with common vitamin D pathway gene variants." -> no_association_stated
    - "Markers of skeletal muscle mitochondrial oxidative phosphorylation were
      also unaltered." -> no_association_stated

`none`
    The abstract makes no claim connecting this pathway to this disease. The two
    are merely co-mentioned, or the pathway is discussed in a context (a cell
    line, a different organism, a drug's metabolism, a definition sentence) that
    is not a claim about this disease. Expect this to be common, especially for
    pairs whose entities never share a sentence.
    - An abstract about diatom metabolism that opens "BMAA is an environmental
      factor connected to neurodegenerative diseases" makes no claim about the
      diatom's urea cycle in neurodegenerative disease -> none

# Reference point for `upregulation` / `downregulation`

The sign is relative to the comparison the abstract itself makes — disease versus
healthy where available, otherwise the comparison stated (resistant versus
sensitive cells, one subtype versus another, patients with a feature versus
without). If the abstract makes no comparison at all, the label is `association`
or `none`, not a guessed sign.

# `certainty`

`asserted`   the abstract states the claim as a finding.
`hedged`     the claim is softened: may, might, could, suggests, potential,
             possible, warrants further study, has not been reported to date.
Hedging is not negation. A hedged claim keeps its label and sets `certainty` to
`hedged`.

# `evidence`

One sentence, copied CHARACTER FOR CHARACTER from the abstract, that carries the
claim. Do not paraphrase, do not join two sentences, do not fix typography. A
quote that is not found in the abstract verbatim causes the row to be discarded.
`none` takes an empty evidence string.

# `confidence`

`high`    the sentence states the claim plainly.
`medium`  the claim is present but requires reading across the sentence.
`low`     you are unsure between two labels.

# Output

Return ONLY a JSON array, one object per pair, in the given order:

[{"i": 1, "label": "...", "certainty": "...", "confidence": "...", "evidence": "..."}]

No prose before or after. No markdown fences.
"""


def render(abstract: str, pairs: list[tuple[str, str]]) -> str:
    """Build the user message for one abstract and its candidate pairs.

    `pairs` is a list of (pathway surface, disease surface) in the order the
    caller wants labelled; the returned indices are 1-based over that order.
    """
    lines = [
        GUIDE,
        "",
        "# Abstract",
        "",
        abstract,
        "",
        "# Pairs to label",
        "",
    ]
    for i, (pathway, disease) in enumerate(pairs, 1):
        lines.append(f'{i}. PATHWAY="{pathway}"  DISEASE="{disease}"')
    lines += [
        "",
        f"Return a JSON array of exactly {len(pairs)} objects.",
    ]
    return "\n".join(lines)
