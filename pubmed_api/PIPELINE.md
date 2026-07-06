# PubMed Pathway–Disease Pipeline

Goal: build a corpus of PubMed articles linking **Recon3D metabolic pathways** to
**diseases** (cancer, neurodegenerative, metabolic) for downstream relation extraction
and NER training data expansion.

---

## Architecture

```
fetch_mesh_diseases.py          fetch MeSH disease descriptors by tree prefix
        ↓
select_diseases.py              curate ~100 target diseases
        ↓
fetch_pathway_disease_pairs.py  PubMed co-occurrence search (pathway × disease)
        ↓
fetch_articles.py               fetch full text (PMC) or abstract (PubMed)
        ↓
data/raw/articles.jsonl         final corpus — ready for NER / RE annotation
```

---

## Scripts

### `fetch_mesh_diseases.py`
Fetches MeSH disease descriptors for one or more tree prefixes via NCBI E-utilities
(ESearch → EFetch plain text → parse).

```bash
# Fetch metabolic diseases (C18) — already done
python3 pubmed_api/fetch_mesh_diseases.py --trees C18

# Fetch cancer (C04) and neurodegenerative (C10.574) — already done
python3 pubmed_api/fetch_mesh_diseases.py --trees C04 C10.574
```

**Outputs** (one file per tree + combined if multiple):
- `data/raw/mesh_C18_diseases.json`   — 334 metabolic diseases
- `data/raw/mesh_C04_diseases.json`   — 455 cancer diseases
- `data/raw/mesh_C10_574_diseases.json` — 77 neurodegenerative diseases
- `data/raw/mesh_all_diseases.json`   — all combined (deduplicated)

**Cache:** `data/raw/mesh_cache/`

---

### `select_diseases.py`
Curates a focused list of ~100 diseases from the fetched MeSH data covering three
categories. Falls back to a direct NCBI name lookup for entries not in the cached
tree files.

```bash
python3 pubmed_api/select_diseases.py
```

**Output:** `data/raw/selected_diseases.json`
Fields per entry: `mesh_id, name, synonyms[], tree_numbers[], category, query_name`

**Current selection:** 98 diseases — 37 cancer, 28 neurodegenerative, 33 metabolic

---

### `fetch_pathway_disease_pairs.py`
For each (Recon3D pathway × selected disease) pair, runs a PubMed ESearch query:
`("pathway"[Title/Abstract]) AND ("disease"[Title/Abstract])`

Collects PMIDs (capped at 20 per pair). With `--dry-run` skips abstract fetching.

```bash
# Full run
python3 pubmed_api/fetch_pathway_disease_pairs.py \
    --diseases data/raw/selected_diseases.json

# Dry run (search only, no abstracts)
python3 pubmed_api/fetch_pathway_disease_pairs.py \
    --diseases data/raw/selected_diseases.json --dry-run

# Test with first N diseases
python3 pubmed_api/fetch_pathway_disease_pairs.py \
    --diseases data/raw/selected_diseases.json --top 5 --dry-run
```

**Inputs:**
- `unique_pathways_from_recon.json` — 98 Recon3D pathway names
- `data/raw/selected_diseases.json` (or custom `--diseases` file)

**Output:** `data/raw/pathway_disease_pairs.json`
```json
[
  {
    "pathway": "oxidative phosphorylation",
    "disease_name": "Alzheimer Disease",
    "disease_mesh_id": "68000537",
    "disease_category": "neurodegenerative",
    "pmids": ["12345678", "87654321"]
  }
]
```

**Cache:** `data/raw/pair_cache/` (one JSON per pair — resumable)

---

### `fetch_articles.py`
For every PMID in `pathway_disease_pairs.json`:
1. ELink pubmed → pmc to find a PMCID
2. If PMCID exists → EFetch PMC JATS XML → parse full text + abstract
3. Else → EFetch PubMed abstract XML

```bash
python3 pubmed_api/fetch_articles.py \
    --pairs data/raw/pathway_disease_pairs.json
```

**Output:** `data/raw/articles.json` — JSON array:
```json
[
  {
    "pmid":          "12345678",
    "pmcid":         "PMC1234567",
    "doi":           "10.1016/...",
    "title":         "...",
    "year":          2021,
    "journal":       "Nature Metabolism",
    "pub_types":     ["Journal Article"],
    "keywords":      ["oxidative phosphorylation"],
    "mesh_headings": [
      {"term": "Alzheimer Disease", "ui": "D000544", "major": true, "qualifiers": ["metabolism"]}
    ],
    "abstract":      "...",
    "sections": [
      {"label": "Introduction", "text": "..."},
      {"label": "Results",      "text": "..."}
    ],
    "full_text":     "...",
    "has_full_text": true
  }
]
```

**Cache:** `data/raw/article_cache/` (elink, pmc XML, pubmed abstract — all cached)

---

## Linkage / Joining

To reconstruct which articles belong to which pathway–disease pair:

```python
import json

pairs = json.load(open("data/raw/pathway_disease_pairs.json"))
articles = {
    r["pmid"]: r
    for line in open("data/raw/articles.jsonl")
    for r in [json.loads(line)]
}

for pair in pairs:
    for pmid in pair["pmids"]:
        article = articles.get(pmid)
        if article:
            print(pair["pathway"], pair["disease_name"], article["has_full_text"])
```

---

## Run order (full pipeline)

```bash
cd /home/enes/NER-pipeline

# Step 1 — already done
python3 pubmed_api/fetch_mesh_diseases.py --trees C18
python3 pubmed_api/fetch_mesh_diseases.py --trees C04 C10.574
python3 pubmed_api/select_diseases.py

# Step 2 — run next (~50 min for 9,604 pairs)
python3 pubmed_api/fetch_pathway_disease_pairs.py \
    --diseases data/raw/selected_diseases.json

# Step 3 — run after step 2
python3 pubmed_api/fetch_articles.py

# Update stats after each step
python3 pubmed_api/compute_stats.py
```

---

## Environment

- Python: `/home/enes/sci-usage/venv310/bin/python3`
- Working dir: `/home/enes/NER-pipeline`
- API key env var: `NCBI_API_KEY` (fallback hardcoded in each script)
- Rate limit: ~3 req/s with API key (SLEEP = 0.34 s between calls)
