#!/usr/bin/env python3
"""
booster.py

Deterministic recall booster for pathway surface extraction ("Option B", noted at
the end of llm/prompts/pathway_extraction.py).

The guided LLM reliably catches canonical/verbatim pathway names but misses two
kinds of variation (measured on the golden set, P3-0c/d — both models, 7b and 14b):
  - word-order reversal : "metabolism of androgens" for "androgen ... metabolism"
  - redundancy/dedup    : "arginine biosynthesis" dropped when the model already
                          returned the canonical "arginine and proline metabolism"
                          from the same sentence

This module finds those without a model. For each Recon canonical it strips the
process word(s) off the name to get its content phrases, then scans the text for
two patterns:
    A)  <content> <process>        -> "arginine biosynthesis"
    B)  <process> of <content>     -> "metabolism of androgens"

Requiring an adjacent process word is what keeps precision: a bare metabolite
mention ("decreased ... arginine, and aspartate levels") never matches.

Since 2026-08-26 this module also hosts a second, independent scan:
``boost_surface()`` matches a **dictionary of literature surface forms** built by
``preprocessing/pathway_surface_forms.py`` — canonical names, abbreviations (TCA
cycle, OXPHOS), KEGG names of the same pathway, and the split forms of
multi-substrate canonicals ("aspartate metabolism" for "alanine and aspartate
metabolism"). Whole-phrase matches need no direction guard: the phrase carries its
own process word, and the dictionary already says which canonical it belongs to.
It closes the gap measured in section 6.3 of the progress report, where 627
documents contained their pathway query term verbatim yet carried no span.

The two scans are complementary, not nested. The pattern scan is generative — 103
content phrases x 11 process words x 2 templates, a 2,266-phrase space that exists
only as regexes — so it finds "arginine oxidation" and "catabolism of lysine",
which nobody would enumerate. The dictionary is the opposite: a closed list, the
only way to reach "Warburg effect", "FAO" or "kynurenine pathway", which contain
no Recon content phrase and no process word for the pattern scan to anchor on.

They are deliberately NOT merged here. ``llm/run_silver.py`` passes them to
``merge()`` as two separate sources alongside the LLM, so the precedence order —
and with it every tie-break — is visible at the call site.

It scans the **whole 90-name Recon vocabulary**, not just the article's query
pathways. Measured reason: PMID 11469814 mentions "metabolism of androgens" but was
never retrieved by "androgen and estrogen synthesis and metabolism" — that canonical
is absent from its 21 query pathways, so a query-only scan structurally cannot find
it. Query pathways are an incomplete hint.

Entry points:
    boost(text, vocab=None)   -> pattern spans,    source "booster"
    boost_surface(text)       -> dictionary spans, source "dict"
    merge(*sources)           -> union; longest wins on overlap, earlier source
                                 wins a tie of equal length
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "preprocessing"))

from pathway_surface_forms import build_surface_forms  # noqa: E402
from recon_vocab import load_recon_names  # noqa: E402

# Process words, longest-first so the alternation prefers the longer form.
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

# Dropped when splitting a canonical name into content phrases.
_CONNECTORS = re.compile(r"\s+and\s+|\s*,\s*|\s*/\s*")
_MIN_PHRASE_LEN = 4

# The process word carries direction, and Recon distinguishes it ("purine synthesis"
# vs "purine catabolism", "heme synthesis" vs "heme degradation"). Content phrases
# alone are identical for both, so without this guard "purine biosynthesis" lands on
# whichever canonical happens to come first in the vocabulary — the exact opposite
# meaning half the time. Shared with llm/canonicalize.py.
_ANABOLIC = ("biosynthesis", "synthesis", "formation", "production", "lipogenesis")
_CATABOLIC = ("catabolism", "degradation", "breakdown", "oxidation", "lysis")


def process_class(s: str) -> str:
    """'anabolic' | 'catabolic' | 'neutral' — direction implied by the process word."""
    t = s.lower()
    ana = any(w in t for w in _ANABOLIC)
    cat = any(w in t for w in _CATABOLIC)
    if ana and not cat:
        return "anabolic"
    if cat and not ana:
        return "catabolic"
    return "neutral"  # "metabolism" / "cycle" / both present -> covers either direction


def direction_ok(surface: str, canonical: str) -> bool:
    """False when surface and canonical imply opposite directions."""
    a, b = process_class(surface), process_class(canonical)
    return a == "neutral" or b == "neutral" or a == b


def content_phrases(canonical: str) -> list[str]:
    """Strip trailing process words off a canonical name, split into components.

    "arginine and proline metabolism"                -> ["arginine", "proline"]
    "androgen and estrogen synthesis and metabolism" -> ["androgen", "estrogen"]
    "arachidonic acid metabolism"                    -> ["arachidonic acid"]
    """
    name = canonical.lower().strip()
    # Repeatedly peel trailing "<process>" and dangling connectors off the end.
    changed = True
    while changed:
        changed = False
        stripped = re.sub(rf"\s*(?:{_PROCESS_RE})\s*$", "", name)
        if stripped != name:
            name, changed = stripped, True
        stripped = re.sub(r"\s*(?:and|,|/)\s*$", "", name)
        if stripped != name:
            name, changed = stripped, True

    phrases = []
    for part in _CONNECTORS.split(name):
        # Splitting "glycine, serine, and threonine" on "," leaves "and threonine".
        part = re.sub(r"^(?:and|or)\s+", "", part.strip()).strip()
        if len(part) >= _MIN_PHRASE_LEN and part not in PROCESS_WORDS:
            phrases.append(part)
    return phrases


_VOCAB_CACHE: list[str] | None = None


def _default_vocab() -> list[str]:
    global _VOCAB_CACHE
    if _VOCAB_CACHE is None:
        _VOCAB_CACHE = load_recon_names()  # 90 names, blocklist applied
    return _VOCAB_CACHE


_SURFACE_CACHE: list[tuple[re.Pattern, str, str]] | None = None


def _surface_patterns() -> list[tuple[re.Pattern, str, str]]:
    """(compiled pattern, canonical, origin), longest phrase first.

    Longest-first ordering makes the "first claim wins" rule in boost() prefer
    "androgen synthesis and metabolism" over the shorter "androgen synthesis"
    that starts at the same offset.
    """
    global _SURFACE_CACHE
    if _SURFACE_CACHE is None:
        entries = []
        for canonical, forms in build_surface_forms().items():
            for f in forms:
                flags = 0 if f.case_sensitive else re.IGNORECASE
                # Trailing (?![\w-]) also blocks "glycolysis-derived" style hits.
                pat = re.compile(rf"(?<![\w-]){re.escape(f.text)}(?![\w-])", flags)
                entries.append((len(f.text), pat, canonical, f.origin))
        entries.sort(key=lambda e: -e[0])
        _SURFACE_CACHE = [(p, c, o) for _, p, c, o in entries]
    return _SURFACE_CACHE


def boost_surface(text: str) -> list[dict]:
    """Dictionary scan: whole-phrase hits from pathway_surface_forms.py."""
    found: dict[tuple[int, int], dict] = {}
    for pat, canonical, origin in _surface_patterns():
        for m in pat.finditer(text):
            key = (m.start(), m.end())
            if key not in found:
                found[key] = {
                    "surface": text[m.start():m.end()],
                    "start": m.start(),
                    "end": m.end(),
                    "canonical": canonical,
                    "source": "dict",
                    "rule": f"surface:{origin}",
                }
    return sorted(found.values(), key=lambda d: d["start"])


def boost(text: str, vocab: list[str] | None = None) -> list[dict]:
    """Pattern scan: <content> <process> and <process> of <content> spans.

    This is the generative half of the deterministic layer. It never enumerates
    phrases: 103 content phrases x 11 process words x 2 templates is a 2,266-phrase
    space that only exists as regexes, which is how it catches "arginine oxidation"
    and "catabolism of lysine" without anyone writing them down.

    The enumerated half is boost_surface(). The two are merged by the caller —
    llm/run_silver.py runs them as separate sources so that the merge order, and
    with it the tie-breaking, is visible at the call site rather than buried here.

    vocab defaults to the full 90-name Recon vocabulary (see module docstring for
    why this is not restricted to the article's query pathways).
    """
    found: dict[tuple[int, int], dict] = {}
    for canonical in vocab if vocab is not None else _default_vocab():
        for phrase in content_phrases(canonical):
            p = re.escape(phrase)
            patterns = [
                # A: "arginine biosynthesis" / "glycine metabolism"
                rf"\b{p}(?:s|es)?\s+(?:{_PROCESS_RE})\b",
                # B: "metabolism of androgens"
                rf"\b(?:{_PROCESS_RE})\s+of\s+{p}(?:s|es)?\b",
            ]
            for pat in patterns:
                for m in re.finditer(pat, text, flags=re.IGNORECASE):
                    key = (m.start(), m.end())
                    # Never let an anabolic surface claim a catabolic canonical (or
                    # vice versa): "purine biosynthesis" is not "purine catabolism".
                    if not direction_ok(m.group(0), canonical):
                        continue
                    # First canonical to claim a span wins; keeps output stable.
                    if key not in found:
                        found[key] = {
                            "surface": text[m.start():m.end()],
                            "start": m.start(),
                            "end": m.end(),
                            "canonical": canonical,
                            "source": "booster",
                            "rule": "pattern",
                        }
    return sorted(found.values(), key=lambda d: d["start"])


def merge(*sources: list[dict]) -> list[dict]:
    """Union of the given span sets; on overlap the longer span wins.

    Sources are listed in precedence order: when two spans have the *same* length
    and overlap, the one from the earlier source is kept. Callers therefore encode
    their trust ordering in the argument order. run_silver.py passes the dictionary
    first, because it is the only source that knows which canonical a phrase belongs
    to — measured over the 10,125 cached qwen2.5:14b records, the dictionary and the
    LLM produce byte-identical spans 13,414 times, and in 1,013 of those the LLM
    span canonicalizes to None while the dictionary carries the right canonical.

    The two-argument form merge(llm_spans, booster_spans) still works and keeps its
    old meaning.
    """
    spans = sorted(
        [s for src in sources for s in src],
        key=lambda d: (d["start"] - d["end"], d["start"]),  # longest first
    )
    kept: list[dict] = []
    for s in spans:
        if any(s["start"] < k["end"] and k["start"] < s["end"] for k in kept):
            continue
        kept.append(s)
    return sorted(kept, key=lambda d: d["start"])
