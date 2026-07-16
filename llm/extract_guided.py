#!/usr/bin/env python3
"""
extract_guided.py

Guided, whole-abstract pathway surface extraction via a local LLM (Ollama).
One LLM call per abstract, hinting the article's query pathway(s) and optionally
the 98 Recon vocabulary. Returns surface strings grounded to character offsets.

Canonical mapping is intentionally NOT done here — the model only proposes
surfaces; we map them to the 98 Recon names downstream (Phase 1+).

Reusable entry point:
    extract_guided(text, query_pathways, vocab=None, model="qwen2.5:7b")
        -> [{"surface": str, "start": int, "end": int}, ...]

Run as a module:
    venv310/bin/python3 -m llm.extract_guided   # smoke test on one golden abstract
"""

import json
import re
from typing import Optional

import requests

from prompts.pathway_extraction_guided import (
    GUIDED,
    RULES_LENIENT,
    RULES_STRICT,
    VOCAB_BLOCK,
)

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:7b"
MAX_CHARS = 3000


def build_prompt(
    text: str,
    query_pathways: list[str],
    vocab: Optional[list[str]] = None,
    lenient: bool = True,
) -> str:
    if query_pathways:
        qp = "\n".join(f"- {p}" for p in query_pathways)
    else:
        qp = "- (none provided)"
    vocab_block = ""
    if vocab:
        vocab_list = ", ".join(f'"{v}"' for v in vocab)
        vocab_block = VOCAB_BLOCK.format(vocab_list=vocab_list)
    rules = RULES_LENIENT if lenient else RULES_STRICT
    return GUIDED.format(
        text=text[:MAX_CHARS], query_pathways=qp, vocab_block=vocab_block, rules=rules
    )


def call_llm(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 120) -> list[str]:
    """Return the raw list of surface strings the model proposed (unverified)."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "seed": 42},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        parsed = json.loads(m.group())
        return [s.strip() for s in parsed.get("mentions", []) if isinstance(s, str) and s.strip()]
    except Exception:
        return []


def find_offsets(text: str, surface: str) -> list[tuple[int, int]]:
    """All non-overlapping, case-insensitive verbatim occurrences of surface."""
    spans: list[tuple[int, int]] = []
    if not surface:
        return spans
    for m in re.finditer(re.escape(surface), text, flags=re.IGNORECASE):
        spans.append((m.start(), m.end()))
    return spans


def ground(text: str, surfaces: list[str]) -> list[dict]:
    """Keep only surfaces present verbatim in text; expand to char-offset spans.

    Deduplicated on (start, end); the offset text (as it truly appears) is kept as
    `surface` so downstream code always sees the real substring.
    """
    seen: set[tuple[int, int]] = set()
    grounded: list[dict] = []
    for s in surfaces:
        for start, end in find_offsets(text, s):
            if (start, end) in seen:
                continue
            seen.add((start, end))
            grounded.append({"surface": text[start:end], "start": start, "end": end})
    grounded.sort(key=lambda d: d["start"])
    return grounded


def extract_guided(
    text: str,
    query_pathways: list[str],
    vocab: Optional[list[str]] = None,
    model: str = DEFAULT_MODEL,
    lenient: bool = True,
) -> list[dict]:
    # Chosen Phase 3 config (P3-0c): no-vocab (vocab=None) + lenient compound rule.
    # The prompt's "synonyms" wording is baked into pathway_extraction_guided.py.
    prompt = build_prompt(text, query_pathways, vocab, lenient=lenient)
    surfaces = call_llm(prompt, model=model)
    return ground(text, surfaces)


def _smoke_test() -> None:
    """Run once on a golden abstract to sanity-check the end-to-end path."""
    from pathlib import Path

    gold = json.loads(
        (Path(__file__).resolve().parents[1] / "playground/golden_set/golden_set.json").read_text()
    )
    art = gold["articles"][2]  # PMID 40225847 (arginine/proline)
    text = art["abstract"]
    out = extract_guided(text, query_pathways=["arginine and proline metabolism"], vocab=None)
    print(f"PMID {art['pmid']} — {len(out)} grounded mentions:")
    for d in out:
        print(f"  [{d['start']:>4}:{d['end']:<4}] {d['surface']}")


if __name__ == "__main__":
    _smoke_test()
