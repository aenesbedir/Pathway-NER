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
pattern and scispacy ships it as `AbbreviationDetector`. This module prefers it
and falls back to a parenthesis pattern when scispacy is unavailable, so the
pipeline still runs without the optional dependency.

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

#: "long form (SHORT)" with the short form in parentheses immediately after.
#: Kept deliberately tight - a loose pattern here merges unrelated entities.
_PAREN = re.compile(
    r"(?P<long>[A-Za-z][\w\-'/,\s]{2,80}?)\s*\(\s*(?P<short>[A-Za-z][A-Za-z0-9\-'/]{0,9})\s*\)"
)

_STOP = {"of", "the", "and", "in", "a", "an", "with", "to", "for", "or", "by", "on"}


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


def _is_plausible(short: str, long: str) -> bool:
    """Accept only a short form whose letters can be read out of the long form.

    Schwartz-Hearst proper matches characters right to left; this is the cheap
    version used by the fallback. It rejects "(see Methods)" and similar noise,
    and it accepts the plural of a defined form ("ALLs" for "ALL") because the
    caller strips a trailing s before asking.
    """
    letters = [c for c in short.lower() if c.isalnum()]
    if not letters or len(letters) > 10:
        return False
    words = [w for w in re.split(r"[\s\-/]+", long.lower()) if w and w not in _STOP]
    if len(words) < len(letters):
        return False
    initials = "".join(w[0] for w in words)
    if initials == "".join(letters):
        return True
    # Fall back to subsequence: the short form's letters appear in order in the
    # long form. Covers "HHcy" for "hyperhomocysteinemia".
    it = iter(long.lower())
    return all(any(c == ch for ch in it) for c in letters)


def find_definitions(text: str) -> list[Definition]:
    """Return every abbreviation defined in `text`, best detector first."""
    try:
        return _scispacy(text)
    except Exception:  # noqa: BLE001 - optional dependency or model issue
        return _fallback(text)


def _scispacy(text: str) -> list[Definition]:
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


def _fallback(text: str) -> list[Definition]:
    out, seen = [], set()
    for m in _PAREN.finditer(text):
        short, long = m.group("short").strip(), m.group("long").strip()
        if not _is_plausible(short, long):
            continue
        if _norm(short) in seen:
            continue
        seen.add(_norm(short))
        out.append(
            Definition(short, long, m.start("short"), m.end("short"), "regex")
        )
    return out


def merge_map(text: str, keys: set[str]) -> dict[str, str]:
    """Map each normalized surface in `keys` to the key it should merge into.

    Only surfaces that actually occur as entities are merged, and only when both
    sides of a definition are present: finding "acute lymphoblastic leukemia
    (ALL)" is useless unless the pipeline also produced both as entities. A
    trailing plural "s" on the short form is tolerated, so "ALLs" joins "ALL".

    The long form wins as the canonical key. It is the unambiguous one, it reads
    correctly in a report, and it is what a later MeSH lookup would match on.
    """
    mapping: dict[str, str] = {}
    for d in find_definitions(text):
        long_key, short_key = d.long_key, d.short_key
        if long_key not in keys:
            continue
        for candidate in keys:
            base = candidate[:-1] if candidate.endswith("s") else candidate
            if candidate == short_key or base == short_key:
                if candidate != long_key:
                    mapping[candidate] = long_key
    return mapping
