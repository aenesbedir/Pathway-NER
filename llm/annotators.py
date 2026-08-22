#!/usr/bin/env python3
"""
annotators.py

One interface, two span producers. Everything downstream of extraction — the
deterministic booster, merge(), canonicalize(), the resumable cache, the doccano
export — works on character-offset spans and does not care where they came from.
This module is the seam that makes that swappable.

    resolve_annotator("qwen2.5:14b")                     -> LLMAnnotator
    resolve_annotator("runs-truba-checkpoints/.../seed7") -> NERAnnotator

The argument is the same `--model` the runner already took: a registry key or raw
ollama tag keeps the LLM path byte-identical to before, while a filesystem
directory holding `model.safetensors` (or `checkpoint-*/`) selects the fine-tuned
token classifier. Detection is a disk check, not a flag, because the two namespaces
cannot collide — an ollama tag is never a path that exists.

Contract (`Annotator`):
    tag         identity, written into every record
    cache_slug  directory name under the cache root; two annotators never share one
    source      the `source` field of the spans it produces
    max_input   what it can see of an abstract, for the run metadata
    spans_batch(items) -> list per item of {"surface", "start", "end"}

`spans_batch` is the primitive rather than a single-text call because the NER path
is GPU batched and a per-abstract loop wastes most of the throughput; the LLM path
implements it as a sequential loop since each abstract is its own HTTP request.

Failure semantics differ and that is deliberate. The LLM raises `LLMCallError` so a
broken call can never be mistaken for "found nothing" — the runner must not cache
that (see llm/run_silver.py). The NER model is deterministic: it either loads or
raises at construction time, and after that every call succeeds.

Long abstracts:
    LLM  — truncated at MAX_CHARS characters (llm/extract_guided.py).
    NER  — the encoder window is 512 tokens, so the text is tiled with overlapping
           windows (`stride`) and the spans are unioned. Offsets stay in the
           original text's coordinates, so no window arithmetic is needed; a
           mention split by a window edge appears clipped in one window and whole
           in another, and merge() keeps the longer one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Protocol

try:                                    # run from repo root / llm on sys.path
    from extract_guided import extract_guided
    from models import ModelSpec, resolve
except ImportError:                     # imported as `llm.annotators`
    from llm.extract_guided import extract_guided
    from llm.models import ModelSpec, resolve

# The label scheme every pathway checkpoint was trained with
# (preprocessing/tag_bio.py, train.py, scripts/score_gt_100.py).
ID2LABEL = {0: "O", 1: "B-Pathway", 2: "I-Pathway"}

# Overlap between consecutive NER windows, in tokens. Has to exceed the longest
# pathway name so a mention is whole in at least one window; the longest Recon
# canonical ("androgen and estrogen synthesis and metabolism") is ~12 wordpieces.
DEFAULT_STRIDE = 64


class Annotator(Protocol):
    tag: str
    cache_slug: str
    source: str
    max_input: str

    def spans_batch(self, items: list[tuple[str, list[str]]]) -> list[list[dict]]:
        """(text, query_pathways) pairs -> raw spans per item."""
        ...


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")


# ─── LLM backend ─────────────────────────────────────────────────────────────

class LLMAnnotator:
    """The original path: one guided Ollama call per abstract.

    A thin wrapper — the prompt, the grounding of surfaces back to offsets and the
    per-family request body all stay where they were.
    """

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self.tag = spec.tag
        self.cache_slug = spec.cache_slug
        self.source = "llm_silver"      # unchanged: downstream analyses match on it
        self.max_input = "3000 chars"
        # One generation request per abstract: batching would only make a single
        # failure take its neighbours down with it.
        self.batch_size = 1

    def spans_batch(self, items: list[tuple[str, list[str]]]) -> list[list[dict]]:
        # Sequential on purpose: each item is a separate generation request, so
        # there is nothing to batch. LLMCallError propagates — the runner decides.
        return [extract_guided(text, qps, model=self.tag) for text, qps in items]

    def __repr__(self) -> str:
        return f"LLMAnnotator({self.tag})"


# ─── NER checkpoint backend ──────────────────────────────────────────────────

def checkpoint_path(dir_: Path) -> Optional[Path]:
    """The directory holding weights: `dir_` itself or its last `checkpoint-*`.

    Returns None when this is not a checkpoint at all, which is what makes
    resolve_annotator's dispatch a question about the filesystem rather than a flag.
    """
    if not dir_.is_dir():
        return None
    if (dir_ / "model.safetensors").exists() or (dir_ / "pytorch_model.bin").exists():
        return dir_
    cps = sorted(dir_.glob("checkpoint-*"))
    return cps[-1] if cps else None


def decode_word_spans(tags: list[str], offsets: list[tuple[int, int]]) -> list[dict]:
    """B/I/O over word offsets -> character spans.

    Note the offsets must be *word* spans (first wordpiece start, last wordpiece
    end). Feeding first-wordpiece offsets — as the scoring script does, correctly,
    because seqeval matches token runs — would cut the tail off every multi-piece
    word: `oxidative phosphorylation` comes back as `oxidative phosphoryl`. That is
    invisible in an entity-F1 number and very visible in a doccano annotation.
    """
    spans: list[dict] = []
    cur: Optional[list[int]] = None
    for tag, (s, e) in zip(tags, offsets):
        if tag == "B-Pathway":
            if cur is not None:
                spans.append({"start": cur[0], "end": cur[1]})
            cur = [s, e]
        elif tag == "I-Pathway":
            if cur is None:
                cur = [s, e]            # stray I — start a span, same as scoring
            else:
                cur[1] = e
        else:
            if cur is not None:
                spans.append({"start": cur[0], "end": cur[1]})
                cur = None
    if cur is not None:
        spans.append({"start": cur[0], "end": cur[1]})
    return spans


def dedupe_spans(spans: list[dict], text: str) -> list[dict]:
    """Union overlapping/touching spans, then attach the real substring.

    Windows overlap, so the same mention is proposed more than once and sometimes
    clipped differently on each side of a window edge. Unioning by character range
    both de-duplicates and repairs the clipped copy.
    """
    if not spans:
        return []
    out: list[dict] = []
    for sp in sorted(spans, key=lambda d: (d["start"], d["end"])):
        if out and sp["start"] <= out[-1]["end"]:
            out[-1]["end"] = max(out[-1]["end"], sp["end"])
        else:
            out.append(dict(sp))
    return [{"surface": text[s["start"]:s["end"]], "start": s["start"], "end": s["end"]}
            for s in out]


class NERAnnotator:
    """A fine-tuned token classifier (runs-truba-checkpoints/…, models/…).

    Ignores `query_pathways`: the model reads the abstract and nothing else. The
    field stays in the interface because the record keeps it as metadata and the
    LLM backend needs it.
    """

    def __init__(self, path: Path, batch_size: int = 16,
                 stride: int = DEFAULT_STRIDE, device: Optional[str] = None) -> None:
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        self._torch = torch
        weights = checkpoint_path(path)
        if weights is None:
            raise ValueError(f"no model weights under {path}")
        self.path = path
        self.tokenizer = AutoTokenizer.from_pretrained(str(weights))
        self.model = AutoModelForTokenClassification.from_pretrained(str(weights))
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device).eval()

        self.max_tokens = min(self.tokenizer.model_max_length,
                              getattr(self.model.config, "max_position_embeddings", 512))
        self.stride = min(stride, self.max_tokens // 2)
        self.batch_size = batch_size
        # Path-derived so two checkpoints of the same architecture never collide.
        self.tag = str(path)
        self.cache_slug = "ner_" + _slug(str(path).replace("/", "__"))
        self.source = "ner:" + "/".join(path.parts[-3:])
        self.max_input = f"{self.max_tokens} tokens (stride {self.stride})"

    # -- internals ------------------------------------------------------------

    def _windows(self, text: str):
        """Overlapping encodings of one text, each carrying original-text offsets."""
        return self.tokenizer(
            text,
            max_length=self.max_tokens,
            truncation=True,
            stride=self.stride,
            return_overflowing_tokens=True,
            return_offsets_mapping=True,
            return_attention_mask=True,
        )

    def _word_offsets(self, enc, window_index: int) -> list[tuple[int, list[int]]]:
        """[(token position of a word's first piece, [start, end] of the whole word)].

        Special tokens (`word_id is None`) are dropped; a word's pieces are folded
        into one entry so the character span covers the entire word.
        """
        word_ids = enc.word_ids(window_index)
        offsets = enc["offset_mapping"][window_index]
        by_word: dict[int, list] = {}
        order: list[int] = []
        for i, wid in enumerate(word_ids):
            if wid is None:
                continue
            s, e = offsets[i]
            if wid not in by_word:
                by_word[wid] = [i, [s, e]]
                order.append(wid)
            else:
                by_word[wid][1][1] = max(by_word[wid][1][1], e)
        return [(by_word[w][0], by_word[w][1]) for w in order]

    # -- interface ------------------------------------------------------------

    def spans_batch(self, items: list[tuple[str, list[str]]]) -> list[list[dict]]:
        torch = self._torch
        texts = [t for t, _ in items]

        # Flatten every text's windows into one queue, remembering which text each
        # window belongs to, so a batch can straddle documents and short abstracts
        # do not each pay for their own forward pass.
        queue: list[tuple[int, list[int], list[int], list[tuple[int, list[int]]]]] = []
        for doc_i, text in enumerate(texts):
            enc = self._windows(text)
            for w in range(len(enc["input_ids"])):
                queue.append((doc_i, enc["input_ids"][w], enc["attention_mask"][w],
                              self._word_offsets(enc, w)))

        raw: list[list[dict]] = [[] for _ in texts]
        pad = self.tokenizer.pad_token_id or 0
        for i in range(0, len(queue), self.batch_size):
            chunk = queue[i:i + self.batch_size]
            width = max(len(ids) for _, ids, _, _ in chunk)
            input_ids = torch.tensor(
                [ids + [pad] * (width - len(ids)) for _, ids, _, _ in chunk],
                device=self.device)
            attn = torch.tensor(
                [am + [0] * (width - len(am)) for _, _, am, _ in chunk],
                device=self.device)
            with torch.no_grad():
                logits = self.model(input_ids=input_ids, attention_mask=attn).logits
            pred = logits.argmax(dim=-1).cpu().numpy()

            for row, (doc_i, _, _, word_offsets) in enumerate(chunk):
                tags = [ID2LABEL[int(pred[row][pos])] for pos, _ in word_offsets]
                offs = [(o[0], o[1]) for _, o in word_offsets]
                raw[doc_i].extend(decode_word_spans(tags, offs))

        return [dedupe_spans(spans, text) for spans, text in zip(raw, texts)]

    def __repr__(self) -> str:
        return f"NERAnnotator({self.path}, {self.max_input}, {self.device})"


# ─── dispatch ────────────────────────────────────────────────────────────────

def resolve_annotator(name: str, **ner_kwargs) -> Annotator:
    """`name` is a checkpoint directory -> NER; anything else -> LLM (as before)."""
    path = Path(name)
    if checkpoint_path(path) is not None:
        return NERAnnotator(path, **ner_kwargs)
    if path.is_dir():
        raise SystemExit(
            f"{name} is a directory but holds no model.safetensors / checkpoint-*")
    return LLMAnnotator(resolve(name))
