#!/usr/bin/env python3
"""
canonicalize.py

Maps an LLM-proposed surface string to one of the 90 usable Recon canonical names
and derives its match_type — the same vocabulary and match_type scheme the golden
set uses (playground/golden_set/README.md).

Only **LLM** spans need this: booster spans (llm/booster.py) already carry the
canonical they were derived from.

Layers, cheapest first:
  1. exact     — normalized surface == a canonical name
  2. synonym   — surface is a known literature form (RECON_SYNONYMS)
  3. variation — content-phrase overlap after stripping process words
                 ("arginine biosynthesis" -> "arginine and proline metabolism")
  4. unmapped  — no confident mapping; left for the human reviewer in doccano

Deliberately **no embeddings**: the NER model we train is binary B/I/O (labels
0/1/2), so a canonical is not part of any training label — an `unmapped` span is
still a valid positive example. The canonical only drives scope filtering and
analysis. Measure the unmapped rate on the pilot before adding a semantic layer.

Known unmappable-by-string cases (expected `unmapped`):
  - chemical synonyms/hyponyms : "cholecalciferol metabolism" -> vitamin d metabolism
  - abbreviations              : "BCAA metabolism" -> valine, leucine, and isoleucine …
  - umbrella terms             : "amino acid metabolism" -> no single subsystem

Entry point:
    canonicalize(surface) -> (canonical | None, match_type)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "preprocessing"))

from recon_vocab import RECON_SYNONYMS, load_recon_names  # noqa: E402

from booster import PROCESS_WORDS, content_phrases  # noqa: E402

_PROCESS_RE = "|".join(re.escape(p) for p in PROCESS_WORDS)
_LEADING_PROCESS_OF = re.compile(rf"^(?:{_PROCESS_RE})\s+of\s+", re.IGNORECASE)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _singular(token: str) -> str:
    for suf in ("es", "s"):
        if len(token) > 4 and token.endswith(suf):
            return token[: -len(suf)]
    return token


def _phrase_key(phrase: str) -> str:
    return " ".join(_singular(t) for t in phrase.split())


def surface_phrases(surface: str) -> set[str]:
    """Content phrases of a surface, handling the '<process> of X' word order."""
    s = _LEADING_PROCESS_OF.sub("", _norm(surface))
    return {_phrase_key(p) for p in content_phrases(s)}


def _build_tables() -> tuple[dict[str, str], dict[str, str], list[tuple[str, set[str]]]]:
    names = load_recon_names()  # 90, blocklist applied
    exact = {_norm(n): n for n in names}
    synonym = {}
    for canonical, forms in RECON_SYNONYMS.items():
        if canonical not in names:
            continue
        for f in forms:
            synonym[_norm(f)] = canonical
    phrases = [(n, {_phrase_key(p) for p in content_phrases(n)}) for n in names]
    return exact, synonym, phrases


_EXACT, _SYNONYM, _PHRASES = _build_tables()


def match_type_for(surface: str, canonical: str) -> str:
    """match_type for a span whose canonical is already known (booster spans)."""
    key = _norm(surface)
    if key == _norm(canonical):
        return "exact"
    if _SYNONYM.get(key) == canonical:
        return "synonym"
    return "variation"


def canonicalize(surface: str) -> tuple[str | None, str]:
    """Map a surface to (canonical, match_type). Returns (None, 'unmapped') if unsure."""
    key = _norm(surface)

    if key in _EXACT:
        return _EXACT[key], "exact"
    if key in _SYNONYM:
        return _SYNONYM[key], "synonym"

    sp = surface_phrases(surface)
    if not sp:
        return None, "unmapped"

    # Best content-phrase overlap wins; require every surface phrase to be covered
    # so "arginine biosynthesis" maps but a broad umbrella term does not.
    best, best_score = None, 0.0
    for canonical, cp in _PHRASES:
        if not cp:
            continue
        shared = sp & cp
        if not shared or shared != sp:
            continue
        # Prefer the canonical that the surface covers most tightly.
        score = len(shared) / len(cp)
        if score > best_score:
            best, best_score = canonical, score

    if best is not None:
        return best, "variation"
    return None, "unmapped"
