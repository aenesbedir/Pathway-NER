#!/usr/bin/env python3
"""
abbreviations.py

Find in-document abbreviation definitions so that two entity surfaces naming the
same thing become one entity.

Why this and not an ontology
----------------------------
PMID 36531023 writes "acute lymphoblastic leukemia (ALL)" and then uses the short
form five more times. Surface normalisation keeps those apart, so the pipeline
asks about the same disease twice and can record two different answers - which it
did. MeSH does not repair this: PubTator3 tags the long form but none of the bare
"ALL" mentions, and gives "ALLs" a wrong identifier, so the short mentions would
simply disappear rather than merge.

The information needed is in the text, not in a vocabulary: the article defines
its own abbreviation. Schwartz and Hearst (2003) is the standard reader for that
pattern and scispacy ships it as `AbbreviationDetector`. This module requires it.

An earlier version fell back to a parenthesis pattern when scispacy could not be
imported. The fallback was silent and far weaker: it cannot read "oxidative
phosphorylation (OXPHOS)", whose short form is not the initials of the long one.
Rebuilding the silver_2k_full candidates in an environment without scispacy gave
473 of 3,102 same-sentence pairs different ids, with nothing in the output to
say why. A missing detector is now an import error, and `detector_version()`
names the detector for the manifest.

What it deliberately does not do
--------------------------------
Only definitions written in the document count. "leukemia" is not merged into
"acute lymphoblastic leukemia" even though one contains the other: they are
different concepts with a hypernym relation, and merging them would lose that.
Nor is any cross-document synonym list applied. Every merge here is backed by a
parenthetical definition the authors wrote themselves, which makes it auditable:
the pair, its offsets and the detector that found it are all reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

@dataclass(frozen=True)
class Definition:
    """One abbreviation definition found in one document."""

    short: str
    long: str
    start: int  # offset of the short form
    end: int
    detector: str

    @property
    def short_key(self) -> str:
        return _norm(self.short)

    @property
    def long_key(self) -> str:
        return _norm(self.long)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def detector_version() -> str:
    """Name and version of the detector, for the manifest. Raises if missing."""
    from importlib.metadata import version

    import scispacy.abbreviation  # noqa: F401 - fail here, not mid-corpus

    return f"scispacy {version('scispacy')}"


def find_definitions(text: str) -> list[Definition]:
    """Return every abbreviation defined in `text`."""
    import spacy
    from scispacy.abbreviation import AbbreviationDetector  # noqa: F401

    global _NLP
    try:
        nlp = _NLP
    except NameError:
        nlp = spacy.blank("en")
        nlp.add_pipe("abbreviation_detector")
        _NLP = nlp

    doc = nlp(text)
    out = []
    for abrv in doc._.abbreviations:
        long = str(abrv._.long_form)
        short = str(abrv)
        if _norm(short) == _norm(long):
            continue
        out.append(
            Definition(short, long, abrv.start_char, abrv.end_char, "scispacy")
        )
    # One definition per short form; the first is the defining occurrence.
    seen, uniq = set(), []
    for d in sorted(out, key=lambda d: d.start):
        if d.short_key in seen:
            continue
        seen.add(d.short_key)
        uniq.append(d)
    return uniq


def merge_map(text: str, keys: set[str]) -> dict[str, str]:
    """Map each normalized surface in `keys` to the key it should merge into.

    A surface merges only when the abstract itself defines it: the long form and
    the short form must both occur as entities, and the pair must come from a
    parenthetical definition the authors wrote. Nothing is inferred beyond that.

    An earlier version also folded a trailing plural "s" into the defined short
    form, to catch "ALLs" alongside "ALL". Measured on the 2k corpus that rule
    produced 2 correct merges and 1 wrong one: PMID 38569232 defines both "AF"
    (atrial fibrillation) and "AFS" (AF related stroke) and contrasts the two
    patient groups, so reading AFS as a plural of AF collapses two distinct
    conditions. A rule with that ratio is not worth its risk, and guessing at
    morphology is the kind of judgement this module exists to avoid. Plural forms
    therefore stay separate entities unless the abstract defines them.

    The long form wins as the canonical key. It is the unambiguous one, it reads
    correctly in a report, and it is what a later MeSH lookup would match on.
    """
    mapping: dict[str, str] = {}
    for d in find_definitions(text):
        long_key, short_key = d.long_key, d.short_key
        if long_key not in keys or short_key not in keys:
            continue
        mapping[short_key] = long_key
    return mapping
