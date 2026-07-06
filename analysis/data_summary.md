# Data Summary

Summary of all data collected and processed across pipeline phases.

---

## Phase 2 — PubMed Pathway×Disease Corpus (Jul 2026)

### File Overview

```
data/
├── raw/
│   ├── selected_diseases.json          — 98 MeSH diseases (with synonyms)
│   ├── mesh_all_diseases.json          — full MeSH disease descriptor list
│   ├── pathway_disease_pairs.json      — 9,604 pairs searched; 1,959 with hits
│   └── articles.json                   — 10,329 articles (466 MB)
└── processed/
    └── exact_matches.jsonl             — 19,513 (pmid, pathway_id) records with spans
```

---

### selected_diseases.json

**98 diseases** — manually curated subset of MeSH C-tree descriptors across 6 categories (cancer, metabolic, neurological, cardiovascular, inflammatory, genetic).

Each record:
```json
{
  "mesh_id": "68001943",
  "name": "Breast Neoplasms",
  "synonyms": ["Breast Cancer", "Mammary Carcinoma", ...],
  "category": "cancer"
}
```

Synonym lists come directly from MeSH entry terms (avg ~15 synonyms/disease).

---

### pathway_disease_pairs.json

**9,604 pairs** (98 pathways × 98 diseases) searched via PubMed ESearch.
Query template: `("pathway name"[Title/Abstract]) AND ("disease name"[Title/Abstract])`

| Metric | Value |
|---|---|
| Total pairs searched | 9,604 |
| Pairs with ≥1 hit | 1,959 (20.4%) |
| Pairs with 0 hits | 7,645 (79.6%) |
| Unique PMIDs | 10,329 |
| Avg articles per hit pair | 6.8 |
| Median articles per hit pair | 3 |
| Max articles per pair | 20 (retmax cap) |

---

### articles.json

**10,329 articles** — one record per PMID. Fetched via PubMed EFetch (metadata + abstract) and PMC EFetch (JATS XML full text).

Each record schema:
```json
{
  "pmid": "32303640",
  "pmcid": "PMC7278340",
  "doi": "...",
  "title": "...",
  "year": 2020,
  "journal": "...",
  "pub_types": ["Journal Article"],
  "keywords": [...],
  "mesh_headings": [{"term": "...", "ui": "...", "major": false, "qualifiers": [...]}],
  "abstract": "...",
  "sections": [...],
  "full_text": "...",
  "has_full_text": true
}
```

| Metric | Value |
|---|---|
| Total articles | 10,329 |
| With full text (PMC) | 5,837 (56.5%) |
| Abstract only | 4,492 (43.5%) |
| Avg abstract length | ~1,500 chars |
| Avg full-text length | ~32,000 chars |
| Total file size | 466 MB |

---

### exact_matches.jsonl (Phase 2)

**19,513 records** — one per (pmid, pathway_id) pair where a match was found. Built by SpaCy PhraseMatcher over KEGG + Reactome canonical names + synonyms (MIN_TERM_LEN=4).

| Metric | Value |
|---|---|
| Total records | 32,862 |
| Records with spans | 31,544 (96.0%) |
| Records with no spans | 1,318 |
| Total spans | 129,305 |

> **Note:** Generic single-word terms (e.g. "metabolism" from a Reactome entry) can inflate span counts. Consider applying a MIN_WORDS=2 filter before BIO tagging if noise becomes an issue.

Each record schema:
```json
{
  "pmid": "32303640",
  "pathway_id": "hsa00010",
  "spans": [
    {"start": 42, "end": 67, "text": "pentose phosphate pathway", "source": "abstract"}
  ]
}
```

---

## Phase 1 — Original Small Corpus (Steps 1a–1c)

---

## File Overview

```
data/
├── raw/
│   ├── kegg_pathways.jsonl                                          — 86 pathway entries
│   ├── reactome_pathways.jsonl                                      — 335 pathway entries
│   ├── abstracts.jsonl                                              — 1,122 article entries
│   ├── extracted_disease_pathway_db_disease_pathway_just_abstracts.json — 450 disease-pathway pairs
│   ├── pubmed_cache/                                                — gitignored
│   │   ├── abs_{pmid}.json       — 1,191 files
│   │   └── pmc_PMC{id}.json      — 386 files
│   ├── llm_cache/                                                   — gitignored, 1,280 files
│   └── llm_cache_db/                                                — gitignored, 450 files
└── processed/
    ├── pathway_abstract_pairs.jsonl        — 1,366 (pathway, pmid) pairs (Step 1d)
    ├── exact_matches.jsonl                 — 1,366 pairs with rule-based spans (Step 2)
    ├── all_matches.jsonl                   — 1,662 pairs, all sources merged (Steps 2+3+DB)
    ├── db_with_extracted_pathways.json     — V1 LLM results on disease-pathway DB (296/450)
    ├── db_with_extracted_pathways_v2.json  — V2 results (294/450)
    └── db_with_extracted_pathways_v3.json  — V3 results (198/450)
```

All cache files are JSON. Cache directories are gitignored (regenerable by re-running fetch scripts).

---

## abstracts.jsonl

**1,122 records** — one per PMID that has at least abstract or full-text.

Each record schema:
```json
{
  "pmid": "32303640",
  "title": "...",
  "abstract": "...",
  "pmc_id": "PMC7278340",
  "full_text": "..."
}
```

| Metric | Count |
|---|---|
| Total records | 1,122 |
| With abstract | 1,109 (98.8%) |
| With full-text | 360 (32.1%) |
| With both | 278 (24.9%) |
| Abstract only | 831 (74.5%) |

### Text Volume
| Source | Avg length | Total |
|---|---|---|
| Abstracts | 1,367 chars | 1.5 MB |
| Full-texts | 23,141 chars | 6.6 MB |
| Combined | — | ~8.1 MB |

---

## pubmed_cache/ Breakdown

### abs_{pmid}.json — 1,191 files

- 1,191 PMIDs were fetched from PubMed
- 1,109 returned abstract text → written to `abstracts.jsonl`
- **69 have empty abstract** (metadata-only PubMed records, mostly pre-2000 articles) → excluded from `abstracts.jsonl`
- 0 records in `abstracts.jsonl` are missing a cache file

### pmc_PMC{id}.json — 386 files

- 386 PMIDs had a PMC ID (extracted from PubMed XML `ArticleIdList`)
- 360 returned full-text → written to `abstracts.jsonl`
- **26 have empty full_text** — completely paywalled (neither XML API nor HTML page returned body content)

Full list of PMCIDs with no retrievable full-text:
```
PMC1222616  PMC2779761  PMC3648719  PMC4867368
PMC123963   PMC2812977  PMC3979397  PMC5087052
PMC124149   PMC2975232  PMC4226123  PMC5114413
PMC127317   PMC3181353  PMC4315926  PMC5544388
PMC135753   PMC3220592  PMC4415017  PMC5594697
PMC208725   PMC3276472  PMC5602410
PMC210415   PMC2135190
PMC2674699  PMC124149
```

---

## Full-Text Retrieval Strategy

Two methods were used to retrieve full-text, in order:

1. **NCBI efetch XML** — works for PMC Open Access articles; publisher provides JATS XML with `<body>` element
2. **HTML fallback** — for publisher-blocked articles (XML returns metadata only), the HTML page at `pmc.ncbi.nlm.nih.gov/articles/{PMCID}/` is fetched and the `<section class="body main-article-body">` is parsed

| Method | Articles retrieved |
|---|---|
| XML only | 154 |
| HTML fallback (additional) | 206 |
| **Total** | **360** |

---

## all_matches.jsonl

**1,662 records** — the main annotation file fed into Step 4 (BIO tagging). Merges three sources:

| Source | Records | How spans were found |
|---|---|---|
| Step 2 rule-based | 1,366 | SpaCy PhraseMatcher on KEGG/Reactome pairs |
| Step 3 LLM | +0 new records (spans added to existing) | qwen2.5:7b via Ollama |
| Source 3 DB merge | +296 new records | LLM on disease-pathway DB, offsets resolved |
| **Total** | **1,662** | |

560 records have at least one span · 1,102 have no spans (will be filtered in Step 5)  
704 total spans · 318 unique span texts · 571 from abstract · 133 from full_text

Each record schema:
```json
{
  "pathway_id": "hsa00030",
  "source": "kegg",
  "pmid": "16788179",
  "spans": [
    {"start": 42, "end": 68, "text": "pentose phosphate pathway", "source": "abstract"}
  ]
}
```

**Record-level `source`** — which database the pathway came from:
- `"kegg"` — KEGG human metabolism pathways
- `"reactome"` — Reactome metabolism hierarchy
- `"recon3d"` — disease-pathway DB records whose pathway name did not map to a KEGG/Reactome ID

**Span-level `source`** — which part of the article the span was found in:
- `"abstract"` — character offsets index into the `abstract` field of `abstracts.jsonl`
- `"full_text"` — character offsets index into the `full_text` field (offsets can be very large)
