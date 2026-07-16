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

It scans the **whole 90-name Recon vocabulary**, not just the article's query
pathways. Measured reason: PMID 11469814 mentions "metabolism of androgens" but was
never retrieved by "androgen and estrogen synthesis and metabolism" — that canonical
is absent from its 21 query pathways, so a query-only scan structurally cannot find
it. Query pathways are an incomplete hint.

Entry point:
    boost(text, vocab=None) -> [{"surface","start","end","canonical","source"}]
    merge(llm_spans, booster_spans) -> merged spans (longest wins on overlap)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "preprocessing"))

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


def boost(text: str, vocab: list[str] | None = None) -> list[dict]:
    """Find <content> <process> and <process> of <content> spans in text.

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
                        }
    return sorted(found.values(), key=lambda d: d["start"])


def merge(llm_spans: list[dict], booster_spans: list[dict]) -> list[dict]:
    """Union of both span sets; on overlap the longer span wins.

    LLM spans are kept as-is (they carry no canonical); booster spans fill gaps and
    replace shorter overlapping LLM spans (e.g. booster's "metabolism of androgens"
    beats a bare LLM "metabolism").
    """
    spans = sorted(
        llm_spans + booster_spans,
        key=lambda d: (d["start"] - d["end"], d["start"]),  # longest first
    )
    kept: list[dict] = []
    for s in spans:
        if any(s["start"] < k["end"] and k["start"] < s["end"] for k in kept):
            continue
        kept.append(s)
    return sorted(kept, key=lambda d: d["start"])
