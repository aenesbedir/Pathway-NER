#!/usr/bin/env python3
"""Export pathway or disease span records to Doccano JSONL.

Both the span input and article corpus may be JSONL, a JSON array, or a JSON
object containing an ``articles`` array. The span input must contain one record
per PMID and a ``spans`` list. Article text is resolved by PMID and emitted in
Doccano's sequence-labeling import schema::

    {"text": "...", "label": [[0, 7, "DISEASE"]], "meta": {...}}

Character offsets are validated against the exact article text. Missing PMIDs,
duplicate PMIDs/spans, malformed intervals, and surface mismatches are fatal so
the exporter cannot silently discard annotations.

Examples::

    python3 doccano/export_doccano.py \
        --input data/silver/pathway_remaining_6125.jsonl \
        --articles data/processed/disease-ner/articles_remaining_6125.jsonl \
        --label PATHWAY \
        --output data/doccano/pathway_remaining_6125_doccano.jsonl

    python3 doccano/export_doccano.py \
        --input data/processed/disease-ner/disease_spans_remaining_6125_bent.jsonl \
        --articles data/processed/disease-ner/articles_remaining_6125.jsonl \
        --label DISEASE \
        --output data/doccano/disease_remaining_6125_bent_doccano.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/silver/pilot_1k.jsonl"
DEFAULT_ARTICLES = ROOT / "data/raw/articles.json"
DEFAULT_OUTPUT = ROOT / "doccano/pilot_1k_doccano.jsonl"
SUPPORTED_LABELS = ("PATHWAY", "DISEASE")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load JSONL, a JSON array, or an object containing ``articles``."""
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
            f"Expected {path} to contain a JSON array of objects, JSONL, or "
            "an object with an 'articles' array"
        )
    return value


def record_pmid(record: dict[str, Any], *, context: str) -> str:
    """Read and normalize a PMID from a record."""
    value = record.get("pmid")
    if value is None and isinstance(record.get("meta"), dict):
        value = record["meta"].get("pmid")
    if value is None or not str(value).strip():
        raise ValueError(f"{context} has no PMID")
    return str(value)


def article_text(record: dict[str, Any], *, context: str) -> str:
    """Read exact sequence-labeling text without changing character offsets."""
    value = record.get("text")
    if value is None:
        value = record.get("abstract")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{context} has a non-string text/abstract field")
    return value


def index_articles(path: Path) -> dict[str, str]:
    """Build a duplicate-free PMID-to-text lookup."""
    indexed: dict[str, str] = {}
    for index, record in enumerate(load_records(path), 1):
        pmid = record_pmid(record, context=f"{path} article {index}")
        if pmid in indexed:
            raise ValueError(f"Duplicate PMID {pmid} in {path}")
        indexed[pmid] = article_text(record, context=f"{path} PMID {pmid}")
    if not indexed:
        raise ValueError(f"Article corpus is empty: {path}")
    return indexed


def compact_metadata(record: dict[str, Any], pmid: str, label: str) -> dict[str, Any]:
    """Retain document-level provenance without duplicating the span list."""
    metadata: dict[str, Any] = {"pmid": pmid, "entity_type": label}
    for key in (
        "model",
        "model_revision",
        "postprocessing",
        "dataset_wave",
        "annotation_status",
        "source",
        "gold",
    ):
        if record.get(key) is not None:
            metadata[key] = record[key]
    return metadata


def to_doccano(
    record: dict[str, Any],
    text: str,
    *,
    pmid: str,
    label: str,
    context: str,
) -> dict[str, Any]:
    """Validate one span record and convert it to Doccano import format."""
    raw_spans = record.get("spans")
    if not isinstance(raw_spans, list):
        raise ValueError(f"{context} has no 'spans' list")

    labels: list[list[Any]] = []
    seen: set[tuple[int, int]] = set()
    for span_index, span in enumerate(raw_spans, 1):
        if not isinstance(span, dict):
            raise ValueError(f"{context} span {span_index} is not an object")
        try:
            start = int(span["start"])
            end = int(span["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{context} span {span_index} has invalid start/end offsets"
            ) from exc
        if not 0 <= start < end <= len(text):
            raise ValueError(
                f"{context} span {span_index} [{start}, {end}) is outside text "
                f"length {len(text)}"
            )
        surface = span.get("text", span.get("surface"))
        if not isinstance(surface, str):
            raise ValueError(f"{context} span {span_index} has no string surface")
        actual = text[start:end]
        if actual != surface:
            raise ValueError(
                f"{context} span {span_index} surface mismatch: "
                f"expected {surface!r}, found {actual!r}"
            )
        key = (start, end)
        if key in seen:
            raise ValueError(f"{context} has duplicate span [{start}, {end})")
        seen.add(key)
        labels.append([start, end, label])

    labels.sort(key=lambda value: (value[0], value[1], value[2]))
    return {
        "text": text,
        "label": labels,
        "meta": compact_metadata(record, pmid, label),
    }


def write_jsonl_atomic(records: Iterable[dict[str, Any]], output: Path) -> None:
    """Write JSONL atomically so failures cannot leave a partial final file."""
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
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES)
    parser.add_argument("--label", choices=SUPPORTED_LABELS, default="PATHWAY")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


def main() -> None:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    articles_path = args.articles.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if output_path in {input_path, articles_path}:
        raise ValueError("Output must differ from both input paths")
    if output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Pass --overwrite to replace it."
        )

    records = load_records(input_path)
    if args.limit is not None:
        records = records[: args.limit]
    if not records:
        raise ValueError(f"Span input is empty: {input_path}")
    articles = index_articles(articles_path)

    output_records: list[dict[str, Any]] = []
    seen_pmids: set[str] = set()
    label_count = 0
    positive_documents = 0
    for index, record in enumerate(records, 1):
        pmid = record_pmid(record, context=f"{input_path} record {index}")
        if pmid in seen_pmids:
            raise ValueError(f"Duplicate PMID {pmid} in {input_path}")
        seen_pmids.add(pmid)
        if pmid not in articles:
            raise ValueError(f"PMID {pmid} is absent from {articles_path}")
        converted = to_doccano(
            record,
            articles[pmid],
            pmid=pmid,
            label=args.label,
            context=f"{input_path} PMID {pmid}",
        )
        label_count += len(converted["label"])
        positive_documents += bool(converted["label"])
        output_records.append(converted)

    write_jsonl_atomic(output_records, output_path)
    log.info("output=%s", output_path)
    log.info(
        "documents=%d positive_documents=%d labels=%d label_type=%s",
        len(output_records),
        positive_documents,
        label_count,
        args.label,
    )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, FileExistsError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
