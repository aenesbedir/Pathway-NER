#!/usr/bin/env python3
"""
prompts.py

The teacher prompt for pathway-disease relation labelling, v4.

Design notes
------------
The entities are given, not searched for. The model receives the abstract with
every target mention already marked and a numbered list of pairs, and decides one
label per pair. This is relation classification with gold entities, the setting in
which frontier models are reported at roughly 0.7-0.85 F1, rather than end-to-end
document-level extraction, where the same models collapse.

Every worked example below is a real sentence from the gt_100 abstracts, chosen
because it was a case the two-label Opus run got wrong or had to force. The
intervention and `no_association_stated` examples in particular exist to stop the
model reaching for a signed class when the abstract does not state a sign.

The intervention examples sit inside `association` rather than in a class of
their own. v3 gave them a `therapeutic_target` label; v4 removes it, so the rule
that an intervention's direction is not the pathway's direction has to be carried
by the `association` entry instead. Without it the model reads "inhibiting X
treats Y" as `downregulation`, which was the single most common forced label in
the two-class run.

The model must quote its evidence verbatim. `run_teacher.py` checks the quote against
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
    Use `association` ALSO when the only claim is that intervening on the pathway
    treats, prevents or sensitizes the disease. The direction of an intervention
    is not the direction of the pathway in the disease, so such a claim must not
    be labelled up or down.
    - "Inhibiting GTP synthesis radiosensitizes GBM cells and patient-derived
      neurospheres by impairing DNA repair." -> association
    - "Pharmacological and genetic inhibition of serotonin synthesis reduced
      HFD-induced hepatic lipid accumulation." -> association
    If the abstract states BOTH the pathway's state in the disease and an
    intervention, label the state and quote the state sentence.

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

[{"i": 1, "label": "...", "confidence": "...", "evidence": "..."}]

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


# ---------------------------------------------------------------------------
# Single-pair mode
# ---------------------------------------------------------------------------
#
# The mode above asks about every pair of one abstract in one request. That is
# cheaper, and it lets the model resolve pairs against each other - in PMID
# 23377617 it recognised "Zn deficiency" and "ZD" as one disease and rejected
# "neuroblastoma" as a cell line, decisions that are hard to make from a single
# pair in isolation.
#
# It also means the pairs are not judged independently. A label may depend on
# which other pairs happened to share the request, which is a property of the
# candidate file rather than of the abstract. This mode removes that coupling:
# one request carries one pair, and the model sees nothing else.
#
# The entity is no longer named as a quoted surface string for the model to
# locate; every mention of it is marked in the abstract itself. Two things follow.
# The model cannot pick the wrong occurrence of a repeated surface, and a pathway
# nested inside a disease span stays visible as nested rather than being flattened
# into two unrelated quotes.

MARKERS = {
    "PATHWAY": ("[[PATHWAY]]", "[[/PATHWAY]]"),
    "DISEASE": ("[[DISEASE]]", "[[/DISEASE]]"),
}


def mark_abstract(abstract: str, mentions: list) -> str:
    """Insert markers around every given mention, leaving the rest untouched.

    `mentions` carry character offsets into `abstract`. Insertions run from the
    last offset backwards so that earlier offsets stay valid, and nesting is
    preserved: this corpus contains pathway spans that sit inside a disease span
    ("inborn error of glycosphingolipid metabolism"), and flattening those would
    misrepresent what the annotators marked.
    """
    edits = []
    for m in mentions:
        open_tag, close_tag = MARKERS[m.label]
        # Tie-breakers matter only when two spans share an offset, which nesting
        # guarantees. Insertions run right-to-left and each one at a given offset
        # pushes the previous ones rightwards, so whatever is inserted *last* ends
        # up leftmost. For two spans ending together the inner one must close
        # first, so it is sorted last: inner means the later start. For two spans
        # starting together the outer one must open first, so the wider span -
        # the later end - is sorted last.
        edits.append((m.start, 0, m.end, open_tag))
        edits.append((m.end, 1, m.start, close_tag))
    out = abstract
    for pos, _kind, _tie, tag in sorted(edits, key=lambda e: (-e[0], e[1], e[2])):
        out = out[:pos] + tag + out[pos:]
    return out


GUIDE_SINGLE = GUIDE.replace(
    """For each numbered (PATHWAY, DISEASE) pair, decide what THIS ABSTRACT claims about
the relation between them. Both entities are already identified for you; do not
re-annotate entities, and do not consider any other pair.""",
    """Decide what THIS ABSTRACT claims about the relation between ONE pathway and ONE
disease. Both are already identified for you: every mention of the pathway is
wrapped in [[PATHWAY]] ... [[/PATHWAY]] and every mention of the disease in
[[DISEASE]] ... [[/DISEASE]]. The markers are not part of the text. A pathway
marker may appear inside a disease marker; that is a real nesting in the source
annotation, not an error.

Judge only this one pair. Other pathways and diseases in the abstract are left
unmarked and are not your concern.""",
).replace(
    """# Output

Return ONLY a JSON array, one object per pair, in the given order:

[{"i": 1, "label": "...", "confidence": "...", "evidence": "..."}]

No prose before or after. No markdown fences.""",
    """# Output

Return ONLY a JSON object:

{"label": "...", "confidence": "...", "evidence": "..."}

No prose before or after. No markdown fences.""",
)


def render_single(abstract: str, pathway_mentions: list, disease_mentions: list,
                  pathway_text: str, disease_text: str) -> str:
    """Build the user message for exactly one (pathway, disease) pair."""
    marked = mark_abstract(abstract, [*pathway_mentions, *disease_mentions])
    return "\n".join([
        GUIDE_SINGLE,
        "",
        "# Abstract",
        "",
        marked,
        "",
        "# Pair to label",
        "",
        f'PATHWAY = "{pathway_text}"   (marked [[PATHWAY]] ... [[/PATHWAY]])',
        f'DISEASE = "{disease_text}"   (marked [[DISEASE]] ... [[/DISEASE]])',
        "",
        "Return a single JSON object.",
    ])
