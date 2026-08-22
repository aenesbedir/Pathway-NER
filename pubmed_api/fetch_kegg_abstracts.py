#!/usr/bin/env python3
"""
fetch_kegg_abstracts.py

Fetch PubMed abstracts for every PMID in the KEGG–Recon3D matched-pathway table
(`data/raw/kegg_recon3d/kegg_recon3d_matched_pathways.csv`) and write them in the
same record shape as `data/raw/articles.json`, so the downstream LLM silver
pipeline can consume this corpus with no format translation.

Unlike `fetch_articles.py` this is abstract-only: no ELink/PMC step, no full text.
The CSV rows are pathway–disease evidence links, and the silver annotator only ever
reads `abstract`.

Reuses `fetch_articles.fetch_pubmed_batch`, so the shared cache
(`data/raw/article_cache/pubmed_<pmid>.json`) is hit for PMIDs already fetched by
the main pipeline and the run is resumable.

Outputs (both under data/raw/kegg_recon3d/):
    articles.json  — [{pmid, title, abstract, year, journal, doi, pub_types,
                       keywords, mesh_headings, source_csv_rows: [...]}]
                     `source_csv_rows` keeps the pathway/disease link each PMID is
                     evidence for, so the CSV never has to be re-joined downstream.
    pmids.txt      — one PMID per line, in CSV order, for `run_silver.py --pmids`

Run from repo root:
    venv310/bin/python3 pubmed_api/fetch_kegg_abstracts.py
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pubmed_api"))

from fetch_articles import fetch_pubmed_batch  # noqa: E402

DATA_DIR = ROOT / "data/raw/kegg_recon3d"
CSV_FILE = DATA_DIR / "kegg_recon3d_matched_pathways.csv"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# Row fields kept alongside the article — the pathway/disease link the PMID is
# evidence for. Dropped: reference_title/journal, which duplicate the fetched
# metadata and disagree with it whenever KEGG's citation string is stale.
ROW_FIELDS = ["disease_name", "disease_id", "pathway_name", "pathway_id", "category",
              "matched_recon3d_pathway", "match_method", "match_score"]


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(CSV_FILE))
    ap.add_argument("--out-dir", default=str(DATA_DIR))
    ap.add_argument("--limit", type=int, default=None,
                    help="fetch only the first N unique PMIDs (smoke test)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_rows(Path(args.csv))
    by_pmid: dict[str, list[dict]] = {}
    for r in rows:
        pmid = str(r["pmid"]).strip()
        if pmid:
            by_pmid.setdefault(pmid, []).append({k: r.get(k) for k in ROW_FIELDS})

    pmids = list(by_pmid)
    if args.limit:
        pmids = pmids[:args.limit]
    log.info("CSV: %d rows -> %d unique PMIDs", len(rows), len(pmids))

    fetched = fetch_pubmed_batch(pmids)
    log.info("Fetched %d/%d PubMed records", len(fetched), len(pmids))

    articles, no_abstract, missing = [], 0, []
    for pmid in pmids:
        rec = fetched.get(pmid)
        if rec is None:
            missing.append(pmid)
            continue
        if not (rec.get("abstract") or "").strip():
            no_abstract += 1
        articles.append({**rec, "source_csv_rows": by_pmid[pmid]})

    (out_dir / "articles.json").write_text(
        json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "pmids.txt").write_text(
        "# PMIDs of kegg_recon3d_matched_pathways.csv, CSV order, abstract fetched.\n"
        + "".join(a["pmid"] + "\n" for a in articles if (a.get("abstract") or "").strip()),
        encoding="utf-8")

    log.info("─" * 60)
    log.info("Articles      : %d  (%s)", len(articles), out_dir / "articles.json")
    log.info("No abstract   : %d", no_abstract)
    if missing:
        log.warning("NOT FETCHED   : %d pmid(s) — re-run to retry: %s%s",
                    len(missing), ", ".join(missing[:10]),
                    " …" if len(missing) > 10 else "")
    log.info("─" * 60)


if __name__ == "__main__":
    main()
