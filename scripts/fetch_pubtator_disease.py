#!/usr/bin/env python3
"""Fetch PubTator disease annotations and align them to local abstract text.

The input must be JSONL with a PMID and ``text`` or ``abstract`` field. Doccano
metadata PMIDs are also supported. PubTator responses are cached per PMID so a
large request can be resumed safely. Only Disease annotations from abstract
passages are retained, and every emitted span is verified against the exact
local text.

Example::

    python3 scripts/fetch_pubtator_disease.py \
        --input /home/enes/NER-pipeline/data/processed/disease-ner/articles_remaining_6125.jsonl \
        --output /home/enes/NER-pipeline/data/processed/disease-ner/pubtator_disease_remaining_6125.jsonl
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import http.client
import json
import logging
import os
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Sequence

from tqdm import tqdm


API_URL = (
    "https://www.ncbi.nlm.nih.gov/research/pubtator-api/"
    "publications/export/biocjson"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_jsonl(path: Path, limit: int | None) -> list[dict[str, Any]]:
    """Load validated JSONL objects."""
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
            if limit is not None and len(records) >= limit:
                break
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


def record_text(record: dict[str, Any], *, context: str) -> str:
    """Read exact local text without whitespace normalization."""
    value = record.get("text", record.get("abstract"))
    if not isinstance(value, str):
        raise ValueError(f"{context} has no string text/abstract")
    return value


def atomic_json_dump(value: Any, path: Path) -> None:
    """Write one JSON value atomically."""
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
            json.dump(value, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def atomic_jsonl_dump(records: Iterable[dict[str, Any]], path: Path) -> None:
    """Write ordered JSONL atomically."""
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


def pubtator_pmid(document: dict[str, Any]) -> str:
    """Read the PMID prefix from a PubTator BioC document."""
    value = document.get("_id", document.get("id"))
    if value is None:
        raise ValueError("PubTator document has no _id/id")
    return str(value).split("|", 1)[0]


def request_documents(
    pmids: Sequence[str],
    *,
    timeout: float,
    max_retries: int,
) -> dict[str, dict[str, Any]]:
    """Fetch one PMID batch with bounded exponential retry."""
    query = urllib.parse.urlencode({"pmids": ",".join(pmids)})
    url = API_URL + "?" + query
    errors: list[str] = []
    for attempt in range(1, max_retries + 1):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "NER-pipeline disease review/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            documents = payload.get("PubTator3") if isinstance(payload, dict) else payload
            if not isinstance(documents, list):
                raise ValueError("PubTator response has no document array")
            indexed: dict[str, dict[str, Any]] = {}
            for document in documents:
                if not isinstance(document, dict):
                    raise ValueError("PubTator returned a non-object document")
                pmid = pubtator_pmid(document)
                if pmid in indexed:
                    raise ValueError(f"PubTator returned duplicate PMID {pmid}")
                indexed[pmid] = document
            return indexed
        except (
            json.JSONDecodeError,
            http.client.HTTPException,
            TimeoutError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            ValueError,
        ) as exc:
            errors.append(str(exc))
            if attempt == max_retries:
                break
            delay = min(2 ** (attempt - 1), 30)
            log.warning(
                "PubTator request attempt %d/%d failed; retrying in %ds: %s",
                attempt,
                max_retries,
                delay,
                exc,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"PubTator batch failed after {max_retries} attempts: " + " | ".join(errors)
    )


def exact_occurrences(text: str, surface: str) -> list[tuple[int, int]]:
    """Return every exact, case-sensitive surface occurrence."""
    if not surface:
        return []
    values: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = text.find(surface, cursor)
        if start < 0:
            break
        values.append((start, start + len(surface)))
        cursor = start + 1
    return values


def approximate_target_offset(source: str, target: str, source_offset: int) -> int:
    """Map a source boundary to the nearest aligned target boundary."""
    matcher = difflib.SequenceMatcher(None, source, target, autojunk=False)
    best_source = 0
    best_target = 0
    for _, source_start, source_end, target_start, target_end in matcher.get_opcodes():
        if source_start <= source_offset <= source_end:
            if source_end == source_start:
                return target_start
            ratio = (source_offset - source_start) / (source_end - source_start)
            return round(target_start + ratio * (target_end - target_start))
        if source_end <= source_offset:
            best_source = source_end
            best_target = target_end
    return best_target + max(0, source_offset - best_source)


def comparison_form(value: str) -> str:
    """Normalize common PubMed typography for conservative alignment checks."""
    value = value.translate(
        str.maketrans(
            {
                "α": "alpha",
                "β": "beta",
                "γ": "gamma",
                "δ": "delta",
                "Δ": "delta",
                "κ": "kappa",
                "Κ": "kappa",
            }
        )
    )
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in decomposed if character.isalnum())


def align_surface(
    source_text: str,
    target_text: str,
    *,
    source_start: int,
    source_end: int,
    surface: str,
) -> tuple[int, int, str] | None:
    """Align one PubTator surface to an exact occurrence in local text."""
    source_occurrences = exact_occurrences(source_text, surface)
    target_occurrences = exact_occurrences(target_text, surface)
    if source_occurrences and len(source_occurrences) == len(target_occurrences):
        nearest_index = min(
            range(len(source_occurrences)),
            key=lambda index: abs(source_occurrences[index][0] - source_start),
        )
        start, end = target_occurrences[nearest_index]
        return start, end, "exact_surface_occurrence"
    if target_occurrences:
        expected = approximate_target_offset(source_text, target_text, source_start)
        start, end = min(
            target_occurrences, key=lambda value: abs(value[0] - expected)
        )
        return start, end, "exact_surface_occurrence"

    mapped_start = approximate_target_offset(source_text, target_text, source_start)
    mapped_end = approximate_target_offset(source_text, target_text, source_end)
    if not 0 <= mapped_start < mapped_end <= len(target_text):
        return None
    candidate = target_text[mapped_start:mapped_end]
    source_form = comparison_form(surface)
    candidate_form = comparison_form(candidate)
    if not source_form or not candidate_form:
        return None
    similarity = difflib.SequenceMatcher(
        None, source_form, candidate_form, autojunk=False
    ).ratio()
    if similarity < 0.90:
        return None
    return mapped_start, mapped_end, "sequence_alignment"


def normalize_document(
    document: dict[str, Any] | None,
    *,
    pmid: str,
    text: str,
) -> dict[str, Any]:
    """Extract exact local disease spans from one cached BioC document."""
    spans: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    abstract_passages = []
    if document is not None:
        passages = document.get("passages", [])
        if not isinstance(passages, list):
            raise ValueError(f"PMID {pmid} PubTator passages must be a list")
        abstract_passages = [
            passage
            for passage in passages
            if isinstance(passage, dict)
            and str(passage.get("infons", {}).get("type", "")).lower()
            == "abstract"
        ]

    seen: set[tuple[int, int]] = set()
    for passage in abstract_passages:
        source_text = passage.get("text")
        passage_offset = passage.get("offset")
        annotations = passage.get("annotations", [])
        if not isinstance(source_text, str) or not isinstance(passage_offset, int):
            raise ValueError(f"PMID {pmid} has an invalid abstract passage")
        if not isinstance(annotations, list):
            raise ValueError(f"PMID {pmid} annotations must be a list")
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            infons = annotation.get("infons", {})
            if str(infons.get("type", "")).lower() != "disease":
                continue
            surface = annotation.get("text")
            locations = annotation.get("locations", [])
            if not isinstance(surface, str) or not isinstance(locations, list):
                continue
            for location in locations:
                if not isinstance(location, dict):
                    continue
                global_start = location.get("offset")
                length = location.get("length")
                if not isinstance(global_start, int) or not isinstance(length, int):
                    continue
                source_start = global_start - passage_offset
                source_end = source_start + length
                if (
                    0 <= source_start < source_end <= len(source_text)
                    and source_text[source_start:source_end] == surface
                    and source_text == text
                ):
                    aligned = (source_start, source_end, "direct_offset")
                else:
                    aligned = align_surface(
                        source_text,
                        text,
                        source_start=source_start,
                        source_end=source_end,
                        surface=surface,
                    )
                if aligned is None:
                    failures.append(
                        {
                            "surface": surface,
                            "source_start": source_start,
                            "source_end": source_end,
                        }
                    )
                    continue
                start, end, alignment_method = aligned
                local_surface = text[start:end]
                key = (start, end)
                if key in seen:
                    continue
                seen.add(key)
                spans.append(
                    {
                        "start": start,
                        "end": end,
                        "text": local_surface,
                        "label": "DISEASE",
                        "identifier": infons.get("identifier"),
                        "normalized_name": infons.get("name"),
                        "alignment_method": alignment_method,
                        "pubtator_text": (
                            surface if surface != local_surface else None
                        ),
                    }
                )
    spans.sort(key=lambda span: (span["start"], span["end"]))
    return {
        "pmid": pmid,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source": "NCBI PubTator",
        "source_url": API_URL,
        "status": "ok" if document is not None and abstract_passages else "missing",
        "abstract_text_exact_match": bool(
            abstract_passages and abstract_passages[0].get("text") == text
        ),
        "alignment_failures": failures,
        "spans": spans,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--request-delay", type=float, default=0.34)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("--batch-size must be between 1 and 100")
    if args.timeout <= 0 or args.max_retries <= 0 or args.request_delay < 0:
        parser.error("timeout/retries must be positive and delay non-negative")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


def main() -> None:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if output_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Pass --overwrite to replace it."
        )
    cache_dir = (
        args.cache_dir.expanduser().resolve()
        if args.cache_dir is not None
        else output_path.parent / "cache" / "pubtator_disease"
    )
    records = load_jsonl(input_path, args.limit)
    prepared: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        pmid = record_pmid(record, context=f"{input_path}:{index}")
        if pmid in seen:
            raise ValueError(f"Duplicate PMID {pmid} in {input_path}")
        seen.add(pmid)
        prepared.append((pmid, record_text(record, context=f"{input_path}:{index}")))

    cache_dir.mkdir(parents=True, exist_ok=True)
    missing = [pmid for pmid, _ in prepared if not (cache_dir / f"{pmid}.json").is_file()]
    log.info(
        "input=%s documents=%d cached=%d fetch=%d",
        input_path,
        len(prepared),
        len(prepared) - len(missing),
        len(missing),
    )
    for start in tqdm(
        range(0, len(missing), args.batch_size),
        desc="PubTator batches",
        unit="batch",
    ):
        batch = missing[start : start + args.batch_size]
        fetched = request_documents(
            batch,
            timeout=args.timeout,
            max_retries=args.max_retries,
        )
        absent = set(batch) - set(fetched)
        if absent:
            log.warning("PubTator returned no document for %d PMID(s)", len(absent))
        for pmid in batch:
            atomic_json_dump(fetched.get(pmid), cache_dir / f"{pmid}.json")
        if start + args.batch_size < len(missing) and args.request_delay:
            time.sleep(args.request_delay)

    output: list[dict[str, Any]] = []
    total_spans = total_failures = missing_documents = text_mismatches = 0
    for pmid, text in prepared:
        cache_path = cache_dir / f"{pmid}.json"
        if not cache_path.is_file():
            raise FileNotFoundError(f"Missing expected cache file: {cache_path}")
        document = json.loads(cache_path.read_text(encoding="utf-8"))
        if document is not None and pubtator_pmid(document) != pmid:
            raise ValueError(f"Cached PMID mismatch in {cache_path}")
        normalized = normalize_document(document, pmid=pmid, text=text)
        total_spans += len(normalized["spans"])
        total_failures += len(normalized["alignment_failures"])
        missing_documents += normalized["status"] == "missing"
        text_mismatches += (
            normalized["status"] == "ok"
            and not normalized["abstract_text_exact_match"]
        )
        output.append(normalized)
    atomic_jsonl_dump(output, output_path)
    log.info(
        "wrote=%s documents=%d spans=%d missing_documents=%d "
        "text_mismatches=%d alignment_failures=%d",
        output_path,
        len(output),
        total_spans,
        missing_documents,
        text_mismatches,
        total_failures,
    )


if __name__ == "__main__":
    try:
        main()
    except (
        FileExistsError,
        FileNotFoundError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
