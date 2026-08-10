#!/usr/bin/env python3
"""Build a human-review file from independent NER source disagreements.

The primary annotations are a merged Doccano JSONL containing DISEASE and
PATHWAY labels. Disease and pathway reviewer JSONL files must contain spans for
the same PMIDs. Exact agreement is accepted; one-to-one overlaps with different
boundaries become correction candidates; multi-span overlap components become
uncertain candidates; and non-overlapping spans become possible false positives
or false negatives.

This output is review evidence, not automatically corrected gold data. Every
disagreement is explicitly marked as requiring a human decision.

Example::

    python3 analysis/build_disagreement_review.py \
        --annotations /home/enes/NER-pipeline/data/doccano/disease_pathway_remaining_6125_doccano.jsonl \
        --disease-primary-evidence /home/enes/NER-pipeline/data/processed/disease-ner/disease_spans_remaining_6125_bent.jsonl \
        --disease-reviewer /home/enes/NER-pipeline/data/processed/disease-ner/pubtator_disease_remaining_6125.jsonl \
        --pathway-reviewer /home/enes/NER-pipeline/data/processed/pathway-ner/pathway_best_remaining_6125.jsonl \
        --output /home/enes/NER-pipeline/data/reviews/disease_pathway_remaining_6125_review_candidates.jsonl \
        --include-accepted
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable, Sequence


ENTITY_TYPES = ("DISEASE", "PATHWAY")
CATEGORIES = (
    "accepted",
    "false_positives",
    "false_negatives",
    "corrections",
    "uncertain",
    "unreviewed",
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load non-empty JSONL objects with contextual errors."""
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    records: list[dict[str, Any]] = []
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
            records.append(record)
    if not records:
        raise ValueError(f"No records found in {path}")
    return records


def record_pmid(record: dict[str, Any], *, context: str) -> str:
    """Read a PMID from the top level or compact Doccano metadata."""
    value = record.get("pmid")
    if value is None and isinstance(record.get("meta"), dict):
        value = record["meta"].get("pmid")
    if value is None or not str(value).strip():
        raise ValueError(f"{context} has no PMID")
    return str(value)


def text_sha256(text: str) -> str:
    """Hash exact source text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_annotations(
    record: dict[str, Any], *, context: str
) -> tuple[str, str, dict[str, list[dict[str, Any]]]]:
    """Validate one merged Doccano record and assign stable entity IDs."""
    pmid = record_pmid(record, context=context)
    text = record.get("text")
    labels = record.get("label", record.get("labels"))
    if not isinstance(text, str) or not isinstance(labels, list):
        raise ValueError(f"{context} must contain string text and list labels")
    spans = {entity_type: [] for entity_type in ENTITY_TYPES}
    counts = Counter()
    seen: set[tuple[int, int, str]] = set()
    for index, value in enumerate(labels, 1):
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError(f"{context} label {index} is not [start, end, type]")
        start, end, entity_type = value
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"{context} label {index} has unknown type {entity_type!r}")
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or not 0 <= start < end <= len(text)
        ):
            raise ValueError(f"{context} label {index} has invalid offsets")
        key = (start, end, entity_type)
        if key in seen:
            raise ValueError(f"{context} has duplicate label {key}")
        seen.add(key)
        counts[entity_type] += 1
        prefix = "D" if entity_type == "DISEASE" else "P"
        spans[entity_type].append(
            {
                "source_id": f"{prefix}{counts[entity_type]:04d}",
                "start": start,
                "end": end,
                "text": text[start:end],
                "label": entity_type,
            }
        )
    return pmid, text, spans


def normalize_reviewer(
    record: dict[str, Any],
    *,
    entity_type: str,
    pmid: str,
    text: str,
    context: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Validate reviewer status, text hash, offsets, and duplicate spans."""
    reviewer_pmid = record_pmid(record, context=context)
    if reviewer_pmid != pmid:
        raise ValueError(f"{context} PMID {reviewer_pmid} does not match {pmid}")
    expected_hash = record.get("text_sha256")
    if expected_hash is not None and expected_hash != text_sha256(text):
        raise ValueError(f"{context} text hash does not match PMID {pmid}")
    status = str(record.get("status", "ok"))
    values = record.get("spans")
    if not isinstance(values, list):
        raise ValueError(f"{context} spans must be a list")
    spans: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            raise ValueError(f"{context} span {index} is not an object")
        start = value.get("start")
        end = value.get("end")
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or not 0 <= start < end <= len(text)
        ):
            raise ValueError(f"{context} span {index} has invalid offsets")
        key = (start, end)
        if key in seen:
            raise ValueError(f"{context} contains duplicate span {key}")
        seen.add(key)
        surface = text[start:end]
        reported_surface = value.get("text", value.get("surface"))
        if reported_surface is not None and reported_surface != surface:
            raise ValueError(f"{context} span {index} text does not match offsets")
        evidence = {
            key: value[key]
            for key in (
                "score",
                "identifier",
                "normalized_name",
                "alignment_method",
                "pubtator_text",
                "model",
                "source",
            )
            if value.get(key) is not None
        }
        spans.append(
            {
                "start": start,
                "end": end,
                "text": surface,
                "label": entity_type,
                "evidence": evidence,
            }
        )
    return status, spans


def overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return whether two half-open spans share at least one character."""
    return left["start"] < right["end"] and right["start"] < left["end"]


def span_fields(span: dict[str, Any]) -> dict[str, Any]:
    """Copy stable public span fields."""
    return {
        key: span[key]
        for key in ("start", "end", "text", "label")
        if key in span
    }


def overlap_components(
    primary: Sequence[dict[str, Any]],
    reviewer: Sequence[dict[str, Any]],
) -> list[tuple[list[int], list[int]]]:
    """Return connected bipartite components containing at least one overlap."""
    primary_edges: dict[int, set[int]] = {index: set() for index in range(len(primary))}
    reviewer_edges: dict[int, set[int]] = {index: set() for index in range(len(reviewer))}
    for primary_index, primary_span in enumerate(primary):
        for reviewer_index, reviewer_span in enumerate(reviewer):
            if overlaps(primary_span, reviewer_span):
                primary_edges[primary_index].add(reviewer_index)
                reviewer_edges[reviewer_index].add(primary_index)

    components: list[tuple[list[int], list[int]]] = []
    visited_primary: set[int] = set()
    visited_reviewer: set[int] = set()
    for seed in range(len(primary)):
        if seed in visited_primary or not primary_edges[seed]:
            continue
        queue: deque[tuple[str, int]] = deque([("primary", seed)])
        component_primary: set[int] = set()
        component_reviewer: set[int] = set()
        while queue:
            side, index = queue.popleft()
            if side == "primary":
                if index in visited_primary:
                    continue
                visited_primary.add(index)
                component_primary.add(index)
                queue.extend(("reviewer", value) for value in primary_edges[index])
            else:
                if index in visited_reviewer:
                    continue
                visited_reviewer.add(index)
                component_reviewer.add(index)
                queue.extend(("primary", value) for value in reviewer_edges[index])
        components.append(
            (sorted(component_primary), sorted(component_reviewer))
        )
    return components


def compare_entity(
    primary: Sequence[dict[str, Any]],
    reviewer: Sequence[dict[str, Any]],
    *,
    entity_type: str,
    reviewer_name: str,
    reviewer_status: str,
    include_accepted: bool,
) -> dict[str, Any]:
    """Classify exact, boundary, ambiguous, and unmatched cross-source spans."""
    result: dict[str, Any] = {category: [] for category in CATEGORIES}
    if reviewer_status != "ok":
        result["unreviewed"] = [
            {
                **span,
                "reason": f"{reviewer_name} had no usable abstract annotations.",
                "review_decision_required": True,
            }
            for span in primary
        ]
        return result

    primary_by_key = {(span["start"], span["end"]): span for span in primary}
    reviewer_by_key = {(span["start"], span["end"]): span for span in reviewer}
    exact_keys = set(primary_by_key) & set(reviewer_by_key)
    if include_accepted:
        for key in sorted(exact_keys):
            span = primary_by_key[key]
            result["accepted"].append(
                {
                    **span,
                    "agreement": "exact",
                    "reviewer": reviewer_name,
                }
            )

    primary_remaining = [
        span for span in primary if (span["start"], span["end"]) not in exact_keys
    ]
    reviewer_remaining = [
        span for span in reviewer if (span["start"], span["end"]) not in exact_keys
    ]
    covered_primary: set[int] = set()
    covered_reviewer: set[int] = set()
    for primary_indices, reviewer_indices in overlap_components(
        primary_remaining, reviewer_remaining
    ):
        covered_primary.update(primary_indices)
        covered_reviewer.update(reviewer_indices)
        if len(primary_indices) == 1 and len(reviewer_indices) == 1:
            original = primary_remaining[primary_indices[0]]
            suggested = reviewer_remaining[reviewer_indices[0]]
            result["corrections"].append(
                {
                    "source_id": original["source_id"],
                    "original": span_fields(original),
                    "suggested": span_fields(suggested),
                    "reason": (
                        f"The current annotation and {reviewer_name} overlap but "
                        "disagree on exact boundaries."
                    ),
                    "confidence": "medium",
                    "review_decision_required": True,
                    "primary_evidence": original.get("evidence", {}),
                    "reviewer_evidence": suggested.get("evidence", {}),
                }
            )
            continue
        result["uncertain"].append(
            {
                "current": [
                    primary_remaining[index] for index in primary_indices
                ],
                "reviewer_suggestions": [
                    reviewer_remaining[index] for index in reviewer_indices
                ],
                "reason": (
                    f"The current annotations and {reviewer_name} form a "
                    "multi-span overlap that cannot be resolved one-to-one."
                ),
                "confidence": "low",
                "review_decision_required": True,
            }
        )

    disagreement_confidence = "medium" if entity_type == "PATHWAY" else "low"
    for index, span in enumerate(primary_remaining):
        if index in covered_primary:
            continue
        confidence = disagreement_confidence
        primary_score = span.get("evidence", {}).get("score")
        if (
            entity_type == "DISEASE"
            and isinstance(primary_score, (int, float))
            and primary_score < 0.75
        ):
            confidence = "medium"
        result["false_positives"].append(
            {
                **span,
                "reason": (
                    f"{reviewer_name} produced no overlapping {entity_type} span."
                ),
                "confidence": confidence,
                "review_decision_required": True,
            }
        )
    for index, span in enumerate(reviewer_remaining):
        if index in covered_reviewer:
            continue
        result["false_negatives"].append(
            {
                **span_fields(span),
                "reason": (
                    f"{reviewer_name} produced this {entity_type} span with no "
                    "overlap in the current annotations."
                ),
                "confidence": disagreement_confidence,
                "review_decision_required": True,
                "reviewer_evidence": span.get("evidence", {}),
            }
        )
    represented_primary = (
        len(exact_keys)
        + len(result["false_positives"])
        + len(result["corrections"])
        + sum(len(component["current"]) for component in result["uncertain"])
    )
    represented_reviewer = (
        len(exact_keys)
        + len(result["false_negatives"])
        + len(result["corrections"])
        + sum(
            len(component["reviewer_suggestions"])
            for component in result["uncertain"]
        )
    )
    if represented_primary != len(primary) or represented_reviewer != len(reviewer):
        raise ValueError(
            f"{entity_type} comparison did not partition every source span"
        )
    return result


def atomic_jsonl_dump(records: Iterable[dict[str, Any]], path: Path) -> None:
    """Write ordered review records atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def atomic_json_dump(value: dict[str, Any], path: Path) -> None:
    """Write a JSON summary atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--disease-primary-evidence", type=Path, default=None)
    parser.add_argument("--disease-reviewer", type=Path, required=True)
    parser.add_argument("--pathway-reviewer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-accepted", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


def main() -> None:
    args = parse_args()
    annotation_path = args.annotations.expanduser().resolve()
    disease_primary_path = (
        args.disease_primary_evidence.expanduser().resolve()
        if args.disease_primary_evidence is not None
        else None
    )
    disease_path = args.disease_reviewer.expanduser().resolve()
    pathway_path = args.pathway_reviewer.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    summary_path = (
        args.summary_output.expanduser().resolve()
        if args.summary_output is not None
        else output_path.with_suffix(".summary.json")
    )
    for path in (output_path, summary_path):
        if path.exists() and not args.overwrite:
            raise FileExistsError(
                f"Output already exists: {path}. Pass --overwrite to replace it."
            )

    annotations = load_jsonl(annotation_path)
    disease_primary_records = (
        load_jsonl(disease_primary_path) if disease_primary_path is not None else None
    )
    disease_records = load_jsonl(disease_path)
    pathway_records = load_jsonl(pathway_path)
    if args.limit is not None:
        annotations = annotations[: args.limit]
        if disease_primary_records is not None:
            disease_primary_records = disease_primary_records[: args.limit]
        disease_records = disease_records[: args.limit]
        pathway_records = pathway_records[: args.limit]
    if not len(annotations) == len(disease_records) == len(pathway_records):
        raise ValueError(
            "Annotation and reviewer files must contain the same number of records"
        )
    if disease_primary_records is not None and len(disease_primary_records) != len(
        annotations
    ):
        raise ValueError(
            "Disease primary evidence must contain the same number of records"
        )

    reviews: list[dict[str, Any]] = []
    totals = Counter()
    candidate_documents = Counter()
    span_partitions = {entity: Counter() for entity in ("disease", "pathway")}
    confidence_counts = Counter()
    reviewer_status_counts = {
        entity: Counter() for entity in ("disease", "pathway")
    }
    disease_alignment_methods = Counter()
    disease_alignment_failures = 0
    disease_text_mismatches = 0
    for index, (annotation, disease_record, pathway_record) in enumerate(
        zip(annotations, disease_records, pathway_records), 1
    ):
        pmid, text, primary = normalize_annotations(
            annotation, context=f"{annotation_path}:{index}"
        )
        disease_primary_record = (
            disease_primary_records[index - 1]
            if disease_primary_records is not None
            else None
        )
        if disease_primary_record is not None:
            _, evidence_spans = normalize_reviewer(
                disease_primary_record,
                entity_type="DISEASE",
                pmid=pmid,
                text=text,
                context=f"{disease_primary_path}:{index}",
            )
            evidence_by_key = {
                (span["start"], span["end"]): span.get("evidence", {})
                for span in evidence_spans
            }
            primary_keys = {
                (span["start"], span["end"]) for span in primary["DISEASE"]
            }
            if primary_keys != set(evidence_by_key):
                raise ValueError(
                    f"PMID {pmid} disease primary evidence does not match "
                    "the Doccano disease labels"
                )
            for span in primary["DISEASE"]:
                span["evidence"] = evidence_by_key[(span["start"], span["end"])]
        disease_status, disease_reviewer = normalize_reviewer(
            disease_record,
            entity_type="DISEASE",
            pmid=pmid,
            text=text,
            context=f"{disease_path}:{index}",
        )
        pathway_status, pathway_reviewer = normalize_reviewer(
            pathway_record,
            entity_type="PATHWAY",
            pmid=pmid,
            text=text,
            context=f"{pathway_path}:{index}",
        )
        reviewer_status_counts["disease"][disease_status] += 1
        reviewer_status_counts["pathway"][pathway_status] += 1
        for span in disease_record["spans"]:
            disease_alignment_methods[str(span.get("alignment_method", "unknown"))] += 1
        disease_alignment_failures += len(
            disease_record.get("alignment_failures", [])
        )
        disease_text_mismatches += (
            disease_status == "ok"
            and not disease_record.get("abstract_text_exact_match", False)
        )
        disease = compare_entity(
            primary["DISEASE"],
            disease_reviewer,
            entity_type="DISEASE",
            reviewer_name="NCBI PubTator",
            reviewer_status=disease_status,
            include_accepted=args.include_accepted,
        )
        pathway = compare_entity(
            primary["PATHWAY"],
            pathway_reviewer,
            entity_type="PATHWAY",
            reviewer_name="gold-trained pathway checkpoint",
            reviewer_status=pathway_status,
            include_accepted=args.include_accepted,
        )
        for name, section in (("disease", disease), ("pathway", pathway)):
            has_candidates = False
            for category in CATEGORIES:
                count = len(section[category])
                totals[f"{name}.{category}"] += count
                if category != "accepted" and count:
                    has_candidates = True
                for item in section[category]:
                    confidence = item.get("confidence")
                    if confidence is not None:
                        confidence_counts[f"{name}.{category}.{confidence}"] += 1
            candidate_documents[name] += has_candidates
            label = "DISEASE" if name == "disease" else "PATHWAY"
            reviewer_values = (
                disease_reviewer if name == "disease" else pathway_reviewer
            )
            current_keys = {
                (span["start"], span["end"]) for span in primary[label]
            }
            reviewer_keys = {
                (span["start"], span["end"]) for span in reviewer_values
            }
            span_partitions[name]["exact_agreements"] += len(
                current_keys & reviewer_keys
            )
            span_partitions[name]["one_to_one_boundary_disagreements"] += len(
                section["corrections"]
            )
            span_partitions[name]["current_only_candidates"] += len(
                section["false_positives"]
            )
            span_partitions[name]["reviewer_only_candidates"] += len(
                section["false_negatives"]
            )
            span_partitions[name]["ambiguous_components"] += len(
                section["uncertain"]
            )
            span_partitions[name]["ambiguous_current_spans"] += sum(
                len(component["current"]) for component in section["uncertain"]
            )
            span_partitions[name]["ambiguous_reviewer_spans"] += sum(
                len(component["reviewer_suggestions"])
                for component in section["uncertain"]
            )
            span_partitions[name]["unreviewed_current_spans"] += len(
                section["unreviewed"]
            )
        span_partitions["disease"]["current_total"] += len(primary["DISEASE"])
        span_partitions["disease"]["reviewer_total"] += len(disease_reviewer)
        span_partitions["pathway"]["current_total"] += len(primary["PATHWAY"])
        span_partitions["pathway"]["reviewer_total"] += len(pathway_reviewer)
        reviews.append(
            {
                "doc_index_1based": index,
                "pmid": pmid,
                "text": text,
                "text_sha256": text_sha256(text),
                "review_kind": "independent_source_disagreement_candidates",
                "review_status": "requires_human_adjudication",
                "sources": {
                    "annotations": str(annotation_path),
                    "disease_primary_evidence": (
                        str(disease_primary_path)
                        if disease_primary_path is not None
                        else None
                    ),
                    "disease_reviewer": str(disease_path),
                    "pathway_reviewer": str(pathway_path),
                },
                "machine_span_count": {
                    "DISEASE": len(primary["DISEASE"]),
                    "PATHWAY": len(primary["PATHWAY"]),
                },
                "reviewer_span_count": {
                    "DISEASE": len(disease_reviewer),
                    "PATHWAY": len(pathway_reviewer),
                },
                "reviewer_details": {
                    "DISEASE": {
                        "name": "NCBI PubTator",
                        "status": disease_status,
                        "source": disease_record.get("source"),
                        "source_url": disease_record.get("source_url"),
                    },
                    "PATHWAY": {
                        "name": "gold-trained pathway checkpoint",
                        "status": pathway_status,
                        "model": pathway_record.get("model"),
                    },
                },
                "disease": disease,
                "pathway": pathway,
            }
        )

    summary = {
        "review_kind": "independent_source_disagreement_candidates",
        "warning": (
            "Disagreements are candidates for human adjudication, not automatic "
            "false-positive or false-negative decisions."
        ),
        "documents": len(reviews),
        "include_accepted": args.include_accepted,
        "documents_with_candidates": dict(candidate_documents),
        "counts": dict(sorted(totals.items())),
        "span_partitions": {
            entity: dict(sorted(counts.items()))
            for entity, counts in span_partitions.items()
        },
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "reviewer_quality": {
            "disease": {
                "document_status": dict(reviewer_status_counts["disease"]),
                "abstract_text_mismatches_aligned": disease_text_mismatches,
                "alignment_methods": dict(sorted(disease_alignment_methods.items())),
                "alignment_failures_skipped": disease_alignment_failures,
            },
            "pathway": {
                "document_status": dict(reviewer_status_counts["pathway"]),
            },
        },
        "sources": {
            "annotations": str(annotation_path),
            "disease_primary_evidence": (
                str(disease_primary_path)
                if disease_primary_path is not None
                else None
            ),
            "disease_reviewer": str(disease_path),
            "pathway_reviewer": str(pathway_path),
        },
    }
    atomic_jsonl_dump(reviews, output_path)
    atomic_json_dump(summary, summary_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Review JSONL: {output_path}")
    print(f"Summary JSON: {summary_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        FileExistsError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
