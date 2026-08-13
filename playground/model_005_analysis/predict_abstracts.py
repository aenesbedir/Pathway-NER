#!/usr/bin/env python3
"""Run a fine-tuned pathway-NER checkpoint over an arbitrary corpus.

The input may be a JSON array or JSONL. Each record must have a PMID. Text can
be present in the record as ``text`` or ``abstract``; when the input only
contains PMIDs and labels (for example a silver-run JSONL), pass ``--articles``
to resolve text from a second JSON/JSONL corpus.

Long texts are processed in overlapping tokenizer windows. Predictions are
decoded at word level because the training pipeline supervises only the first
subword of each word. Duplicate and fully contained window-level spans are
removed before character offsets are written.

Output is JSONL with one record per input PMID::

    {"pmid": "123", "model": "...", "text_sha256": "...",
     "num_windows": 2,
     "spans": [{"start": 10, "end": 25, "text": "lipid metabolism"}]}

Example from the repository root::

    venv310/bin/python3 playground/model_005_analysis/predict_abstracts.py \
        --model-dir models/pathway-ner-gold-wave4-random-all-biomedbert-base \
        --input data/silver/pathway_remaining_6125.jsonl \
        --articles data/raw/articles.json \
        --output data/processed/pathway-ner/pathway_best_remaining_6125.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch
from tqdm import tqdm
from transformers import AutoModelForTokenClassification, AutoTokenizer


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load a JSON array, an object containing ``articles``, or JSONL."""
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")

    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON at {path}:{line_number}: {exc}"
                    ) from exc
                if not isinstance(record, dict):
                    raise ValueError(
                        f"Expected a JSON object at {path}:{line_number}"
                    )
                records.append(record)
        return records

    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if isinstance(value, dict) and isinstance(value.get("articles"), list):
        value = value["articles"]
    if not isinstance(value, list) or not all(
        isinstance(record, dict) for record in value
    ):
        raise ValueError(
            f"Expected {path} to contain a JSON array of objects or an "
            "object with an 'articles' array"
        )
    return value


def record_pmid(record: dict[str, Any], *, context: str) -> str:
    """Read a PMID from the top level or Doccano-style nested metadata."""
    value = record.get("pmid")
    if value is None and isinstance(record.get("meta"), dict):
        value = record["meta"].get("pmid")
    if value is None or not str(value).strip():
        raise ValueError(f"{context} has no PMID")
    return str(value)


def record_text(record: dict[str, Any], text_field: str) -> str | None:
    """Return normalized text from a record, or None when it has no text."""
    fields = ("text", "abstract") if text_field == "auto" else (text_field,)
    for field in fields:
        value = record.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"Field {field!r} must be a string")
            return value.strip()
    return None


def index_article_texts(path: Path, text_field: str) -> dict[str, str]:
    """Build a PMID-to-text lookup from a JSON/JSONL article corpus."""
    texts: dict[str, str] = {}
    for index, record in enumerate(load_records(path), 1):
        pmid = record_pmid(record, context=f"{path} record {index}")
        if pmid in texts:
            raise ValueError(f"Duplicate PMID {pmid} in {path}")
        text = record_text(record, text_field)
        if text is None:
            text = ""
        texts[pmid] = text
    return texts


def prepare_inputs(
    records: Sequence[dict[str, Any]],
    *,
    article_texts: dict[str, str] | None,
    text_field: str,
) -> list[tuple[str, str]]:
    """Resolve and validate an ordered, duplicate-free PMID/text collection."""
    prepared: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        pmid = record_pmid(record, context=f"input record {index}")
        if pmid in seen:
            raise ValueError(f"Duplicate PMID {pmid} in the input")
        seen.add(pmid)
        text = record_text(record, text_field)
        if text is None:
            if article_texts is None:
                raise ValueError(
                    f"PMID {pmid} has no text; pass --articles to resolve it"
                )
            if pmid not in article_texts:
                raise ValueError(f"PMID {pmid} is absent from --articles")
            text = article_texts[pmid]
        prepared.append((pmid, text))
    if not prepared:
        raise ValueError("The input contains no records")
    return prepared


def normalize_bio_label(label: str) -> str:
    """Normalize common token-classification label spellings to O/B/I."""
    upper = label.upper()
    if upper == "O":
        return "O"
    if upper == "B" or upper.startswith(("B-", "B_")):
        return "B"
    if upper == "I" or upper.startswith(("I-", "I_")):
        return "I"
    raise ValueError(f"Unsupported token label {label!r}; expected a BIO model")


def label_prefixes(model: Any) -> dict[int, str]:
    id2label = {int(key): str(value) for key, value in model.config.id2label.items()}
    prefixes = {index: normalize_bio_label(label) for index, label in id2label.items()}
    present = set(prefixes.values())
    if "O" not in present or not {"B", "I"} & present:
        raise ValueError(f"Model does not expose a usable BIO label map: {id2label}")
    return prefixes


def effective_max_length(tokenizer: Any, model: Any, requested: int | None) -> int:
    limits: list[int] = []
    tokenizer_limit = getattr(tokenizer, "model_max_length", None)
    if isinstance(tokenizer_limit, int) and 0 < tokenizer_limit < 1_000_000:
        limits.append(tokenizer_limit)
    model_limit = getattr(model.config, "max_position_embeddings", None)
    if isinstance(model_limit, int) and model_limit > 0:
        limits.append(model_limit)
    if requested is not None:
        limits.append(requested)
    if not limits:
        raise ValueError("Could not determine a finite model maximum length")
    return min(limits)


def words_from_window(
    offsets: Sequence[Sequence[int]],
    labels: Sequence[int],
    word_ids: Sequence[int | None],
    prefixes: dict[int, str],
) -> list[list[int | str]]:
    """Collapse subwords using the first-subword label used during training."""
    words: list[list[int | str]] = []
    previous_word_id: int | None = None
    for (start, end), label_id, word_id in zip(offsets, labels, word_ids):
        if word_id is None:
            continue
        if word_id != previous_word_id:
            words.append([start, end, prefixes[label_id]])
        else:
            words[-1][1] = end
        previous_word_id = word_id
    return words


def spans_from_words(words: Iterable[Sequence[int | str]]) -> list[tuple[int, int]]:
    """BIO-decode word predictions; a leading I opens a lenient span."""
    spans: list[tuple[int, int]] = []
    current: list[int] | None = None
    for raw_start, raw_end, raw_prefix in words:
        start, end, prefix = int(raw_start), int(raw_end), str(raw_prefix)
        if prefix == "B":
            if current:
                spans.append((current[0], current[1]))
            current = [start, end]
        elif prefix == "I":
            if current:
                current[1] = end
            else:
                current = [start, end]
        elif current:
            spans.append((current[0], current[1]))
            current = None
    if current:
        spans.append((current[0], current[1]))
    return spans


def keep_longest(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Deduplicate window predictions and remove fully contained fragments."""
    unique = sorted(set(spans), key=lambda span: span[1] - span[0], reverse=True)
    kept: list[tuple[int, int]] = []
    for span in unique:
        if not any(
            other[0] <= span[0] and span[1] <= other[1] for other in kept
        ):
            kept.append(span)
    return sorted(kept, key=lambda span: (span[0], span[1]))


@torch.no_grad()
def predict(
    text: str,
    tokenizer: Any,
    model: Any,
    device: torch.device,
    *,
    max_length: int,
    stride: int,
    window_batch_size: int,
    prefixes: dict[int, str],
) -> tuple[list[dict[str, Any]], int]:
    if not text:
        return [], 0
    encoded = tokenizer(
        text,
        max_length=max_length,
        truncation=True,
        stride=stride,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        return_tensors="pt",
        padding=True,
    )
    offsets = encoded.pop("offset_mapping").tolist()
    encoded.pop("overflow_to_sample_mapping", None)
    num_windows = len(offsets)
    word_ids = [encoded.word_ids(index) for index in range(num_windows)]
    predictions: list[list[int]] = []

    for start in range(0, num_windows, window_batch_size):
        end = min(start + window_batch_size, num_windows)
        model_inputs = {
            key: value[start:end].to(device)
            for key, value in encoded.items()
            if key in tokenizer.model_input_names
        }
        predictions.extend(model(**model_inputs).logits.argmax(-1).tolist())

    window_spans: list[tuple[int, int]] = []
    for window_offsets, labels, window_word_ids in zip(
        offsets, predictions, word_ids
    ):
        words = words_from_window(
            window_offsets, labels, window_word_ids, prefixes
        )
        window_spans.extend(spans_from_words(words))

    spans = keep_longest(window_spans)
    return [
        {"start": start, "end": end, "text": text[start:end]}
        for start, end in spans
    ], num_windows


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    return device


def write_jsonl_atomic(records: Iterable[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--articles",
        type=Path,
        default=None,
        help="optional JSON/JSONL text source for PMID-only input records",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--text-field",
        choices=("auto", "abstract", "text"),
        default="auto",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--max-length", type=int, default=None)
    parser.add_argument("--stride", type=int, default=64)
    parser.add_argument("--window-batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.window_batch_size <= 0:
        parser.error("--window-batch-size must be positive")
    if args.stride < 0:
        parser.error("--stride cannot be negative")
    if args.max_length is not None and args.max_length < 8:
        parser.error("--max-length must be at least 8")
    return args


def main() -> None:
    args = parse_args()
    model_dir = args.model_dir.expanduser().resolve()
    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    articles_path = args.articles.expanduser().resolve() if args.articles else None
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Model directory does not exist: {model_dir}")
    if output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Pass --overwrite to replace it."
        )
    if output_path in {input_path, articles_path}:
        raise ValueError("Output must differ from every input path")

    records = load_records(input_path)
    if args.limit is not None:
        records = records[: args.limit]
    article_texts = (
        index_article_texts(articles_path, args.text_field) if articles_path else None
    )
    prepared = prepare_inputs(
        records, article_texts=article_texts, text_field=args.text_field
    )

    device = choose_device(args.device)
    tokenizer = AutoTokenizer.from_pretrained(
        str(model_dir), use_fast=True, local_files_only=args.local_files_only
    )
    if not tokenizer.is_fast:
        raise ValueError("A fast tokenizer is required for character offsets")
    model = AutoModelForTokenClassification.from_pretrained(
        str(model_dir), local_files_only=args.local_files_only
    )
    model.to(device).eval()
    prefixes = label_prefixes(model)
    max_length = effective_max_length(tokenizer, model, args.max_length)
    if args.stride >= max_length - 2:
        raise ValueError(
            f"--stride must be smaller than {max_length - 2}, got {args.stride}"
        )

    print(f"Model     : {model_dir}")
    print(f"Input     : {input_path}")
    if articles_path:
        print(f"Articles  : {articles_path}")
    print(f"Documents : {len(prepared)}")
    print(f"Device    : {device}")
    print(f"Windowing : max_length={max_length} stride={args.stride}")

    output_records: list[dict[str, Any]] = []
    span_count = 0
    positive_documents = 0
    for pmid, text in tqdm(prepared, unit="document", desc="Pathway NER"):
        spans, num_windows = predict(
            text,
            tokenizer,
            model,
            device,
            max_length=max_length,
            stride=args.stride,
            window_batch_size=args.window_batch_size,
            prefixes=prefixes,
        )
        span_count += len(spans)
        positive_documents += bool(spans)
        output_records.append(
            {
                "pmid": pmid,
                "model": str(model_dir),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "num_windows": num_windows,
                "spans": spans,
            }
        )

    write_jsonl_atomic(output_records, output_path)
    print("-" * 64)
    print(f"Output             : {output_path}")
    print(f"Documents          : {len(output_records)}")
    print(f"Positive documents : {positive_documents}")
    print(f"Spans              : {span_count}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
