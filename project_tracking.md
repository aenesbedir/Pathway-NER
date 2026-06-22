# NER Pipeline — Project Tracking

## Goal
Fine-tune `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` for Named Entity Recognition of **Metabolic Pathways** in biomedical literature, using a distant supervision + local LLM hybrid approach.

> **Bigger picture:** Combine this pathway NER model with an existing disease NER model (off-the-shelf), then apply a relation extraction model to find pathway↔disease associations evidenced by literature. End goal: a database linking metabolic pathways to diseases with source PMIDs. Current project covers only the pathway NER step.

---

## Architecture Overview

```
KEGG API  ──┐
            ├──► Pathway → [PMIDs + synonyms]  ──► PubMed/PMC abstracts + full-text
Reactome ───┘                                        (cached to disk)
Recon    ───┘                                              │
                                             Step 2: SpaCy PhraseMatcher
                                             (exact + synonym, char offsets)
                                                           │
                                             Step 3: LLM variant extraction
                                             (sentence-level, Python API,
                                              re-verified against source text)
                                                           │
                                             Step 4: HF fast tokenizer alignment
                                             (word_ids(), sliding window,
                                              B/I/O + -100 for special tokens)
                                                           │
                                             Step 5: Filter → deduplicate →
                                             stratified split → HF JSON datasets
```

---

## Status

### ✅ Step 1a — KEGG Fetch (`fetch_kegg.py`)
- Fetches all human **Metabolism** class pathways from the KEGG REST API
- Parses canonical names, synonyms (split from compound names like `A / B`), and PMIDs from REFERENCE sections
- Resumable via `data/raw/kegg_cache/` (one `.txt` file per pathway entry)
- **Output:** `data/raw/kegg_pathways.jsonl`
- **Results:** 86 pathways · 524 PMIDs · avg 6.1 PMIDs/pathway · 0 failures

### ✅ Step 1b — Reactome Fetch (`fetch_reactome.py`)
- Downloads two bulk hierarchy files (`ReactomePathways.txt`, `ReactomePathwaysRelation.txt`) to build the full pathway tree
- BFS walk from Metabolism root `R-HSA-1430728` collects all 335 descendant pathways
- Fetches detail records via `/ContentService/data/query/{stId}` for name synonyms and PMIDs
- Resumable via `data/raw/reactome_cache/` (one `.json` file per pathway)
- **Output:** `data/raw/reactome_pathways.jsonl`
- **Results:** 335 pathways · 933 PMIDs · avg 2.8 PMIDs/pathway · 0 failures

### 📄 Reference Data
- `unique_pathways_from_recon.json` — 99 metabolic pathway names from the Recon human metabolic network model (Recon2/3D subsystem names). ~90 are usable as synonym variants; ~9 are model-internal artifacts to filter out during Step 1d.

---

### ✅ Step 1c — PubMed / PMC Abstract + Full-Text Fetch (`fetch_pubmed.py`)
- Deduplicated 1,192 unique PMIDs across KEGG + Reactome outputs
- Batch-fetched PubMed abstracts (200/request) using NCBI E-utilities with API key
- Extracted PMC IDs from PubMed XML `<ArticleIdList>` (no elink call needed)
- Fetched PMC Open Access full-text (JATS XML) for articles with PMC IDs; extracted body paragraphs
- Resumable via `data/raw/pubmed_cache/` (1,191 abs + 386 pmc JSON files)
- Added HTML fallback for publisher-blocked PMC articles
- **Output:** `data/raw/abstracts.jsonl`
- **Results:** 1,122 records · 1,109 with abstract · 360 with full-text · 69 skipped (no text)
- All cache files are JSON (no XML/HTML persisted)
- Analysis: `analysis/pubmed_year_distribution.md`, `analysis/data_summary.md`

---

### ✅ Step 1d — Mapping (`build_mapping.py`)
- KEGG and Reactome kept separate (no cross-database merging — no mapping exists between the two databases)
- Enriched synonyms with Recon subsystem names (89 usable, 9 artifacts filtered)
- Joined (pathway, pmid) pairs with `abstracts.jsonl` — stored pmid reference only, not text
- **Output:** `data/processed/pathway_abstract_pairs.jsonl`
- **Results:** 1,366 pairs · 51 pathways skipped (no PMIDs) · 91 PMIDs skipped (no text)

### ✅ Step 2 — Rule-Based Matching (`match_exact.py`)
- SpaCy `en_core_sci_sm` PhraseMatcher (`attr="LOWER"`) over abstract + full_text
- Match canonical name + all synonyms per pathway; longest span wins on overlap
- All pairs written to output (zero-span pairs pass to Step 3)
- **Output:** `data/processed/exact_matches.jsonl`
- **Results:** 1,366 pairs · 86 with spans (6.3%) · 1,280 no spans → Step 3 · 228 total spans
- Low match rate expected: KEGG/Reactome links are gene/enzyme based, not pathway-name based

---

### 🔬 LLM Extraction Experiment (`extract_pathway_from_db.py`)

Separate experiment using a pre-built disease-pathway dataset to evaluate and
refine LLM prompting before applying to the main pipeline (Step 3).

**Input:** `data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json`
- 450 records, each with: `disease`, `pathway`, `abstract`, `pmid`, `mesh_descriptors`
- Pre-built using PubMed API; covers known pathway↔disease article pairs
- Useful for prompt benchmarking since ground-truth pathway associations are known

**Model:** `qwen2.5:7b` via Ollama (local, RTX 4060 8GB VRAM)
- Chosen for: best JSON output discipline among 7B models, fits in 8GB VRAM
- All LLM responses verified verbatim against source text before accepting

**Prompt versions benchmarked** (see `prompts/pathway_extraction.py`):

| Version | Strategy | Found | Notes |
|---|---|---|---|
| V1 (active) | Zero-shot with rules | 296/450 (65.8%) | Best precision, fewest false positives |
| V2 | + word-order variant rule | 294/450 (65.3%) | Slight regression — rule confused model |
| V3 | Few-shot (5 examples + entity def) | 198/450 (44.0%) | Significant regression on 7B model |

- V3 confirmed finding from research: few-shot helps GPT-4/70B but hurts smaller models
- V1 is active; V2 and V3 kept in `prompts/pathway_extraction.py` for future model testing
- **Next improvement:** Option B — token overlap post-processing as deterministic fallback (not yet implemented)

**Outputs:**
- `data/processed/db_with_extracted_pathways.json` — V1 results (296 matches)
- `data/processed/db_with_extracted_pathways_v2.json` — V2 results (294 matches)
- `data/processed/db_with_extracted_pathways_v3.json` — V3 results (198 matches)

---

## Planned

### Step 3 — LLM Variant Extraction (`match_llm.py`)
- For 1,280 pairs with no spans from Step 2, call Ollama (`qwen2.5:7b`) via REST API
- Use V1 prompt from `prompts/pathway_extraction.py`
- Re-verify every LLM-returned string exists verbatim in source text before accepting
- Resumable via `data/raw/llm_cache/` (per-pair JSON cache)
- **Output:** `data/processed/all_matches.jsonl` (Step 2 spans + LLM spans, all 1,366 pairs)

### Step 4 — Token Alignment & BIO Tagging (`tag_bio.py`)
- HF fast tokenizer `word_ids()` for subword-accurate alignment
- Sliding window with overlap for abstracts near the 512-token BiomedBERT limit
- Special tokens (`[CLS]`, `[SEP]`) get label `-100`
- Per-token label sequences: `B-Pathway`, `I-Pathway`, `O`

### Step 5 — Dataset Compilation (`build_dataset.py`)
- Filter out samples with zero positive labels
- Stratified split by pathway (not random) to prevent data leakage
- Write `train.json`, `val.json`, `test.json` in HF NER format
