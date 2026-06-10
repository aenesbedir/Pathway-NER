# NER Pipeline — Project Tracking

## Goal
Fine-tune `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` for Named Entity Recognition of **Metabolic Pathways** in biomedical literature, using a distant supervision + local LLM hybrid approach.

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

## Planned

### ✅ Step 1c — PubMed / PMC Abstract + Full-Text Fetch (`fetch_pubmed.py`)
- Deduplicated 1,192 unique PMIDs across KEGG + Reactome outputs
- Batch-fetched PubMed abstracts (200/request) using NCBI E-utilities with API key
- Extracted PMC IDs from PubMed XML `<ArticleIdList>` (no elink call needed)
- Fetched PMC Open Access full-text (JATS XML) for articles with PMC IDs; extracted body paragraphs
- Resumable via `data/raw/pubmed_cache/` (batch XMLs + per-article PMC XMLs)
- **Output:** `data/raw/abstracts.jsonl`
- **Results:** 1,112 records · 1,109 with abstract · 154 with full-text · 80 skipped (no text)

### Step 1d — Mapping & Merge (`build_mapping.py`)
- Join KEGG + Reactome records on shared pathway names and KEGG cross-references
- Merge synonyms across sources (KEGG names, Reactome names, Recon subsystem names)
- Filter Recon artifact entries (`"intracellular demand"`, `"exchange/demand reaction"`, etc.)
- Produce `(pathway_id, canonical_name, all_synonyms[], pmid, abstract_text)` pairs
- **Output:** `data/processed/pathway_abstract_pairs.jsonl`

### Step 2 — Rule-Based Matching (`match_exact.py`)
- SpaCy `PhraseMatcher` with `attr="LOWER"` over each abstract
- Match canonical name + all synonyms for the paired pathway
- Output character-level span annotations

### Step 3 — LLM Variant Extraction (`match_llm.py`)
- For sentences with no span found after Step 2, call a local LLM (Ollama Python API)
- Prompt: extract pathway name variant as strict JSON list
- Re-verify every LLM-extracted string has an exact character span in the source sentence before accepting
- Merge with Step 2 output

### Step 4 — Token Alignment & BIO Tagging (`tag_bio.py`)
- HF fast tokenizer `word_ids()` for subword-accurate alignment
- Sliding window with overlap for abstracts near the 512-token BiomedBERT limit
- Special tokens (`[CLS]`, `[SEP]`) get label `-100`
- Per-token label sequences: `B-Pathway`, `I-Pathway`, `O`

### Step 5 — Dataset Compilation (`build_dataset.py`)
- Filter out samples with zero positive labels
- Stratified split by pathway (not random) to prevent data leakage
- Write `train.json`, `val.json`, `test.json` in HF NER format
