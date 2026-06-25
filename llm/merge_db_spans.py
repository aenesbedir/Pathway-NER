#!/usr/bin/env python3
"""
merge_db_spans.py

Converts source-3 extractions (db_with_extracted_pathways.json) into
character-offset spans and appends them to all_matches.jsonl.

- Pathway names matched to KEGG/Reactome get their real pathway_id + source.
- Unmatched pathway names get a synthetic id  "db__{normalized_name}".
- All spans are re-verified verbatim before writing.

Run with:
    python3 llm/merge_db_spans.py
"""

import json
import re
from pathlib import Path

DB_FILE = Path("data/processed/db_with_extracted_pathways.json")
ALL_MATCHES = Path("data/processed/all_matches.jsonl")
KEGG_FILE = Path("data/raw/kegg_pathways.jsonl")
REACTOME_FILE = Path("data/raw/reactome_pathways.jsonl")


def normalize(s: str) -> str:
    return re.sub(r"[\s\-/,]+", " ", s.lower()).strip()


def build_lookup() -> dict:
    lookup = {}
    for line in KEGG_FILE.open(encoding="utf-8"):
        p = json.loads(line)
        for name in [p["canonical_name"]] + p.get("synonyms", []):
            lookup[normalize(name)] = ("kegg", p["pathway_id"])
    for line in REACTOME_FILE.open(encoding="utf-8"):
        p = json.loads(line)
        for name in [p["canonical_name"]] + p.get("synonyms", []):
            lookup[normalize(name)] = ("reactome", p["pathway_id"])
    return lookup


def find_spans(text: str, candidates: list[str]) -> list[dict]:
    text_lower = text.lower()
    spans = []
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        pos = text_lower.find(c.lower())
        if pos == -1:
            continue
        spans.append({
            "start": pos,
            "end": pos + len(c),
            "text": text[pos: pos + len(c)],
            "source": "abstract",
        })
    return spans


def main() -> None:
    lookup = build_lookup()

    db = json.loads(DB_FILE.read_text(encoding="utf-8"))
    records_with = [r for r in db if r.get("extracted_pathway_names")]
    print(f"DB records with extractions: {len(records_with)}")

    new_records = []
    skipped_no_spans = 0

    for rec in records_with:
        pathway_name = rec["pathway"]
        pmid = str(rec["pmid"])
        abstract = (rec.get("abstract") or "").strip()

        if not abstract:
            skipped_no_spans += 1
            continue

        spans = find_spans(abstract, rec["extracted_pathway_names"])
        if not spans:
            skipped_no_spans += 1
            continue

        key = normalize(pathway_name)
        if key in lookup:
            source, pathway_id = lookup[key]
        else:
            source = "recon3d"
            pathway_id = "db__" + re.sub(r"[^\w]", "_", pathway_name.lower())

        new_records.append({
            "pathway_id": pathway_id,
            "source": source,
            "pmid": pmid,
            "spans": spans,
        })

    with ALL_MATCHES.open("a", encoding="utf-8") as fh:
        for r in new_records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_spans = sum(len(r["spans"]) for r in new_records)
    matched = sum(1 for r in new_records if r["source"] != "db")
    print(f"New records appended : {len(new_records)}")
    print(f"  — mapped to KEGG/Reactome : {matched}")
    print(f"  — synthetic db__ id       : {len(new_records) - matched}")
    print(f"  — skipped (no spans)      : {skipped_no_spans}")
    print(f"Total new spans      : {total_spans}")
    print(f"all_matches.jsonl now has {sum(1 for _ in ALL_MATCHES.open())} records")


if __name__ == "__main__":
    main()
