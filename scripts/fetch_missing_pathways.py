#!/usr/bin/env python3
"""
fetch_missing_pathways.py

Recover PubMed coverage for the Recon pathways that the 10k corpus never
annotated and that the dictionary matcher never found — the "missing" set.

For every literature surface form of those pathways (from
preprocessing/pathway_surface_forms.py) two PubMed searches are run:

  solo : "<form>"[Title/Abstract]
  pair : ("<form>"[Title/Abstract]) AND ("<disease>"[Title/Abstract])
         over the 98 curated diseases, capped at PAIR_CAP pmids per pair

The pair query is the one the original corpus used
(pubmed_api/fetch_pathway_disease_pairs.py); running both makes the choice
between them measurable instead of assumed.

Output: data/raw/missing_pathways/queries.json
Cache : data/raw/missing_pathways/cache/  (one file per query, resumable)
"""

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "preprocessing"))
import pathway_surface_forms as psf  # noqa: E402

API_KEY = "d4e795e70597e6edfa4d1282886100ecee08"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
SLEEP = 0.11
WORKERS = 8        # NCBI allows 10 req/s with an API key; the limiter enforces it
SOLO_CAP = 200
PAIR_CAP = 10

OUT_DIR = ROOT / "data/raw/missing_pathways"
CACHE = OUT_DIR / "cache"
DISEASES = ROOT / "data/raw/selected_diseases.json"

# Recon names absent from both the 10k annotation and exact_matches.jsonl.
TARGETS = json.loads((Path(sys.argv[1])).read_text()) if len(sys.argv) > 1 else None


_lock = threading.Lock()
_next = [0.0]
_session = requests.Session()


def _throttle() -> None:
    """Serialise request starts so the pool never exceeds the NCBI rate."""
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next[0] - now)
        _next[0] = max(now, _next[0]) + SLEEP
    if wait:
        time.sleep(wait)


def esearch(term: str, retmax: int) -> dict:
    key = re.sub(r"[^a-z0-9]+", "_", term.lower())[:150] + f"_{retmax}"
    cf = CACHE / f"{key}.json"
    if cf.exists():
        return json.loads(cf.read_text())
    for attempt in range(4):
        _throttle()
        try:
            r = _session.get(BASE, params={
                "db": "pubmed", "term": term, "retmax": retmax,
                "retmode": "json", "api_key": API_KEY,
            }, timeout=30)
            r.raise_for_status()
            res = r.json()["esearchresult"]
            out = {"count": int(res["count"]), "ids": res["idlist"]}
            cf.write_text(json.dumps(out))
            return out
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(1.0 * (attempt + 1))


def forms_for(name: str, surface: dict) -> list[dict]:
    """Surface forms of one canonical; blocklisted names have none, so the
    canonical itself is used and tagged as such."""
    if name in surface:
        return [{"text": f.text, "origin": f.origin} for f in surface[name]]
    return [{"text": name, "origin": "canonical_blocklisted"}]


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    surface = psf.build_surface_forms()
    diseases = [d["query_name"] for d in json.loads(DISEASES.read_text())]
    targets = TARGETS

    out = {}
    for i, name in enumerate(targets, 1):
        forms = forms_for(name, surface)
        rec = {"blocklisted": name not in surface, "forms": {}}
        for f in forms:
            solo = esearch(f'"{f["text"]}"[Title/Abstract]', SOLO_CAP)
            queries = [
                (dis, f'("{f["text"]}"[Title/Abstract]) AND ("{dis}"[Title/Abstract])')
                for dis in diseases
            ]
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                results = list(pool.map(lambda qq: esearch(qq[1], PAIR_CAP), queries))
            pairs = {dis: r["ids"] for (dis, _), r in zip(queries, results) if r["ids"]}
            rec["forms"][f["text"]] = {
                "origin": f["origin"],
                "solo_count": solo["count"],
                "solo_ids": solo["ids"],
                "pair_hits": len(pairs),
                "pair_pmids": sorted({p for v in pairs.values() for p in v}),
                "pairs": pairs,
            }
            print(f'[{i}/{len(targets)}] {name} | {f["text"]}  solo={solo["count"]} '
                  f'pair_hits={len(pairs)}', flush=True)
        out[name] = rec

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "queries.json").write_text(json.dumps(out, indent=1))
    print("wrote", OUT_DIR / "queries.json")


if __name__ == "__main__":
    main()
