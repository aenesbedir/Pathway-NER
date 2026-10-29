"""Merge the reviewed 10k corpus with the missing-pathway corpus, PATHWAY only.

Sources
-------
data/doccano/10k_dict_match.jsonl
    10,125 abstracts. PATHWAY labels are reviewed (human review on wave3/wave4,
    assistant review on pilot/wave2, curated decisions on the remaining 6,125)
    with a `pathway_surface_forms.py` overlay applied on top. Also carries
    DISEASE labels from pruas/BENT-PubMedBERT-NER-Disease, which this script
    drops: the missing corpus has no disease annotation, so keeping them would
    teach the model that every disease in the new abstracts is O.

data/processed/missing_pathways/missing_llm_review.jsonl
    831 abstracts retrieved for the eight curated Recon targets that the 10k
    corpus never covered. Spans are the merge of three stages: the project NER
    checkpoint, the pattern booster, and the surface-form dictionary, after
    scripts/apply_llm_review.py removed the 29 spans an LLM audit judged wrong.
    Boundary and canonical findings from that audit are not applied - see the
    script for why. No human has reviewed these spans.

Overlap: 56 of the 831 PMIDs already appear in the 10k corpus. The 10k version
wins for those - it is reviewed, the missing one is not - so only the 775 new
abstracts are added.

Text for the missing side comes from data/raw/missing_pathways/articles.json
and is the abstract alone, which is what run_missing_stages.py fed the model,
so the character offsets carry over unchanged. The 10k side is likewise the
abstract alone (verified against pathway-10k/articles.jsonl).

Usage:
    python scripts/build_merged_pathway_dataset.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = Path("/home/enes/NER-pipeline")
TEN_K = MAIN / "data/doccano/10k_dict_match.jsonl"
MISSING = ROOT / "data/processed/missing_pathways/missing_llm_review.jsonl"
ARTICLES = ROOT / "data/raw/missing_pathways/articles.json"
OUT_DIR = ROOT / "data/doccano"
OUT = OUT_DIR / "pathway_10k_plus_missing.jsonl"
MANIFEST = OUT_DIR / "pathway_10k_plus_missing.manifest.json"


def sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dedupe(spans: list[list]) -> list[list]:
    """Drop exact duplicates, keep document order, then sort by offset."""
    seen = set()
    out = []
    for s in spans:
        key = (s[0], s[1], s[2])
        if key in seen:
            continue
        seen.add(key)
        out.append([s[0], s[1], s[2]])
    return sorted(out, key=lambda s: (s[0], s[1]))


def main() -> None:
    arts = {a["pmid"]: a for a in json.loads(ARTICLES.read_text())}

    records = []
    ten_k_pmids = set()
    dropped_disease = 0

    for line in TEN_K.open(encoding="utf-8"):
        doc = json.loads(line)
        pmid = doc["meta"]["pmid"]
        ten_k_pmids.add(pmid)
        pathway = [e for e in doc["label"] if e[2] == "PATHWAY"]
        dropped_disease += len(doc["label"]) - len(pathway)
        meta = dict(doc["meta"])
        meta.pop("disease_source", None)
        meta["merge_source"] = "10k_dict_match"
        records.append({"text": doc["text"], "label": dedupe(pathway), "meta": meta})

    added = 0
    skipped_overlap = 0
    skipped_no_text = 0
    offset_mismatch = 0
    added_spans = 0
    by_stage = Counter()

    for line in MISSING.open(encoding="utf-8"):
        rec = json.loads(line)
        pmid = rec["pmid"]
        if pmid in ten_k_pmids:
            skipped_overlap += 1
            continue
        text = (arts.get(pmid, {}).get("abstract") or "").strip()
        if not text:
            skipped_no_text += 1
            continue

        label = []
        for s in rec["spans"]:
            # The offsets were produced against this exact string; verify rather
            # than trust, because a silent shift would poison the training data.
            if text[s["start"]:s["end"]] != s["text"]:
                offset_mismatch += 1
                continue
            label.append([s["start"], s["end"], "PATHWAY"])
            by_stage[s["source"]] += 1

        label = dedupe(label)
        added_spans += len(label)
        records.append({
            "text": text,
            "label": label,
            "meta": {
                "pmid": pmid,
                "merge_source": "missing_pathways",
                "pathway_source": {
                    "input_file": "data/processed/missing_pathways/missing_llm_review.jsonl",
                    "stages": "ner + booster + surface-form dictionary (merged)",
                    "review": "llm audit applied: wrong spans dropped, boundaries kept",
                    "model": rec.get("model"),
                    "route": rec["route"],
                    "query_pathways": rec["pathways"],
                    "annotation_status": "llm_reviewed_silver",
                },
            },
        })
        added += 1

    with OUT.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    total_spans = sum(len(r["label"]) for r in records)
    manifest = {
        "schema_version": 1,
        "artifact_type": "doccano_sequence_labeling_import",
        "version": "10k-plus-missing-v1",
        "label_set": ["PATHWAY"],
        "output": {
            "path": str(OUT.relative_to(ROOT)),
            "sha256": sha256(OUT),
            "documents": len(records),
            "labels": {"PATHWAY": total_spans},
        },
        "inputs": {
            "ten_k": {
                "path": str(TEN_K),
                "sha256": sha256(TEN_K),
                "documents": len(ten_k_pmids),
                "dropped_disease_spans": dropped_disease,
            },
            "missing": {
                "path": str(MISSING.relative_to(ROOT)),
                "sha256": sha256(MISSING),
                "documents_added": added,
                "spans_added": added_spans,
                "spans_by_stage": dict(by_stage),
                "skipped_already_in_10k": skipped_overlap,
                "skipped_no_abstract": skipped_no_text,
                "spans_dropped_offset_mismatch": offset_mismatch,
                "annotation_status": "llm_reviewed_silver",
            },
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
