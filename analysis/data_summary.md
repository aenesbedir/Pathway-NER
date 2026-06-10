# Data Summary

Summary of all data collected and analysed in Steps 1a–1c.

---

## File Overview

```
data/
├── raw/
│   ├── kegg_pathways.jsonl       — 86 entries
│   ├── reactome_pathways.jsonl   — 335 entries
│   ├── abstracts.jsonl           — 1,122 entries
│   └── pubmed_cache/
│       ├── abs_{pmid}.json       — 1,191 files (one per fetched PMID)
│       └── pmc_PMC{id}.json      — 386 files (one per PMC article)
└── processed/                    — empty (Step 1d output will go here)
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
