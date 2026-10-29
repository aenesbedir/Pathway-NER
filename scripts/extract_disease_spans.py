#!/usr/bin/env python3
"""Extract disease spans from a JSONL corpus with a token-classification model.

The input must contain one JSON object per line with a ``pmid`` and either an
``abstract`` or ``text`` field. The output contains one record per input document,
including documents for which the model finds no disease:

    {"pmid": "123", "model": "...", "model_revision": "...",
     "text_sha256": "...", "num_windows": 2,
     "spans": [{"start": 10, "end": 24, "text": "lung disease",
                "label": "DISEASE", "score": 0.9971}]}

Long documents are processed in overlapping windows. Probabilities for tokens
that occur in more than one window are averaged before BIO decoding, avoiding
both duplicate spans and unreliable boundaries at window edges.

The optional ``--postprocess bent`` mode reproduces the disease-relevant part of
BENT's ``correct_tokens`` rule: consecutive predictions that touch or have one
character between them are merged, their scores are averaged, and remaining
one-character entities are removed. Raw output remains the default so the two
representations can be compared explicitly.

Examples (run from the repository root):

    /home/enes/NER-pipeline/venv310/bin/python3 \
        scripts/extract_disease_spans.py \
        --model /home/enes/.cache/huggingface/hub/models--pruas--BENT-PubMedBERT-NER-Disease \
        --input /home/enes/NER-pipeline/data/processed/gold-wave4/articles.jsonl

    # Small smoke run to a separate output file.
    /home/enes/NER-pipeline/venv310/bin/python3 \
        scripts/extract_disease_spans.py --model /path/to/model \
        --input /path/to/articles.jsonl --output /tmp/disease-spans.jsonl \
        --limit 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterator, Sequence

import torch
from tqdm import tqdm
from transformers import AutoModelForTokenClassification, AutoTokenizer


DATA_ROOT = Path(
    os.environ.get("NER_PIPELINE_DATA_DIR", "/home/enes/NER-pipeline/data")
).expanduser()
DEFAULT_INPUT = DATA_ROOT / "processed/gold-wave4/articles.jsonl"
DEFAULT_OUTPUT = DATA_ROOT / "processed/disease-ner/disease_spans.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def resolve_cached_model(model_arg: str) -> tuple[str, str | None]:
    """Resolve either a normal model reference or a Hugging Face cache root.

    ``from_pretrained`` cannot load directly from a directory named
    ``models--owner--model`` because its files live under ``snapshots/<sha>``.
    Accepting that directory is useful here because it is the natural path users
    find while inspecting the local cache.
    """
    path = Path(model_arg).expanduser()
    if not path.exists():
        return model_arg, None

    path = path.resolve()
    if (path / "config.json").is_file():
        revision = path.name if path.parent.name == "snapshots" else None
        return str(path), revision

    refs_main = path / "refs/main"
    snapshots = path / "snapshots"
    if refs_main.is_file() and snapshots.is_dir():
        revision = refs_main.read_text(encoding="utf-8").strip()
        if not revision or "/" in revision or "\\" in revision:
            raise ValueError(f"Invalid Hugging Face cache revision in {refs_main}")
        snapshot = snapshots / revision
        if not (snapshot / "config.json").is_file():
            raise FileNotFoundError(
                f"The main cache snapshot has no config.json: {snapshot}"
            )
        return str(snapshot), revision

    raise FileNotFoundError(
        f"{path} is not a loadable model directory and is not a Hugging Face "
        "cache root with refs/main"
    )


def display_model_name(model_arg: str) -> str:
    """Return a stable, readable name while retaining arbitrary model paths."""
    name = Path(model_arg).expanduser().name
    if name.startswith("models--"):
        parts = name.removeprefix("models--").split("--", maxsplit=1)
        if len(parts) == 2:
            return "/".join(parts)
    return model_arg


def bio_prefix(label: str) -> str:
    """Normalize O/B/I and B-DISEASE/I-DISEASE style labels."""
    upper = label.upper()
    if upper == "O":
        return "O"
    if upper == "B" or upper.startswith(("B-", "B_")):
        return "B"
    if upper == "I" or upper.startswith(("I-", "I_")):
        return "I"
    raise ValueError(
        f"Unsupported label {label!r}; this script expects a BIO disease model"
    )


def validate_label_schema(id2label: dict[int, str]) -> dict[int, str]:
    prefixes = {idx: bio_prefix(label) for idx, label in id2label.items()}
    present = set(prefixes.values())
    if "O" not in present or not ({"B", "I"} & present):
        raise ValueError(
            f"The model labels are not a usable BIO schema: {id2label}"
        )
    return prefixes


def iter_jsonl(path: Path, limit: int | None = None) -> Iterator[dict[str, Any]]:
    yielded = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected an object at {path}:{line_number}")
            yield record
            yielded += 1
            if limit is not None and yielded >= limit:
                return


def read_records(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    records = list(iter_jsonl(path, limit))
    if not records:
        raise ValueError(f"No records found in {path}")

    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        if "pmid" not in record:
            raise ValueError(f"Input record {index} has no pmid")
        pmid = str(record["pmid"])
        if pmid in seen:
            raise ValueError(f"Duplicate PMID in input: {pmid}")
        seen.add(pmid)
        if not any(field in record for field in ("abstract", "text")):
            raise ValueError(
                f"Input record {index} (PMID {pmid}) has neither abstract nor text"
            )
    return records


def record_text(record: dict[str, Any], text_field: str) -> str:
    if text_field == "auto":
        value = record.get("text")
        if value is None:
            value = record.get("abstract")
    else:
        value = record.get(text_field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(
            f"PMID {record.get('pmid')} has a non-string {text_field} value"
        )
    return value


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(requested)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    return device


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


def batched(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def decode_spans(
    text: str,
    token_probabilities: dict[tuple[int, int], tuple[torch.Tensor, int]],
    prefixes: dict[int, str],
) -> list[dict[str, Any]]:
    """Average overlapping-window predictions and decode one global BIO stream."""
    tokens: list[tuple[int, int, str, float]] = []
    for (start, end), (probability_sum, count) in token_probabilities.items():
        probabilities = probability_sum / count
        label_id = int(probabilities.argmax().item())
        tokens.append(
            (start, end, prefixes[label_id], float(probabilities[label_id].item()))
        )
    tokens.sort(key=lambda item: (item[0], item[1]))

    spans: list[dict[str, Any]] = []
    active_start: int | None = None
    active_end: int | None = None
    active_scores: list[float] = []

    def finish() -> None:
        nonlocal active_start, active_end, active_scores
        if active_start is not None and active_end is not None:
            spans.append(
                {
                    "start": active_start,
                    "end": active_end,
                    "text": text[active_start:active_end],
                    "label": "DISEASE",
                    "score": round(sum(active_scores) / len(active_scores), 6),
                }
            )
        active_start = None
        active_end = None
        active_scores = []

    for start, end, prefix, score in tokens:
        if prefix == "O":
            finish()
        elif prefix == "B":
            finish()
            active_start, active_end, active_scores = start, end, [score]
        else:  # I
            if active_start is None:
                active_start, active_end, active_scores = start, end, [score]
            else:
                active_end = max(active_end or end, end)
                active_scores.append(score)
    finish()
    return spans


def bent_postprocess_spans(
    text: str, spans: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply BENT's adjacency correction for a single disease entity type.

    BENT's ``correct_tokens`` joins consecutive annotations when the previous
    end equals the current start or ``current start - 1``. The intervening
    character is therefore retained (usually a space, hyphen, or slash). It then
    removes one-character non-chemical entities; every entity here is a disease.
    """
    merged: list[dict[str, Any]] = []
    for span in spans:
        current = dict(span)
        current["merged_from"] = int(current.get("merged_from", 1))
        if merged:
            previous = merged[-1]
            gap = current["start"] - previous["end"]
            separator = text[previous["end"] : current["start"]]
            if gap in (0, 1) and "\n" not in separator:
                previous_count = int(previous["merged_from"])
                current_count = int(current["merged_from"])
                total_count = previous_count + current_count
                previous["end"] = current["end"]
                previous["text"] = text[previous["start"] : current["end"]]
                previous["score"] = round(
                    (
                        previous_count * float(previous["score"])
                        + current_count * float(current["score"])
                    )
                    / total_count,
                    6,
                )
                previous["merged_from"] = total_count
                continue
        merged.append(current)

    # BENT excludes length-one entities for every type except chemicals.
    return [
        span
        for span in merged
        if len(span["text"]) > 1 and not span["text"].startswith(":")
    ]


class DiseaseSpanExtractor:
    def __init__(
        self,
        model_ref: str,
        device: torch.device,
        batch_size: int,
        stride: int,
        max_length: int | None,
        local_files_only: bool,
    ) -> None:
        log.info("Loading tokenizer and model from %s", model_ref)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_ref, use_fast=True, local_files_only=local_files_only
        )
        if not self.tokenizer.is_fast:
            raise ValueError("A fast tokenizer is required for character offsets")
        self.model = AutoModelForTokenClassification.from_pretrained(
            model_ref, local_files_only=local_files_only
        )
        self.model.eval()
        self.model.to(device)
        self.device = device
        self.batch_size = batch_size
        self.max_length = effective_max_length(
            self.tokenizer, self.model, max_length
        )
        if stride < 0 or stride >= self.max_length - 2:
            raise ValueError(
                f"stride must be between 0 and {self.max_length - 3}, got {stride}"
            )
        self.stride = stride
        id2label = {int(k): str(v) for k, v in self.model.config.id2label.items()}
        self.prefixes = validate_label_schema(id2label)
        log.info(
            "device=%s max_length=%d stride=%d window_batch_size=%d labels=%s",
            device,
            self.max_length,
            stride,
            batch_size,
            id2label,
        )

    def extract_many(self, texts: Sequence[str]) -> list[tuple[list[dict[str, Any]], int]]:
        """Return ``(spans, number_of_windows)`` for every input text."""
        results: list[tuple[list[dict[str, Any]], int] | None] = [None] * len(texts)
        nonempty_indices = [index for index, text in enumerate(texts) if text]
        if not nonempty_indices:
            return [([], 0) for _ in texts]

        nonempty_texts = [texts[index] for index in nonempty_indices]
        encoded = self.tokenizer(
            nonempty_texts,
            truncation=True,
            max_length=self.max_length,
            stride=self.stride,
            return_overflowing_tokens=True,
            return_offsets_mapping=True,
            return_special_tokens_mask=True,
            padding=True,
            return_tensors="pt",
        )
        sample_mapping = encoded.pop("overflow_to_sample_mapping").tolist()
        offsets = encoded.pop("offset_mapping")
        special_tokens = encoded.pop("special_tokens_mask")
        attention_mask = encoded["attention_mask"]

        votes: list[dict[tuple[int, int], tuple[torch.Tensor, int]]] = [
            {} for _ in nonempty_texts
        ]
        window_counts = [0 for _ in nonempty_texts]

        number_of_windows = len(sample_mapping)
        with torch.inference_mode():
            for window_start in range(0, number_of_windows, self.batch_size):
                window_end = min(window_start + self.batch_size, number_of_windows)
                model_inputs = {
                    key: value[window_start:window_end].to(self.device)
                    for key, value in encoded.items()
                    if key in self.tokenizer.model_input_names
                }
                probabilities = torch.softmax(
                    self.model(**model_inputs).logits.float(), dim=-1
                ).cpu()

                for local_window, global_window in enumerate(
                    range(window_start, window_end)
                ):
                    sample_index = sample_mapping[global_window]
                    window_counts[sample_index] += 1
                    for token_index in range(offsets.shape[1]):
                        if not attention_mask[global_window, token_index].item():
                            continue
                        if special_tokens[global_window, token_index].item():
                            continue
                        start, end = offsets[global_window, token_index].tolist()
                        if end <= start:
                            continue
                        key = (int(start), int(end))
                        probability = probabilities[local_window, token_index]
                        previous = votes[sample_index].get(key)
                        if previous is None:
                            votes[sample_index][key] = (probability.clone(), 1)
                        else:
                            probability_sum, count = previous
                            votes[sample_index][key] = (
                                probability_sum + probability,
                                count + 1,
                            )

        for local_index, original_index in enumerate(nonempty_indices):
            spans = decode_spans(
                texts[original_index], votes[local_index], self.prefixes
            )
            results[original_index] = (spans, window_counts[local_index])
        return [result if result is not None else ([], 0) for result in results]


def read_partial(
    partial_path: Path,
    records: Sequence[dict[str, Any]],
    texts: Sequence[str],
    model_name: str,
    model_revision: str | None,
    postprocessing: str,
) -> tuple[int, int]:
    """Validate a partial output and return completed document/span counts."""
    if not partial_path.exists():
        return 0, 0
    completed = list(iter_jsonl(partial_path))
    if len(completed) > len(records):
        raise ValueError(f"Partial output has more records than the input: {partial_path}")
    for index, output_record in enumerate(completed):
        expected_pmid = str(records[index]["pmid"])
        if str(output_record.get("pmid")) != expected_pmid:
            raise ValueError(
                f"Partial output is not an input prefix at record {index + 1}: "
                f"expected PMID {expected_pmid}, got {output_record.get('pmid')}"
            )
        if output_record.get("model") != model_name:
            raise ValueError(
                f"Partial output used model {output_record.get('model')!r}, "
                f"not {model_name!r}"
            )
        if output_record.get("model_revision") != model_revision:
            raise ValueError(
                "Partial output model revision does not match the loaded model: "
                f"{output_record.get('model_revision')!r} != {model_revision!r}"
            )
        if output_record.get("postprocessing") != postprocessing:
            raise ValueError(
                "Partial output post-processing mode does not match this run: "
                f"{output_record.get('postprocessing')!r} != {postprocessing!r}"
            )
        expected_hash = hashlib.sha256(texts[index].encode("utf-8")).hexdigest()
        if output_record.get("text_sha256") != expected_hash:
            raise ValueError(
                f"Input text changed for PMID {expected_pmid}; refusing to resume"
            )
    span_count = sum(len(record.get("spans", [])) for record in completed)
    return len(completed), span_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract disease spans from an abstract JSONL corpus"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Hugging Face model ID, snapshot directory, or models--owner--name cache root",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--text-field",
        choices=("auto", "abstract", "text"),
        default="auto",
        help="Input text field; auto prefers text and falls back to abstract",
    )
    parser.add_argument("--batch-size", type=int, default=16,
                        help="Maximum inference windows per model forward pass")
    parser.add_argument("--stride", type=int, default=128,
                        help="Overlapping tokens between consecutive windows")
    parser.add_argument(
        "--max-length",
        type=int,
        default=None,
        help="Optional lower cap on the tokenizer/model context limit",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="auto, cpu, cuda, or a specific device such as cuda:0",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Forbid Hugging Face network access while loading the model",
    )
    parser.add_argument(
        "--postprocess",
        choices=("none", "bent"),
        default="none",
        help="Optional span correction; bent merges predictions with a 0/1-character gap",
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N records (for smoke checks)")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing final or partial output instead of refusing",
    )
    args = parser.parse_args()
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.max_length is not None and args.max_length < 8:
        parser.error("--max-length must be at least 8")
    return args


def main() -> None:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    partial_path = output_path.with_name(output_path.name + ".partial")
    if not input_path.is_file():
        raise FileNotFoundError(
            f"Input file does not exist: {input_path}. Pass the generated 3200-document "
            "articles.jsonl with --input."
        )
    if input_path in {output_path, partial_path}:
        raise ValueError("Input and output paths must be different")

    if args.overwrite:
        # Keep a valid final output until its replacement finishes successfully.
        partial_path.unlink(missing_ok=True)
    elif output_path.exists():
        raise FileExistsError(
            f"Output already exists: {output_path}. Use a different path or --overwrite."
        )

    records = read_records(input_path, args.limit)
    texts = [record_text(record, args.text_field) for record in records]
    model_ref, revision = resolve_cached_model(args.model)
    model_name = display_model_name(args.model)

    log.info("input=%s records=%d", input_path, len(records))
    device = choose_device(args.device)
    extractor = DiseaseSpanExtractor(
        model_ref=model_ref,
        device=device,
        batch_size=args.batch_size,
        stride=args.stride,
        max_length=args.max_length,
        local_files_only=args.local_files_only,
    )
    revision = revision or getattr(extractor.model.config, "_commit_hash", None)
    completed, span_count = read_partial(
        partial_path, records, texts, model_name, revision, args.postprocess
    )
    if completed:
        log.info("resuming %s after %d completed records", partial_path, completed)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    remaining_records = records[completed:]
    remaining_texts = texts[completed:]
    document_count = completed
    mode = "a" if completed else "w"
    with partial_path.open(mode, encoding="utf-8") as handle:
        progress = tqdm(total=len(records), initial=completed, unit="document")
        for text_batch in batched(remaining_texts, args.batch_size):
            batch_start = document_count
            extracted = extractor.extract_many(text_batch)
            for offset, (spans, num_windows) in enumerate(extracted):
                record = remaining_records[batch_start - completed + offset]
                text = text_batch[offset]
                if args.postprocess == "bent":
                    spans = bent_postprocess_spans(text, spans)
                result = {
                    "pmid": str(record["pmid"]),
                    "model": model_name,
                    "model_revision": revision,
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "num_windows": num_windows,
                    "postprocessing": args.postprocess,
                    "spans": spans,
                }
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                span_count += len(spans)
            handle.flush()
            document_count += len(text_batch)
            progress.update(len(text_batch))
        progress.close()
        os.fsync(handle.fileno())

    os.replace(partial_path, output_path)
    log.info(
        "wrote %d documents and %d disease spans to %s",
        len(records),
        span_count,
        output_path,
    )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        sys.exit(2)
