#!/usr/bin/env python3
"""Curate flat disagreement decisions without modifying Doccano annotations.

The input inspection file contains one proposed decision per simple false-positive
or false-negative candidate. This script validates every candidate against the
source Doccano JSONL, applies the project's entity policies, and writes a separate
row-level decision file. Ambiguous proposals are explicitly deferred instead of
being treated as safe annotation edits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ENTITY_TYPES = {"DISEASE", "PATHWAY"}
FINAL_DECISIONS = {
    "false_positive": {"keep", "remove", "defer"},
    "false_negative": {"add", "reject", "defer"},
}
ACTION_BY_DECISION = {
    "add": "add_span",
    "remove": "remove_span",
    "keep": "none",
    "reject": "none",
    "defer": "defer",
}

SAFE_DISEASE_EXCLUSION_RULES = {
    "DIS-ANATOMY",
    "DIS-CELLLINE",
    "DIS-GENE",
    "DIS-GENERIC-HEAD",
    "DIS-MODIFIER",
    "DIS-NONENTITY",
    "DIS-NOTADISEASE",
    "DIS-ORGANISM",
    "DIS-PROCESS",
    "DIS-STATE-ADJ",
    "FRAG-COORD",
    "FRAG-CUT",
    "FRAG-STOP",
}
SAFE_PATHWAY_EXCLUSION_RULES = {
    "FRAG-COORD",
    "FRAG-CUT",
    "FRAG-STOP",
    "PW-COMPARTMENT",
    "PW-COMPOUND",
    "PW-DISEASE",
    "PW-ENZYME",
    "PW-FRAG-MODIFIER",
    "PW-NONMETABOLIC",
    "PW-SIGNALLING",
    "PW-STATE",
}
RISKY_DISEASE_RULES = {
    "DIS-NONE",
    "DIS-ORGAN-PATHOLOGY",
    "DIS-SYMPTOM",
    "DIS-SYMPTOM-HEAD",
    "LEX-ACCEPTED",
}

DISEASE_HEAD_RE = re.compile(
    r"\b(?:"
    r"diseases?|disorders?|syndromes?|cancers?|tumou?rs?|carcinomas?|"
    r"adenocarcinomas?|sarcomas?|leuk(?:a|e)mias?|lymphomas?|melanomas?|"
    r"myelomas?|gliomas?|blastomas?|adenomas?|diabetes|obesity|hypertension|"
    r"fibrosis|cirrhosis|steatosis|atherosclerosis|epilepsy|schizophrenia|"
    r"depression|infections?|deficienc(?:y|ies)|sepsis|ischemias?|infarctions?|"
    r"strokes?|neuropath(?:y|ies)|nephropath(?:y|ies)|retinopath(?:y|ies)|"
    r"encephalopath(?:y|ies)|cardiomyopath(?:y|ies)|arthritis|asthma|pneumonia|"
    r"hepatitis|nephritis|colitis|dermatitis|pancreatitis|endometriosis|covid-19"
    r")\b",
    re.IGNORECASE,
)
GENERIC_DISEASE_SURFACES = {
    "abnormality",
    "abnormalities",
    "cancer",
    "cancers",
    "condition",
    "conditions",
    "deficiency",
    "disease",
    "diseases",
    "disorder",
    "disorders",
    "syndrome",
    "syndromes",
    "tumor",
    "tumors",
    "tumour",
    "tumours",
}
DISEASE_ADJECTIVE_SURFACES = {
    "atherosclerotic",
    "autistic",
    "cancerous",
    "cirrhotic",
    "diabetic",
    "fibrotic",
    "hyperlipidemic",
    "hypertensive",
    "inflammatory",
    "ischemic",
    "leukemic",
    "metastatic",
    "neurodegenerative",
    "neurotoxic",
    "obese",
    "overweight",
    "proinflammatory",
    "psychotic",
    "toxic",
}
DISEASE_POLICY_REJECT_SURFACES = {
    "inflammatory",
    "metastases",
    "metastasis",
    "proinflammatory",
}
PATHWAY_EXCLUDED_PROCESS_RE = re.compile(
    r"\b(?:"
    r"electron(?:ic)?\s+transport|transport(?:er|ers|ation)?|uptake|efflux|"
    r"secretion|translocation|import(?:ation)?|export(?:ation)?|"
    r"signali[sz](?:ing|ation)"
    r")\b",
    re.IGNORECASE,
)

UNSAFE_PUBTATOR_ALIGNMENT_PMIDS = {
    "36669126",
    "39490674",
    "39496388",
    "42066955",
}
NESTED_REVIEWER_DUPLICATES = {
    ("42066955", "DISEASE", 1610, 1617),
    ("36669126", "DISEASE", 181, 187),
    ("25525878", "DISEASE", 839, 850),
    ("41397566", "DISEASE", 225, 233),
}
KNOWN_CONTEXT_OVERRIDES = {
    ("23956011", "DISEASE", 244, 247): (
        "remove",
        "BPH means brown planthopper in this article, not benign prostatic hyperplasia.",
    ),
    ("23956011", "DISEASE", 464, 467): (
        "remove",
        "BPH means brown planthopper in this article, not benign prostatic hyperplasia.",
    ),
    ("23956011", "DISEASE", 539, 542): (
        "remove",
        "BPH means brown planthopper in this article, not benign prostatic hyperplasia.",
    ),
    ("23956011", "DISEASE", 597, 600): (
        "remove",
        "BPH means brown planthopper in this article, not benign prostatic hyperplasia.",
    ),
    ("23956011", "DISEASE", 1431, 1434): (
        "remove",
        "BPH means brown planthopper in this article, not benign prostatic hyperplasia.",
    ),
    ("23956011", "DISEASE", 1675, 1678): (
        "remove",
        "BPH means brown planthopper in this article, not benign prostatic hyperplasia.",
    ),
    ("22132949", "DISEASE", 22, 31): (
        "remove",
        "The bare generic word 'disorders' does not name a disease.",
    ),
    ("22132949", "DISEASE", 35, 41): (
        "remove",
        "Purine is part of the pathway mention 'purine metabolism', not a disease.",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", type=Path, required=True)
    parser.add_argument("--doccano", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected an object at {path}:{line_number}")
            records.append(value)
    if not records:
        raise ValueError(f"No records found in {path}")
    return records


def atomic_jsonl_dump(records: Iterable[dict[str, Any]], path: Path) -> None:
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


def pmid_from_doccano(record: dict[str, Any], *, context: str) -> str:
    meta = record.get("meta")
    pmid = meta.get("pmid") if isinstance(meta, dict) else record.get("pmid")
    if pmid is None or not str(pmid).strip():
        raise ValueError(f"{context} has no PMID")
    return str(pmid)


def load_doccano(path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for line_number, record in enumerate(load_jsonl(path), 1):
        context = f"{path}:{line_number}"
        pmid = pmid_from_doccano(record, context=context)
        if pmid in index:
            raise ValueError(f"Duplicate PMID {pmid} in {path}")
        text = record.get("text")
        labels = record.get("label", record.get("labels"))
        if not isinstance(text, str) or not isinstance(labels, list):
            raise ValueError(f"{context} must contain string text and list labels")
        normalized_labels: set[tuple[int, int, str]] = set()
        for label_index, label in enumerate(labels, 1):
            if not isinstance(label, list) or len(label) != 3:
                raise ValueError(f"{context} label {label_index} is invalid")
            start, end, entity = label
            if (
                isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(end, bool)
                or not isinstance(end, int)
                or entity not in ENTITY_TYPES
                or not 0 <= start < end <= len(text)
            ):
                raise ValueError(f"{context} label {label_index} is invalid")
            key = (start, end, entity)
            if key in normalized_labels:
                raise ValueError(f"{context} contains duplicate label {key}")
            normalized_labels.add(key)
        index[pmid] = {
            "doc_index_1based": line_number,
            "text": text,
            "labels": normalized_labels,
        }
    return index


def candidate_id(record: dict[str, Any]) -> str:
    stable = "|".join(
        str(record.get(key, ""))
        for key in (
            "doc_index_1based",
            "pmid",
            "entity",
            "candidate_type",
            "start",
            "end",
            "source_id",
        )
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_short_abbreviation(surface: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]", "", surface)
    return bool(compact) and len(compact) <= 5 and compact.upper() == compact


def strong_disease_surface(surface: str) -> bool:
    lowered = surface.casefold().strip()
    return (
        lowered not in GENERIC_DISEASE_SURFACES
        and lowered not in DISEASE_ADJECTIVE_SURFACES
        and DISEASE_HEAD_RE.search(surface) is not None
    )


def result(
    decision: str,
    status: str,
    confidence: str,
    basis: str,
) -> tuple[str, str, str, str]:
    return decision, status, confidence, basis


def curate(record: dict[str, Any], overlap_count: int) -> tuple[str, str, str, str]:
    pmid = str(record["pmid"])
    entity = record["entity"]
    candidate_type = record["candidate_type"]
    surface = str(record["text"])
    lowered = surface.casefold().strip()
    rule = str(record["rule"])
    proposed = str(record["decision"])
    confidence = str(record["confidence"])

    override = KNOWN_CONTEXT_OVERRIDES.get(
        (pmid, entity, int(record["start"]), int(record["end"]))
    )
    if override is not None:
        return result(override[0], "overridden", "high", override[1])

    if (pmid, entity, int(record["start"]), int(record["end"])) in NESTED_REVIEWER_DUPLICATES:
        return result(
            "reject",
            "overridden" if proposed != "reject" else "approved",
            "high",
            "The reviewer span duplicates or nests inside an existing disease annotation; do not add it separately.",
        )

    if entity == "DISEASE" and pmid in UNSAFE_PUBTATOR_ALIGNMENT_PMIDS:
        return result(
            "defer",
            "deferred",
            "low",
            "PubTator occurrence alignment is known to be unreliable for this PMID.",
        )

    if entity == "DISEASE" and lowered in DISEASE_POLICY_REJECT_SURFACES:
        decision = "reject" if candidate_type == "false_negative" else "remove"
        explanation = {
            "inflammatory": "A standalone adjective is not a disease mention.",
            "proinflammatory": "A standalone inflammation-promoting adjective is not a disease mention.",
            "metastasis": "A bare process term is not added; annotate a complete secondary-lesion phrase when present.",
            "metastases": "A bare process or generic lesion term is not added; annotate a complete secondary-lesion phrase when present.",
        }[lowered]
        return result(
            decision,
            "overridden" if proposed != decision else "approved",
            "high",
            explanation,
        )

    if entity == "PATHWAY" and PATHWAY_EXCLUDED_PROCESS_RE.search(surface):
        decision = "reject" if candidate_type == "false_negative" else "remove"
        return result(
            decision,
            "overridden" if proposed != decision else "approved",
            "high",
            "Transport, uptake, efflux, secretion, translocation, and signaling processes are outside the metabolic-pathway policy.",
        )

    if overlap_count and candidate_type == "false_negative":
        return result(
            "defer",
            "deferred",
            "low",
            "The proposed false negative overlaps a current annotation and requires boundary adjudication.",
        )

    if confidence == "low":
        return result(
            "defer",
            "deferred",
            "low",
            "The inspection proposal has low confidence and lacks deterministic policy evidence.",
        )

    if entity == "DISEASE":
        if rule in SAFE_DISEASE_EXCLUSION_RULES and proposed in {"reject", "remove"}:
            return result(
                proposed,
                "approved",
                "high" if confidence == "high" else "medium",
                "The exclusion rule matches the disease policy and the inspected context.",
            )

        if rule in RISKY_DISEASE_RULES:
            return result(
                "defer",
                "deferred",
                "low" if confidence == "medium" else "medium",
                "This rule conflates symptoms, phenotypes, pathology descriptions, or context-dependent lexical matches with diseases.",
            )

        if rule == "DIS-ACCEPT-LIST":
            if is_short_abbreviation(surface):
                return result(
                    "defer",
                    "deferred",
                    "medium",
                    "A short abbreviation is unsafe without a verified local definition.",
                )
            if proposed in {"add", "keep"} and strong_disease_surface(surface):
                return result(
                    proposed,
                    "approved",
                    "high",
                    "The full surface contains an explicit disease head and is not a standalone adjective.",
                )
            return result(
                "defer",
                "deferred",
                "medium",
                "The accept-list match is not sufficient contextual evidence for a disease decision.",
            )

        if rule == "ABBR-DEF" and confidence == "high":
            if proposed == "reject":
                return result(
                    proposed,
                    "approved",
                    "high",
                    "The local definition shows that the abbreviation is not a disease.",
                )
            return result(
                "defer",
                "deferred",
                "medium",
                "The local definition may denote a symptom, model, enzyme, effect, or cell line rather than a disease mention at this occurrence.",
            )

        if rule in {"DIS-KEYWORD", "DIS-SUFFIX"} and proposed in {"add", "keep"}:
            if confidence == "high" and strong_disease_surface(surface):
                return result(
                    proposed,
                    "approved",
                    "high",
                    "The complete surface contains a strong disease-forming head or suffix.",
                )
            return result(
                "defer",
                "deferred",
                "medium",
                "A keyword or suffix alone is insufficient for this surface under the disease-only policy.",
            )

        if rule == "MANUAL" and confidence == "high":
            return result(
                proposed,
                "approved",
                "high",
                "The inspection contains a high-confidence context-specific manual decision.",
            )

    if entity == "PATHWAY":
        if rule in SAFE_PATHWAY_EXCLUSION_RULES and proposed in {"reject", "remove"}:
            return result(
                proposed,
                "approved",
                "high" if confidence == "high" else "medium",
                "The surface does not name a metabolic process under the pathway guide.",
            )

        if (
            rule in {"PW-ACCEPT-LIST", "PW-PROCESS-WORD", "ABBR-DEF"}
            and proposed in {"add", "keep"}
            and confidence == "high"
        ):
            return result(
                proposed,
                "approved",
                "high",
                "The complete surface names a metabolic process and passes the project exclusions.",
            )

        if rule == "LEX-ACCEPTED" and proposed in {"add", "keep"}:
            return result(
                "defer",
                "deferred",
                "medium",
                "A repeated lexical surface is not enough to prove a metabolic process in this context.",
            )

        if rule == "MANUAL" and confidence == "high":
            return result(
                proposed,
                "approved",
                "high",
                "The inspection contains a high-confidence context-specific manual decision.",
            )

    return result(
        "defer",
        "deferred",
        "low" if confidence == "medium" else "medium",
        "No sufficiently precise project rule supports applying this proposal automatically.",
    )


def validate_and_curate(
    inspect_records: list[dict[str, Any]],
    doccano_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, record in enumerate(inspect_records, 1):
        context = f"inspect line {line_number}"
        required = {
            "candidate_type",
            "confidence",
            "context",
            "decision",
            "doc_index_1based",
            "end",
            "entity",
            "pmid",
            "rationale",
            "rule",
            "start",
            "text",
        }
        missing = sorted(required - record.keys())
        if missing:
            raise ValueError(f"{context} is missing keys: {', '.join(missing)}")
        pmid = str(record["pmid"])
        entity = record["entity"]
        candidate_type = record["candidate_type"]
        start = record["start"]
        end = record["end"]
        if entity not in ENTITY_TYPES or candidate_type not in FINAL_DECISIONS:
            raise ValueError(f"{context} has invalid entity or candidate type")
        if pmid not in doccano_index:
            raise ValueError(f"{context} PMID {pmid} is absent from Doccano")
        source = doccano_index[pmid]
        source_text = source["text"]
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or not 0 <= start < end <= len(source_text)
        ):
            raise ValueError(f"{context} has invalid offsets")
        if source_text[start:end] != record["text"]:
            raise ValueError(f"{context} surface does not match Doccano text")
        if int(record["doc_index_1based"]) != source["doc_index_1based"]:
            raise ValueError(f"{context} document index does not match Doccano")

        exact_key = (start, end, entity)
        current_exact = exact_key in source["labels"]
        if candidate_type == "false_positive" and not current_exact:
            raise ValueError(f"{context} false positive is absent from Doccano")
        current_overlaps = sorted(
            [
                [label_start, label_end, label_entity]
                for label_start, label_end, label_entity in source["labels"]
                if label_entity == entity and start < label_end and label_start < end
            ]
        )

        decision, status, final_confidence, basis = curate(
            record, len(current_overlaps)
        )
        if decision not in FINAL_DECISIONS[candidate_type]:
            raise ValueError(
                f"{context} produced invalid decision {decision!r} for {candidate_type}"
            )
        stable_id = candidate_id(record)
        if stable_id in seen_ids:
            raise ValueError(f"Duplicate candidate identity at {context}: {stable_id}")
        seen_ids.add(stable_id)

        output.append(
            {
                "candidate_id": stable_id,
                "doc_index_1based": int(record["doc_index_1based"]),
                "pmid": pmid,
                "entity": entity,
                "candidate_type": candidate_type,
                "start": start,
                "end": end,
                "text": record["text"],
                "context": record["context"],
                "source_id": record.get("source_id"),
                "primary_model_score": record.get("primary_model_score"),
                "reviewer_identifier": record.get("reviewer_identifier"),
                "inspect_decision": record["decision"],
                "inspect_confidence": record["confidence"],
                "inspect_rule": record["rule"],
                "inspect_rationale": record["rationale"],
                "inspect_policy_conflict": bool(record.get("policy_conflict", False)),
                "inspect_exact_agreement_count": record.get("corpus_accepted_count"),
                "final_decision": decision,
                "doccano_action": ACTION_BY_DECISION[decision],
                "curation_status": status,
                "curation_confidence": final_confidence,
                "curation_basis": basis,
                "validation": {
                    "source_text_matches": True,
                    "doc_index_matches": True,
                    "current_exact_span": current_exact,
                    "current_overlapping_spans": current_overlaps,
                },
            }
        )
    return output


def build_summary(
    records: list[dict[str, Any]],
    *,
    inspect_path: Path,
    doccano_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    candidate_documents: set[str] = set()
    actionable_documents: set[str] = set()
    for record in records:
        candidate_documents.add(record["pmid"])
        if record["doccano_action"] in {"add_span", "remove_span"}:
            actionable_documents.add(record["pmid"])
        counters["entity"][record["entity"]] += 1
        counters["candidate_type"][record["candidate_type"]] += 1
        counters["inspect_decision"][record["inspect_decision"]] += 1
        counters["final_decision"][record["final_decision"]] += 1
        counters["doccano_action"][record["doccano_action"]] += 1
        counters["curation_status"][record["curation_status"]] += 1
        counters["curation_confidence"][record["curation_confidence"]] += 1
        counters[f"{record['entity'].lower()}_final_decision"][record["final_decision"]] += 1
    return {
        "review_kind": "curated_simple_disagreement_decisions",
        "warning": (
            "Only add_span and remove_span rows are actionable. Deferred rows require "
            "manual adjudication. This file does not modify Doccano annotations."
        ),
        "scope_limitations": [
            "The inspection input contains only simple false-positive and false-negative candidates.",
            "Exact agreements, boundary corrections, uncertain overlap components, and unreviewed spans are not represented.",
            "Project-wide policy sweeps are not synthesized for spans absent from the inspection input.",
        ],
        "policy": {
            "disease": (
                "Annotate disease names, not standalone symptoms, signs, phenotype "
                "adjectives, generic pathology descriptions, or ambiguous abbreviations."
            ),
            "pathway": (
                "Annotate metabolic processes; exclude transport, uptake, efflux, "
                "secretion, translocation, signaling, compounds, genes, and diseases."
            ),
            "metastasis": (
                "Reject a bare process mention; a complete location-qualified secondary "
                "lesion phrase must be adjudicated as its own span."
            ),
        },
        "sources": {
            "inspect": str(inspect_path),
            "inspect_sha256": file_sha256(inspect_path),
            "doccano": str(doccano_path),
            "doccano_sha256": file_sha256(doccano_path),
        },
        "output": str(output_path),
        "records": len(records),
        "documents_with_candidates": len(candidate_documents),
        "documents_with_actionable_changes": len(actionable_documents),
        "counts": {
            name: dict(sorted(counter.items()))
            for name, counter in sorted(counters.items())
        },
        "validation": {
            "all_candidate_offsets_match_source_text": True,
            "all_document_indices_match_source_doccano": True,
            "all_false_positive_spans_exist_in_source_doccano": True,
            "unique_candidate_ids": True,
        },
    }


def main() -> None:
    args = parse_args()
    for path in (args.output, args.summary):
        if path.exists() and not args.overwrite:
            raise FileExistsError(f"Output already exists: {path}; pass --overwrite")
    inspect_records = load_jsonl(args.inspect)
    doccano_index = load_doccano(args.doccano)
    curated = validate_and_curate(inspect_records, doccano_index)
    summary = build_summary(
        curated,
        inspect_path=args.inspect,
        doccano_path=args.doccano,
        output_path=args.output,
    )
    atomic_jsonl_dump(curated, args.output)
    summary["output_sha256"] = file_sha256(args.output)
    atomic_json_dump(summary, args.summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
