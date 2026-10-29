#!/usr/bin/env python3
"""Merge disease and pathway Doccano JSONL files by PMID.

The two entity types remain independent labels. Adjacent, nested, partially
overlapping, and exactly coincident spans are preserved without modification.
When importing the result, enable ``Allow overlapping spans`` in the Doccano
Sequence Labeling project or Doccano will discard overlapping annotations.

Input and output records use Doccano's import schema::

    {"text": "...", "label": [[0, 7, "DISEASE"],
                               [20, 30, "PATHWAY"]],
     "meta": {"pmid": "123", ...}}

The output is the PMID union of both inputs. A PMID found in only one input is
kept with that input's labels and produces a warning. A shared PMID must have
identical text because character offsets cannot be transferred across different
texts. Duplicate PMIDs, invalid labels, and shared-PMID text mismatches are fatal.

Compact output metadata retains provenance but omits redundant per-span metadata;
the authoritative spans are already present in the top-level ``label`` list.

Run from the repository root::

    python3 doccano/merge_disease_pathway.py \
        --disease /home/enes/NER-pipeline/data/doccano/disease_4k_bent_doccano.jsonl \
        --pathway /home/enes/NER-pipeline/data/doccano/pathway_4k_doccano.jsonl \
        --output /home/enes/NER-pipeline/data/doccano/disease_pathway_4k_doccano.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DATA_ROOT = Path(
    os.environ.get("NER_PIPELINE_DATA_DIR", "/home/enes/NER-pipeline/data")
).expanduser()
DEFAULT_DISEASE = DATA_ROOT / "doccano/disease_4k_bent_doccano.jsonl"
DEFAULT_PATHWAY = DATA_ROOT / "doccano/pathway_4k_doccano.jsonl"
DEFAULT_OUTPUT = DATA_ROOT / "doccano/disease_pathway_4k_doccano.jsonl"

DISEASE = "DISEASE"
PATHWAY = "PATHWAY"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedRecords:
    order: list[str]
    by_pmid: dict[str, dict[str, Any]]
    label_count: int


def parse_label(
    value: Any,
    *,
    expected_label: str,
    text_length: int,
    path: Path,
    line_number: int,
) -> list[Any]:
    """Validate and normalize one Doccano span label."""
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(
            f"{path}:{line_number}: expected [start, end, label], got {value!r}"
        )
    start, end, label = value
    if isinstance(start, bool) or not isinstance(start, int):
        raise ValueError(f"{path}:{line_number}: invalid start offset {start!r}")
    if isinstance(end, bool) or not isinstance(end, int):
        raise ValueError(f"{path}:{line_number}: invalid end offset {end!r}")
    if label != expected_label:
        raise ValueError(
            f"{path}:{line_number}: expected label {expected_label!r}, got {label!r}"
        )
    if not 0 <= start < end <= text_length:
        raise ValueError(
            f"{path}:{line_number}: offsets [{start}, {end}) are outside text "
            f"length {text_length}"
        )
    return [start, end, label]


def load_doccano(path: Path, expected_label: str) -> LoadedRecords:
    """Load a Doccano JSONL file and validate its PMID and label invariants."""
    order: list[str] = []
    by_pmid: dict[str, dict[str, Any]] = {}
    label_count = 0

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")

            text = record.get("text")
            labels = record.get("label")
            meta = record.get("meta")
            if not isinstance(text, str):
                raise ValueError(f"{path}:{line_number}: 'text' must be a string")
            if not isinstance(labels, list):
                raise ValueError(f"{path}:{line_number}: 'label' must be a list")
            if not isinstance(meta, dict):
                raise ValueError(f"{path}:{line_number}: 'meta' must be an object")

            raw_pmid = meta.get("pmid")
            if raw_pmid is None or not str(raw_pmid).strip():
                raise ValueError(f"{path}:{line_number}: missing meta.pmid")
            pmid = str(raw_pmid)
            if pmid in by_pmid:
                raise ValueError(f"{path}:{line_number}: duplicate PMID {pmid}")

            normalized_labels = [
                parse_label(
                    value,
                    expected_label=expected_label,
                    text_length=len(text),
                    path=path,
                    line_number=line_number,
                )
                for value in labels
            ]
            if len({tuple(label) for label in normalized_labels}) != len(
                normalized_labels
            ):
                raise ValueError(
                    f"{path}:{line_number}: duplicate {expected_label} span for PMID {pmid}"
                )

            normalized = dict(record)
            normalized["label"] = normalized_labels
            normalized["meta"] = dict(meta)
            order.append(pmid)
            by_pmid[pmid] = normalized
            label_count += len(normalized_labels)

    if not order:
        raise ValueError(f"No records found in {path}")
    return LoadedRecords(order=order, by_pmid=by_pmid, label_count=label_count)


def selected_metadata(
    record: dict[str, Any] | None, *, source_path: Path, entity_type: str
) -> dict[str, Any] | None:
    """Return compact, entity-specific provenance for one input record."""
    if record is None:
        return None
    meta = record["meta"]
    if entity_type == DISEASE:
        keys = ("model", "model_revision", "postprocessing")
    else:
        keys = (
            "model",
            "dataset_wave",
            "annotation_status",
            "source",
            "gold",
        )
    compact = {"input_file": source_path.name}
    compact.update({key: meta[key] for key in keys if meta.get(key) is not None})
    return compact


def spans_overlap(first: list[Any], second: list[Any]) -> bool:
    """Return whether two half-open spans share at least one character."""
    return max(first[0], second[0]) < min(first[1], second[1])


def cross_overlap_count(
    disease_labels: Iterable[list[Any]], pathway_labels: Iterable[list[Any]]
) -> int:
    """Count DISEASE-PATHWAY overlap pairs without altering either collection."""
    pathways = list(pathway_labels)
    return sum(
        spans_overlap(disease, pathway)
        for disease in disease_labels
        for pathway in pathways
    )


def merge_records(
    disease: LoadedRecords,
    pathway: LoadedRecords,
    *,
    disease_path: Path,
    pathway_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge both PMID collections while preserving all validated spans."""
    disease_ids = set(disease.by_pmid)
    pathway_ids = set(pathway.by_pmid)
    disease_only = disease_ids - pathway_ids
    pathway_only = pathway_ids - disease_ids

    for pmid in sorted(disease_only):
        log.warning("PMID %s exists only in the disease input; keeping it", pmid)
    for pmid in sorted(pathway_only):
        log.warning("PMID %s exists only in the pathway input; keeping it", pmid)

    output_order = disease.order + [
        pmid for pmid in pathway.order if pmid not in disease_ids
    ]
    merged: list[dict[str, Any]] = []
    overlap_pairs = 0
    overlap_documents = 0
    disease_labels_written = 0
    pathway_labels_written = 0

    for pmid in output_order:
        disease_record = disease.by_pmid.get(pmid)
        pathway_record = pathway.by_pmid.get(pmid)
        if disease_record is not None and pathway_record is not None:
            if disease_record["text"] != pathway_record["text"]:
                raise ValueError(
                    f"PMID {pmid} has different text in {disease_path} and "
                    f"{pathway_path}; offsets cannot be merged safely"
                )
            text = disease_record["text"]
        elif disease_record is not None:
            text = disease_record["text"]
        elif pathway_record is not None:
            text = pathway_record["text"]
        else:  # pragma: no cover - output_order is constructed from both maps.
            raise AssertionError(f"PMID {pmid} has no source record")

        disease_labels = disease_record["label"] if disease_record else []
        pathway_labels = pathway_record["label"] if pathway_record else []
        document_overlap_pairs = cross_overlap_count(
            disease_labels, pathway_labels
        )
        overlap_pairs += document_overlap_pairs
        overlap_documents += document_overlap_pairs > 0

        # Sorting is deterministic presentation only; no spans are merged,
        # deduplicated across entity types, widened, shortened, or discarded.
        labels = sorted(
            [*disease_labels, *pathway_labels],
            key=lambda value: (value[0], value[1], value[2]),
        )
        disease_labels_written += len(disease_labels)
        pathway_labels_written += len(pathway_labels)
        merged.append(
            {
                "text": text,
                "label": labels,
                "meta": {
                    "pmid": pmid,
                    "disease_source": selected_metadata(
                        disease_record,
                        source_path=disease_path,
                        entity_type=DISEASE,
                    ),
                    "pathway_source": selected_metadata(
                        pathway_record,
                        source_path=pathway_path,
                        entity_type=PATHWAY,
                    ),
                },
            }
        )

    stats = {
        "documents": len(merged),
        "shared_pmids": len(disease_ids & pathway_ids),
        "disease_only_pmids": len(disease_only),
        "pathway_only_pmids": len(pathway_only),
        "disease_labels": disease_labels_written,
        "pathway_labels": pathway_labels_written,
        "cross_overlap_pairs": overlap_pairs,
        "cross_overlap_documents": overlap_documents,
    }
    return merged, stats


def write_jsonl_atomic(records: Iterable[dict[str, Any]], output_path: Path) -> None:
    """Write JSONL atomically so a failed run cannot leave partial output."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(output_path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disease",
        type=Path,
        default=DEFAULT_DISEASE,
        help=f"DISEASE Doccano JSONL (default: {DEFAULT_DISEASE})",
    )
    parser.add_argument(
        "--pathway",
        type=Path,
        default=DEFAULT_PATHWAY,
        help=f"PATHWAY Doccano JSONL (default: {DEFAULT_PATHWAY})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"merged Doccano JSONL (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    disease_path = args.disease.expanduser().resolve()
    pathway_path = args.pathway.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if output_path in {disease_path, pathway_path}:
        raise ValueError("Output path must differ from both input paths")

    disease = load_doccano(disease_path, DISEASE)
    pathway = load_doccano(pathway_path, PATHWAY)
    merged, stats = merge_records(
        disease,
        pathway,
        disease_path=disease_path,
        pathway_path=pathway_path,
    )
    write_jsonl_atomic(merged, output_path)

    log.info("wrote %d documents to %s", stats["documents"], output_path)
    log.info(
        "labels: DISEASE=%d PATHWAY=%d total=%d",
        stats["disease_labels"],
        stats["pathway_labels"],
        stats["disease_labels"] + stats["pathway_labels"],
    )
    log.info(
        "PMIDs: shared=%d disease_only=%d pathway_only=%d",
        stats["shared_pmids"],
        stats["disease_only_pmids"],
        stats["pathway_only_pmids"],
    )
    log.info(
        "preserved %d DISEASE-PATHWAY overlap pairs across %d documents",
        stats["cross_overlap_pairs"],
        stats["cross_overlap_documents"],
    )
    if stats["cross_overlap_pairs"]:
        log.info(
            "enable 'Allow overlapping spans' in Doccano before importing this file"
        )


if __name__ == "__main__":
    main()
