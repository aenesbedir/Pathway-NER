#!/usr/bin/env python3
"""Compare one or more NER prediction files with a reference annotation file.

Supported inputs are JSONL, JSON arrays, review JSON objects with a
``documents`` array, and Doccano JSONL. Prediction/reference records may expose
spans as ``spans``, ``detected_pathways``, or Doccano ``label`` entries. Review
documents use the union of ``tp`` and ``fn`` as their reference spans.

The report contains exact-span agreement, lenient overlap agreement,
boundary-only misses, source/match-type reference recall, and frequent
prediction-only/reference-only surface forms. When the reference is silver,
these values measure model-teacher agreement rather than true accuracy.

Example::

    venv310/bin/python3 analysis/score_against_review.py \
        --reference data/silver/pathway_remaining_6125.jsonl \
        --output data/evaluation/pathway_best_vs_qwen_remaining_6125.json \
        data/processed/pathway-ner/pathway_best_remaining_6125.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "analysis/batch_05_5_review.json"


@dataclass(frozen=True)
class Span:
    """A normalized character-offset span with optional provenance."""

    start: int
    end: int
    text: str
    source: str | None = None
    match_type: str | None = None

    @property
    def key(self) -> tuple[int, int]:
        return self.start, self.end


@dataclass
class SpanCollection:
    """An ordered set of documents and their normalized spans."""

    path: Path
    order: list[str]
    by_pmid: dict[str, dict[tuple[int, int], Span]]
    groups: dict[str, str]


def load_json_records(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Return records and whether they came from a review ``documents`` object."""
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
        return records, False

    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if isinstance(value, dict) and isinstance(value.get("documents"), list):
        records = value["documents"]
        review_format = True
    elif isinstance(value, dict) and isinstance(value.get("articles"), list):
        records = value["articles"]
        review_format = False
    elif isinstance(value, list):
        records = value
        review_format = False
    else:
        raise ValueError(
            f"Expected {path} to contain a JSON array, JSONL, or an object "
            "with a 'documents' or 'articles' array"
        )
    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"Expected every record in {path} to be an object")
    return records, review_format


def record_pmid(record: dict[str, Any], *, context: str) -> str:
    """Read a PMID from the top level or compact Doccano metadata."""
    value = record.get("pmid")
    if value is None and isinstance(record.get("meta"), dict):
        value = record["meta"].get("pmid")
    if value is None or not str(value).strip():
        raise ValueError(f"{context} has no PMID")
    return str(value)


def doccano_spans(record: dict[str, Any], label: str) -> list[dict[str, Any]]:
    """Convert Doccano sequence-label entries to ordinary span dictionaries."""
    entries = record.get("label", record.get("labels", []))
    if not isinstance(entries, list):
        raise ValueError("Doccano 'label'/'labels' must be a list")
    text = record.get("text", "")
    if not isinstance(text, str):
        raise ValueError("Doccano 'text' must be a string")
    spans: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, (list, tuple)) and len(entry) >= 3:
            start, end, entry_label = entry[:3]
        elif isinstance(entry, dict):
            start = entry.get("start_offset", entry.get("start"))
            end = entry.get("end_offset", entry.get("end"))
            entry_label = entry.get("label")
        else:
            raise ValueError(f"Unsupported Doccano label entry: {entry!r}")
        if str(entry_label).upper() != label.upper():
            continue
        spans.append({"start": start, "end": end, "text": text[int(start):int(end)]})
    return spans


def raw_spans(
    record: dict[str, Any], *, review_format: bool, label: str
) -> Sequence[dict[str, Any]]:
    """Select a supported span field from a record."""
    if review_format:
        values = list(record.get("tp", [])) + list(record.get("fn", []))
    elif isinstance(record.get("spans"), list):
        values = record["spans"]
    elif isinstance(record.get("detected_pathways"), list):
        values = record["detected_pathways"]
    elif "label" in record or "labels" in record:
        values = doccano_spans(record, label)
    else:
        raise ValueError("Record has no supported span field")
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("Every span must be an object")
    return values


def normalize_span(
    value: dict[str, Any], *, document_text: str, context: str
) -> Span:
    """Validate and normalize a span while retaining silver provenance."""
    try:
        start = int(value["start"])
        end = int(value["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{context} has invalid start/end offsets: {value!r}") from exc
    if start < 0 or end <= start:
        raise ValueError(f"{context} has an invalid interval [{start}, {end})")
    if document_text and end > len(document_text):
        raise ValueError(
            f"{context} ends at {end}, beyond text length {len(document_text)}"
        )
    surface = value.get("text", value.get("surface"))
    if surface is None and document_text:
        surface = document_text[start:end]
    return Span(
        start=start,
        end=end,
        text=str(surface or ""),
        source=str(value["source"]) if value.get("source") is not None else None,
        match_type=(
            str(value["match_type"]) if value.get("match_type") is not None else None
        ),
    )


def load_collection(path: Path, *, label: str, limit: int | None) -> SpanCollection:
    """Load a duplicate-free, PMID-indexed span collection."""
    records, review_format = load_json_records(path)
    if limit is not None:
        records = records[:limit]
    order: list[str] = []
    by_pmid: dict[str, dict[tuple[int, int], Span]] = {}
    groups: dict[str, str] = {}
    for index, record in enumerate(records, 1):
        pmid = record_pmid(record, context=f"{path} record {index}")
        if pmid in by_pmid:
            raise ValueError(f"Duplicate PMID {pmid} in {path}")
        document_text = record.get("text", record.get("abstract", ""))
        if not isinstance(document_text, str):
            raise ValueError(f"Text for PMID {pmid} must be a string")
        normalized: dict[tuple[int, int], Span] = {}
        for span_index, value in enumerate(
            raw_spans(record, review_format=review_format, label=label), 1
        ):
            span = normalize_span(
                value,
                document_text=document_text,
                context=f"{path} PMID {pmid} span {span_index}",
            )
            if span.key in normalized:
                raise ValueError(f"Duplicate span {span.key} for PMID {pmid} in {path}")
            normalized[span.key] = span
        order.append(pmid)
        by_pmid[pmid] = normalized
        doc_index = record.get("doc_index_1based")
        if review_format and isinstance(doc_index, int):
            groups[pmid] = "docs 1-50" if doc_index <= 50 else "docs 51-200"
    if not order:
        raise ValueError(f"{path} contains no records")
    return SpanCollection(path=path, order=order, by_pmid=by_pmid, groups=groups)


def overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    """Return whether two half-open intervals share at least one character."""
    return left[0] < right[1] and right[0] < left[1]


def prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    """Calculate precision, recall, and F1 from span counts."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def score_keys(
    pmids: Iterable[str],
    reference: SpanCollection,
    prediction: SpanCollection,
) -> dict[str, Any]:
    """Calculate exact, overlap, boundary, provenance, and error summaries."""
    exact_tp = exact_fp = exact_fn = 0
    predicted_overlap_hits = reference_overlap_hits = 0
    predicted_total = reference_total = 0
    prediction_boundary_only = reference_boundary_only = 0
    prediction_only: Counter[str] = Counter()
    reference_only: Counter[str] = Counter()
    breakdown: dict[str, dict[str, list[int]]] = {
        "source": defaultdict(lambda: [0, 0, 0]),
        "match_type": defaultdict(lambda: [0, 0, 0]),
    }

    for pmid in pmids:
        ref = reference.by_pmid.get(pmid, {})
        pred = prediction.by_pmid.get(pmid, {})
        ref_keys, pred_keys = set(ref), set(pred)
        exact_tp += len(ref_keys & pred_keys)
        exact_fp += len(pred_keys - ref_keys)
        exact_fn += len(ref_keys - pred_keys)
        predicted_total += len(pred_keys)
        reference_total += len(ref_keys)

        pred_overlap = {
            key for key in pred_keys if any(overlaps(key, other) for other in ref_keys)
        }
        ref_overlap = {
            key for key in ref_keys if any(overlaps(key, other) for other in pred_keys)
        }
        predicted_overlap_hits += len(pred_overlap)
        reference_overlap_hits += len(ref_overlap)
        prediction_boundary_only += len((pred_keys - ref_keys) & pred_overlap)
        reference_boundary_only += len((ref_keys - pred_keys) & ref_overlap)

        for key in pred_keys - ref_keys:
            prediction_only[pred[key].text or f"[{key[0]}, {key[1]})"] += 1
        for key in ref_keys - pred_keys:
            reference_only[ref[key].text or f"[{key[0]}, {key[1]})"] += 1
        for key, span in ref.items():
            for field, value in (("source", span.source), ("match_type", span.match_type)):
                if value is None:
                    continue
                counts = breakdown[field][value]
                counts[0] += 1
                counts[1] += key in pred_keys
                counts[2] += key in ref_overlap

    overlap_precision = (
        predicted_overlap_hits / predicted_total if predicted_total else 0.0
    )
    overlap_recall = reference_overlap_hits / reference_total if reference_total else 0.0
    overlap_f1 = (
        2 * overlap_precision * overlap_recall / (overlap_precision + overlap_recall)
        if overlap_precision + overlap_recall
        else 0.0
    )
    normalized_breakdown: dict[str, dict[str, dict[str, float | int]]] = {}
    for field, values in breakdown.items():
        normalized_breakdown[field] = {}
        for value, (total, exact_hits, overlap_hits) in sorted(values.items()):
            normalized_breakdown[field][value] = {
                "reference_spans": total,
                "exact_hits": exact_hits,
                "exact_recall": exact_hits / total if total else 0.0,
                "overlap_hits": overlap_hits,
                "overlap_recall": overlap_hits / total if total else 0.0,
            }

    return {
        "exact": prf(exact_tp, exact_fp, exact_fn),
        "overlap": {
            "predicted_hits": predicted_overlap_hits,
            "predicted_spans": predicted_total,
            "reference_hits": reference_overlap_hits,
            "reference_spans": reference_total,
            "precision": overlap_precision,
            "recall": overlap_recall,
            "f1": overlap_f1,
        },
        "boundary_only": {
            "prediction_spans": prediction_boundary_only,
            "reference_spans": reference_boundary_only,
        },
        "reference_breakdown": normalized_breakdown,
        "prediction_only_surfaces": prediction_only,
        "reference_only_surfaces": reference_only,
    }


def top_counts(counter: Counter[str], top: int) -> list[dict[str, Any]]:
    """Convert the most frequent counter entries into JSON-safe records."""
    return [{"text": text, "count": count} for text, count in counter.most_common(top)]


def score_run(
    reference: SpanCollection,
    prediction: SpanCollection,
    *,
    allow_pmid_mismatch: bool,
    top: int,
) -> dict[str, Any]:
    """Score one run after validating its document coverage."""
    reference_pmids = set(reference.by_pmid)
    prediction_pmids = set(prediction.by_pmid)
    missing = sorted(reference_pmids - prediction_pmids)
    extra = sorted(prediction_pmids - reference_pmids)
    if (missing or extra) and not allow_pmid_mismatch:
        raise ValueError(
            f"PMID mismatch for {prediction.path}: {len(missing)} missing and "
            f"{len(extra)} extra; pass --allow-pmid-mismatch to score their union"
        )

    all_pmids = list(reference.order)
    all_pmids.extend(pmid for pmid in prediction.order if pmid not in reference_pmids)
    scored = score_keys(all_pmids, reference, prediction)
    errors = {
        "prediction_only_surfaces": top_counts(
            scored.pop("prediction_only_surfaces"), top
        ),
        "reference_only_surfaces": top_counts(scored.pop("reference_only_surfaces"), top),
    }
    groups: dict[str, Any] = {}
    for group in sorted(set(reference.groups.values())):
        group_pmids = [pmid for pmid in reference.order if reference.groups.get(pmid) == group]
        group_score = score_keys(group_pmids, reference, prediction)
        groups[group] = {
            "documents": len(group_pmids),
            "exact": group_score["exact"],
            "overlap": group_score["overlap"],
        }
    return {
        "prediction": str(prediction.path),
        "prediction_documents": len(prediction.by_pmid),
        "prediction_spans": sum(len(spans) for spans in prediction.by_pmid.values()),
        "missing_reference_pmids": missing,
        "extra_prediction_pmids": extra,
        **scored,
        "groups": groups,
        "top_errors": errors,
    }


def write_json_atomic(value: dict[str, Any], output: Path) -> None:
    """Write an indented JSON report without exposing a partial output file."""
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
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def print_result(result: dict[str, Any]) -> None:
    """Print a compact console summary for one prediction run."""
    exact = result["exact"]
    overlap = result["overlap"]
    print(f"\nPrediction: {result['prediction']}")
    print(
        "  Exact   "
        f"P={exact['precision']:.4f} R={exact['recall']:.4f} F1={exact['f1']:.4f} "
        f"(TP={exact['tp']} FP={exact['fp']} FN={exact['fn']})"
    )
    print(
        "  Overlap "
        f"P={overlap['precision']:.4f} R={overlap['recall']:.4f} "
        f"F1={overlap['f1']:.4f}"
    )
    boundary = result["boundary_only"]
    print(
        "  Boundary-only misses: "
        f"prediction={boundary['prediction_spans']} "
        f"reference={boundary['reference_spans']}"
    )
    if result["missing_reference_pmids"] or result["extra_prediction_pmids"]:
        print(
            "  PMID mismatch: "
            f"missing={len(result['missing_reference_pmids'])} "
            f"extra={len(result['extra_prediction_pmids'])}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="prediction JSON/JSONL files")
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE,
        help=f"reference JSON/JSONL file (default: {DEFAULT_REFERENCE})",
    )
    parser.add_argument(
        "--label",
        default="PATHWAY",
        help="Doccano label to score when an input contains label lists",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--output", type=Path, default=None, help="optional JSON report")
    parser.add_argument(
        "--allow-pmid-mismatch",
        action="store_true",
        help="score the PMID union, counting missing documents as empty",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.top < 0:
        parser.error("--top cannot be negative")
    return args


def main() -> None:
    args = parse_args()
    reference_path = args.reference.expanduser().resolve()
    reference = load_collection(reference_path, label=args.label, limit=args.limit)
    reference_pmids = set(reference.by_pmid)
    reference_spans = sum(len(spans) for spans in reference.by_pmid.values())
    print(f"Reference : {reference.path}")
    print(f"Documents : {len(reference.by_pmid)}")
    print(f"Spans     : {reference_spans}")
    print("Interpretation: agreement with the supplied reference labels")

    results: list[dict[str, Any]] = []
    for run in args.runs:
        prediction = load_collection(
            run.expanduser().resolve(), label=args.label, limit=None
        )
        if args.limit is not None:
            prediction.order = [pmid for pmid in prediction.order if pmid in reference_pmids]
            prediction.by_pmid = {
                pmid: prediction.by_pmid[pmid] for pmid in prediction.order
            }
        result = score_run(
            reference,
            prediction,
            allow_pmid_mismatch=args.allow_pmid_mismatch,
            top=args.top,
        )
        results.append(result)
        print_result(result)

    report = {
        "reference": str(reference.path),
        "reference_role": (
            "Reference labels are treated as authoritative; when they are silver, "
            "the results measure agreement rather than true accuracy."
        ),
        "label": args.label,
        "reference_documents": len(reference.by_pmid),
        "reference_spans": reference_spans,
        "runs": results,
    }
    if args.output is not None:
        output = args.output.expanduser().resolve()
        if output in {reference.path, *(Path(run["prediction"]) for run in results)}:
            raise ValueError("Report output must differ from every input path")
        write_json_atomic(report, output)
        print(f"\nReport    : {output}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
