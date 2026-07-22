#!/usr/bin/env python3
"""
models.py

One place to declare an LLM annotator and everything the request needs to be made
correctly. Adding a model should be a dict entry here, never an edit to the call site.

Why this exists
---------------
Two settings differ per model family and both are silent failures when wrong:

1. **Thinking / reasoning mode.** Qwen3+ and other reasoning models emit a chain of
   thought before the answer. Our task is deterministic span extraction against a
   strict JSON schema, so thinking only costs latency and can push the JSON object
   out of the response. It has to be switched off explicitly (`think: false`), and
   the flag is harmless on models that do not have the mode.
2. **Sampling.** Everything here runs at `temperature=0, seed=42`. Ollama is still
   not bit-reproducible across runs, but anything else makes it much worse.

Cache scoping
-------------
`cache_slug` is the per-model cache directory (`data/raw/llm_cache_silver/<slug>/`).
The silver cache used to be keyed on pmid alone, which meant swapping the model
silently replayed the previous model's answers for every already-seen abstract —
the run looked successful and re-labelling was impossible. Scoping by model makes a
model swap a cache miss, which is the correct behaviour.

Usage:
    from models import resolve
    spec = resolve("qwen3.5:9b")        # registry key or raw ollama tag
    spec.tag, spec.cache_slug, spec.request_body(prompt)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _slug(tag: str) -> str:
    """Ollama tag -> filesystem-safe directory name ('qwen2.5:14b' -> 'qwen2.5_14b')."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", tag)


@dataclass(frozen=True)
class ModelSpec:
    """How to call one model, and where its cache lives."""

    tag: str                                    # ollama tag, as `ollama list` prints it
    note: str = ""                              # why this entry exists / when to use it
    options: dict = field(default_factory=dict)  # ollama `options` (sampling etc.)
    payload_extra: dict = field(default_factory=dict)  # top-level /api/generate keys
    prompt_suffix: str = ""                     # appended to the prompt, e.g. "/no_think"
    cache_slug: str = ""                        # defaults to a slug of `tag`

    def __post_init__(self) -> None:
        if not self.cache_slug:
            object.__setattr__(self, "cache_slug", _slug(self.tag))

    def request_body(self, prompt: str) -> dict:
        """Full JSON body for POST /api/generate."""
        return {
            "model": self.tag,
            "prompt": prompt + self.prompt_suffix,
            "stream": False,
            "options": dict(self.options),
            **self.payload_extra,
        }


# Deterministic decoding for every entry — see module docstring.
_GREEDY = {"temperature": 0, "seed": 42}

# Structured output. Must mirror the contract the prompt asks for
# (llm/prompts/pathway_extraction_guided.py: `{"mentions": [...]}`) — ollama constrains
# decoding to this shape, so a model physically cannot answer with anything else.
#
# Measured on qwen3.5:9b, PMID 42121260: unconstrained it reasons *inside* the array
# ('"fatty acid synthesis" (implied by context but exact phrase check: wait, ...') and
# the JSON never parses — deterministically, at temperature 0. Constrained, the same
# call returns the three mentions it was reaching for, and does it in 1.2 s instead of
# 78 s: the rambling was the slow part. On a control abstract that already worked the
# output is byte-identical, so this buys robustness without changing behaviour.
#
# The cache is keyed on the model tag alone, so it does not notice that the request
# shape changed: adding or removing this flag on an entry means deleting that model's
# cache directory by hand, or the run silently mixes pre- and post-change records.
_MENTIONS_SCHEMA = {
    "type": "object",
    "properties": {"mentions": {"type": "array", "items": {"type": "string"}}},
    "required": ["mentions"],
}

REGISTRY: dict[str, ModelSpec] = {
    "qwen2.5:14b": ModelSpec(
        tag="qwen2.5:14b",
        note="Phase 3 production annotator. 9.0 GB Q4_K_M — does not fit the 8 GB "
             "card fully, so part of it runs CPU-offloaded.",
        options=_GREEDY,
        payload_extra={"format": _MENTIONS_SCHEMA},
    ),
    "qwen2.5:7b": ModelSpec(
        tag="qwen2.5:7b",
        note="Smoke tests and throughput checks. Fits VRAM; measurably weaker.",
        options=_GREEDY,
    ),
    "qwen3.5:9b": ModelSpec(
        tag="qwen3.5:9b",
        note="Candidate replacement (reports/llm_selection_and_hardware_2026-07.md "
             "§3.2). ~6.6 GB, fits the 8 GB card fully. Reasoning model: `think: False` "
             "turns the thinking channel off, but that alone does not stop it reasoning "
             "inline — the schema does. (`think: True` is worse still: ~82 s/abstract "
             "and an empty `response`, all 14k characters go to `thinking`.)",
        options=_GREEDY,
        payload_extra={"think": False, "format": _MENTIONS_SCHEMA},
    ),
    "qwen3.5:4b": ModelSpec(
        tag="qwen3.5:4b",
        note="Smaller sibling, for throughput comparisons on the same generation.",
        options=_GREEDY,
        payload_extra={"think": False, "format": _MENTIONS_SCHEMA},
    ),
}

DEFAULT = "qwen2.5:14b"


def resolve(name: str | None = None) -> ModelSpec:
    """ModelSpec for a registry key, or a generic one for an unregistered tag.

    An unknown tag still runs — it just gets greedy decoding, no thinking flag and a
    cache directory of its own. That keeps ad-hoc experiments possible without an
    edit here, while never letting two models share a cache.
    """
    tag = name or DEFAULT
    if tag in REGISTRY:
        return REGISTRY[tag]
    return ModelSpec(tag=tag, note="unregistered — generic greedy config",
                     options=_GREEDY)


def names() -> list[str]:
    return list(REGISTRY)


if __name__ == "__main__":
    for key, spec in REGISTRY.items():
        mark = "  (default)" if key == DEFAULT else ""
        print(f"{key}{mark}\n  cache : {spec.cache_slug}\n  body  : "
              f"{ {k: v for k, v in spec.request_body('<prompt>').items() if k != 'prompt'} }"
              f"\n  note  : {spec.note}\n")
