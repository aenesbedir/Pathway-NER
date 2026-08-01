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

### 🔬 LLM Extraction Experiment (`llm/extract_pathway_from_db.py`)

Separate experiment using a pre-built disease-pathway dataset to evaluate and
refine LLM prompting before applying to the main pipeline (Step 3).

**Input:** `data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json`
- 450 records, each with: `disease`, `pathway`, `abstract`, `pmid`, `mesh_descriptors`
- Pre-built using PubMed API; covers known pathway↔disease article pairs
- Useful for prompt benchmarking since ground-truth pathway associations are known

**Model:** `qwen2.5:7b` via Ollama (local, RTX 4060 8GB VRAM)
- Chosen for: best JSON output discipline among 7B models, fits in 8GB VRAM
- All LLM responses verified verbatim against source text before accepting

**Prompt versions benchmarked** (see `llm/prompts/pathway_extraction.py`):

| Version | Strategy | Found | Notes |
|---|---|---|---|
| V1 (active) | Zero-shot with rules | 296/450 (65.8%) | Best precision, fewest false positives |
| V2 | + word-order variant rule | 294/450 (65.3%) | Slight regression — rule confused model |
| V3 | Few-shot (5 examples + entity def) | 198/450 (44.0%) | Significant regression on 7B model |

- V3 confirmed finding from research: few-shot helps GPT-4/70B but hurts smaller models
- V1 is active; V2 and V3 kept in `llm/prompts/pathway_extraction.py` for future model testing
- **Next improvement:** Option B — token overlap post-processing as deterministic fallback (not yet implemented)

**Outputs:**
- `data/processed/db_with_extracted_pathways.json` — V1 results (296 matches)
- `data/processed/db_with_extracted_pathways_v2.json` — V2 results (294 matches)
- `data/processed/db_with_extracted_pathways_v3.json` — V3 results (198 matches)

---

### ✅ Step 3 — LLM Variant Extraction (`llm/match_llm.py`)
- For 1,280 pairs with no spans from Step 2, called Ollama (`qwen2.5:7b`) via REST API
- Used V1 prompt imported from `llm/prompts/pathway_extraction.py`
- Re-verified every LLM-returned string verbatim against source text before accepting
- Resumable via `data/raw/llm_cache/` (per-pair JSON cache, 87 pre-cached from earlier run)
- **Results:** 178 additional pairs found by LLM · 144 hallucinations dropped · 12 min runtime

### ✅ Source 3 Merge — DB Spans (`llm/merge_db_spans.py`)
- Converted `db_with_extracted_pathways.json` (V1 results) into character-offset spans
- Matched pathway names to KEGG/Reactome IDs via normalized + synonym lookup
- Unmatched pathway names (Recon3D-specific names) assigned synthetic `db__` IDs with `source: "recon3d"`
- Appended 296 new records to `all_matches.jsonl`
- **Results:** 162 mapped to KEGG/Reactome · 134 assigned recon3d source · 0 skipped

**Final `data/processed/all_matches.jsonl`:**

| Source | Records with spans | Notes |
|---|---|---|
| Step 2 (rule-based) | 86 | SpaCy PhraseMatcher |
| Step 3 (LLM) | 178 | qwen2.5:7b via Ollama |
| Source 3 (DB merge) | 296 | disease-pathway DB, V1 prompt |
| **Total** | **560** | 704 spans · 318 unique span texts |

Record-level `source` field values: `"kegg"`, `"reactome"`, `"recon3d"`  
Span-level `source` field values: `"abstract"`, `"full_text"`

---

## Completed

### ✅ Step 4 — Token Alignment & BIO Tagging (`preprocessing/tag_bio.py`)
- Loaded `all_matches.jsonl` + `abstracts.jsonl`; supplemented with DB file for recon3d PMIDs
- Grouped spans by pmid; abstract spans → full abstract, full-text spans → ±500 char window
- Tokenized with BiomedBERT fast tokenizer (`AutoTokenizer`); used `word_ids()` + `offset_mapping` for alignment
- First subword of each word gets real BIO label; continuations and special tokens get `-100`
- Nearby full-text spans merged into the same window to avoid redundant examples
- **Output:** `data/processed/bio_tags.jsonl`
- **Results:** 597 records · 488 from abstracts · 109 from full-text windows · 684 B-Pathway · 1,401 I-Pathway tokens · 98.6% O (expected imbalance)

### ✅ Step 5 — Dataset Compilation (`preprocessing/build_dataset.py`)
- Filtered 1 record with no positive labels after tokenization (truncation edge case)
- Stratified split by pathway (primary pathway_id) with seed=42 — all records for a pathway go to the same split to prevent data leakage
- Ratios: 80% train / 10% val / 10% test applied at pathway level
- **Output:** `data/processed/train.jsonl`, `val.jsonl`, `test.jsonl`
- **Results:**

| Split | Pathways | Records | Positive labels |
|---|---|---|---|
| train | 148 | 502 | 1,708 |
| val | 18 | 44 | 224 |
| test | 19 | 50 | 153 |
| **Total** | **185** | **596** | **2,085** |

### 📁 Code reorganisation
- All pipeline scripts moved to `preprocessing/` (fetch_kegg, fetch_reactome, fetch_pubmed, build_mapping, match_exact, tag_bio, build_dataset)
- All LLM scripts remain in `llm/` (match_llm, extract_pathway_from_db, merge_db_spans, prompts/)
- `knowledge_base/nlp_concepts.md` created — running glossary of NLP concepts encountered

---

## Step 6 — Fine-tuning (`train.py`)

Fine-tunes `BertForTokenClassification` on train/val/test splits using HuggingFace `Trainer`.
All experiments tracked in `knowledge_base/model_experiments.md`.

### ✅ Run 001 — Baseline, all layers fine-tuned
- All layers fine-tuned (no freezing) — BiomedBERT pre-trained on same domain
- Weighted cross-entropy loss `[O=0.1, B=5.0, I=3.0]` to handle 98.6% O imbalance
- Early stopping on val F1 (patience=5); stopped at epoch 15, best at epoch 10
- **Test results:** F1=0.46 · Precision=0.40 · Recall=0.55
- **Saved to:** `models/pathway-ner/`
- **Key finding:** Precision too low (0.40) — class weights too aggressive, pushing too many false positives

### ✅ Run 002 — Reduced class weights `[0.1, 2.0, 1.5]`
- Precision dropped further (0.40 → 0.35), recall increased (0.55 → 0.62)
- Weight tuning is not the right lever — ruled out

### ✅ Run 003 — Freeze bottom 6 layers
- F1 dropped to 0.42, precision 0.33 — freezing hurts performance
- BiomedBERT lower layers need full adaptation even within same domain

### ✅ Run 004 — Freeze bottom 9 layers
- Worst result: F1=0.37, Precision=0.27 — clear trend: more freezing = worse
- Freezing strategy definitively ruled out

### Full results

| Run | Change | F1 | Precision | Recall |
|---|---|---|---|---|
| 001 | All layers, w=[0.1/5.0/3.0] | **0.46** | **0.40** | 0.55 |
| 002 | All layers, w=[0.1/2.0/1.5] | 0.45 | 0.35 | **0.62** |
| 003 | Freeze 6 layers | 0.42 | 0.33 | 0.57 |
| 004 | Freeze 9 layers | 0.37 | 0.27 | 0.59 |

**Best checkpoint: Run 001** (`models/pathway-ner/`)

### ✅ Error Analysis (`analysis/error_analysis.py`)
- Ran Run 001 on test set, decoded all predictions back to readable spans
- Output saved to `analysis/error_analysis.json` (per-record + summary)
- **Span-level:** TP=40, FP=41, FN=24 · P=0.49 · R=0.63 · F1=0.55

**Key findings:**
- Many false positives are legitimate pathway names missed by distant supervision (e.g. `"heme synthesis"`, `"cholesterol metabolism"`, `"glycolytic pathway"`) — **data quality is the root cause**
- Partial term false positives (`"sulfate"`, `"biosynthesis"`, `"metabolism"`) — model over-generalizes on pathway name components
- Tokenizer artifact: `"dermatan"` → `"dermat" + "##an"` causes consistent misses (11 FN for dermatan sulfate)
- Conclusion: improving the annotation pipeline will have more impact than further hyperparameter tuning

---

---

# Phase 2 — Corpus Expansion via PubMed Pipeline

**Motivation:** Error analysis of Phase 1 models showed data quality (noisy distant supervision labels, missing pathway names in annotation) is the primary bottleneck, not model capacity. Precision consistently low (0.27–0.40) across all four training runs. Phase 2 builds a much larger, higher-quality corpus by:
1. Collecting a broad disease list (cancer + neurodegenerative + metabolic) from MeSH
2. Querying PubMed for pathway–disease co-occurring articles at scale
3. Applying exact string matching to generate new span annotations

---

## Phase 2 Architecture

```
MeSH API (ESearch + EFetch)
  C18 (Metabolic), C04 (Cancer), C10.574 (Neurodegenerative)
         │
         ▼
fetch_mesh_diseases.py  ──►  834 MeSH disease descriptors (name + synonyms + tree numbers)
         │
         ▼
select_diseases.py  ──►  98 curated target diseases (selected_diseases.json)
                          37 cancer · 33 metabolic · 28 neurodegenerative
         │
         ▼
fetch_pathway_disease_pairs.py
  ("pathway"[Title/Abstract]) AND ("disease"[Title/Abstract])
  98 Recon3D pathways × 98 diseases = 9,604 pairs searched
         │
         ▼
fetch_articles.py
  ELink PMID → PMCID (batch) → PMC full text (JATS XML)
  + PubMed metadata (MeSH, year, DOI, keywords, journal, pub types)
         │
         ▼
preprocessing/match_exact.py  (SpaCy PhraseMatcher, same method as Phase 1 Step 2)
  + synonym expansion (TCA cycle, beta-oxidation, etc.)
  + Recon3D blocklist (non-literary subsystem names filtered)
         │
         ▼
data/processed/exact_matches.jsonl  ──►  22,017 records  (new NER training candidates)
```

---

## Phase 2 Steps

### ✅ Step P2-1 — Disease List from MeSH (`pubmed_api/fetch_mesh_diseases.py`)

Built and rewrote script to use NCBI ESearch + EFetch (NLM text format) instead of the NLM MeSH lookup API (which returned HTTP 400 for tree-prefix queries).

- **ESearch query:** `C18.*[Tree Number]` wildcard returns all numeric UIDs under a subtree
- **EFetch response:** plain text format (one record per numbered block); parsed name, Entry Terms (synonyms), Tree Number(s)
- Script supports `--trees` flag: can fetch multiple tree prefixes in one run
- Results deduplicated across trees; one JSON file saved per prefix + combined file if multiple

| Tree | Category | Descriptors |
|---|---|---|
| C18 | Metabolic / Nutritional Diseases | 334 |
| C04 | Neoplasms (Cancer) | 455 |
| C10.574 | Neurodegenerative Diseases | 77 |
| **Total unique** | — | **834** |

**Outputs:** `data/raw/mesh_C18_diseases.json`, `data/raw/mesh_C04_diseases.json`, `data/raw/mesh_C10_574_diseases.json`  
**Cache:** `data/raw/mesh_cache/`

---

### ✅ Step P2-2 — Disease Curation (`pubmed_api/select_diseases.py`)

Curated a focused list of ~100 high-relevance diseases from the 834 MeSH descriptors, covering three clinically important categories.

- **Output:** `data/raw/selected_diseases.json`
- **Results:** 98 diseases — 37 cancer · 33 metabolic · 28 neurodegenerative
- Fields per entry: `mesh_id`, `name`, `synonyms[]`, `tree_numbers[]`, `category`, `query_name`

---

### ✅ Step P2-3 — PubMed Co-occurrence Search (`pubmed_api/fetch_pathway_disease_pairs.py`)

For every (Recon3D pathway × selected disease) pair, queried PubMed with:
```
("pathway name"[Title/Abstract]) AND ("disease name"[Title/Abstract])
```

- 98 pathways × 98 diseases = **9,604 pairs** searched
- Capped at 20 PMIDs per pair to avoid flooding on broad terms
- Per-pair cache in `data/raw/pair_cache/` (resumable — process was interrupted and restarted; all results read from cache on final run)
- `--dry-run` flag skips article fetch; article fetching separated into `fetch_articles.py`

| Metric | Value |
|---|---|
| Total pairs searched | 9,604 |
| Pairs with ≥1 hit | 1,959 (20.4%) |
| Unique PMIDs | 10,329 |

| Category | Pair hits | Unique PMIDs |
|---|---|---|
| Cancer | 601 | 3,531 |
| Neurodegenerative | 573 | 2,667 |
| Metabolic | 785 | 4,399 |

**Output:** `data/raw/pathway_disease_pairs.json`

---

### ✅ Step P2-4 — Article Fetch (`pubmed_api/fetch_articles.py`)

For every unique PMID from Step P2-3:
1. **ELink** (batch POST, 25 PMIDs/request): PMID → PMCID
2. **PMC EFetch**: JATS XML → full text parsed section by section (label + paragraph text)
3. **PubMed EFetch**: abstract XML → title, abstract, year, journal, DOI, MeSH headings, pub types, keywords
4. Records assembled combining both sources; per-PMID cache for all three operations

| Metric | Value |
|---|---|
| Total articles | 10,329 |
| Has PMC full text | 5,837 (56.5%) |
| Abstract only | 4,492 |
| Has MeSH headings | 7,506 |
| Has DOI | 9,507 |

**Output:** `data/raw/articles.json`  
**Cache:** `data/raw/article_cache/` (elink + pubmed + pmc XML per PMID)

---

### ✅ Step P2-5 — Exact Matching on New Corpus (`preprocessing/match_exact.py`)

Same SpaCy PhraseMatcher approach as Phase 1 Step 2, now applied over the 10,329 newly fetched articles. Additions over Phase 1:
- **Synonym expansion** for Recon3D names with common literature variants (e.g. `"TCA cycle"` → `"citric acid cycle"`, `"beta-oxidation"` → `"fatty acid oxidation"`)
- **Recon blocklist**: 8 non-literary subsystem names excluded (e.g. `"miscellaneous"`, `"protein formation"`, `"intracellular demand"`)
- Matches cover both abstract and full_text fields with source tagged per span

**Output:** `data/processed/exact_matches.jsonl`  
**Results:** 22,017 records (pmid × pathway_id pairs with character-offset spans)

---

### ✅ Step P2-6 — BIO Tagging (`preprocessing/tag_bio.py`)

`tag_bio.py` güncellendi: `--matches`, `--articles`, `--output`, `--db` flag'leri eklendi; articles dosyası JSONL veya JSON array formatını otomatik algılıyor.

```bash
python3 preprocessing/tag_bio.py \
    --matches  data/processed/exact_matches.jsonl \
    --articles data/raw/articles.json \
    --output   data/processed/bio_tags_v2.jsonl \
    --db ""
```

| Metrik | Değer |
|---|---|
| Span'lı PMID | 8,886 |
| Span'sız atlandı | 1,443 |
| Artikel bulunamadı | 0 |
| Toplam kayıt | 41,754 |
| — abstract'tan | 8,415 |
| — full-text window'dan | 33,339 |

**Çıktı:** `data/processed/bio_tags_v2.jsonl`

---

### ✅ Step P2-7 — Dataset Build (`preprocessing/build_dataset.py`)

`build_dataset.py` güncellendi: `--input` ve `--outdir` flag'leri eklendi.

```bash
python3 preprocessing/build_dataset.py \
    --input  data/processed/bio_tags_v2.jsonl \
    --outdir data/processed/phase2
```

| Split | Pathway | Kayıt | Positive label |
|---|---|---|---|
| train | 57 | 37,766 | 134,081 |
| val | 7 | 1,311 | 4,765 |
| test | 8 | 2,624 | 12,182 |
| **Toplam** | **72** | **41,701** | **151,028** |

Phase 1 ile karşılaştırma: 596 → **41,701 kayıt** (70x artış), 2,085 → **151,028 positive label** (72x artış).

**Çıktı:** `data/processed/phase2/train.jsonl`, `val.jsonl`, `test.jsonl`

---

### ⚠️ Run 005 — Phase 2 Only (Durduruldu — Data Leakage Şüphesi)

`train.py` güncellendi: `--data-dir` ve `--output-dir` flag'leri eklendi.

```bash
python3 train.py \
    --data-dir  data/processed/phase2 \
    --output-dir models/pathway-ner-005
```

Eğitim epoch 13'e kadar çalıştı, sonra kullanıcı isteğiyle durduruldu. Checkpoint'ler korunuyor.

| Epoch | Val F1 | Precision | Recall |
|---|---|---|---|
| 9 | 0.969 | 0.947 | 0.993 |
| 10 | 0.974 | 0.956 | 0.992 |
| 11 | 0.977 | 0.962 | 0.993 |
| 12 | 0.980 | 0.966 | 0.994 |
| 13 | 0.980 | 0.967 | 0.994 |

**⚠️ Şüpheli durum:** Val F1 = 0.98 Phase 1'deki 0.49'a kıyasla çok yüksek. Muhtemel neden: aynı PMID'den üretilen abstract + full-text window kayıtları split sırasında farklı split'lere düşmüş olabilir (split pathway bazlı yapılıyor, PMID bazlı değil), bu da train ve val'da aynı metnin farklı window'larının bulunmasına yol açıyor → **data leakage**.

**Kaydedilen checkpoint'ler:** `models/pathway-ner-005/checkpoint-28332`, `checkpoint-30693`

---

## Phase 2 Status

| Step | Script | Status | Çıktı |
|---|---|---|---|
| P2-1: MeSH diseases | `pubmed_api/fetch_mesh_diseases.py` | ✅ Done | `mesh_*.json` (834 hastalık) |
| P2-2: Disease curation | `pubmed_api/select_diseases.py` | ✅ Done | `selected_diseases.json` (98) |
| P2-3: Pair search | `pubmed_api/fetch_pathway_disease_pairs.py` | ✅ Done | `pathway_disease_pairs.json` |
| P2-4: Article fetch | `pubmed_api/fetch_articles.py` | ✅ Done | `articles.json` (10,329) |
| P2-5: Exact matching | `preprocessing/match_exact.py` | ✅ Done | `exact_matches.jsonl` (22,017) |
| P2-6: BIO tagging | `preprocessing/tag_bio.py` | ✅ Done | `bio_tags_v2.jsonl` (41,754) |
| P2-7: Dataset build | `preprocessing/build_dataset.py` | ✅ Done | `phase2/{train,val,test}.jsonl` |
| P2-8: Run 005 | `train.py` | ⚠️ Durduruldu | checkpoint'ler var, devam edilecek |

**Sonraki adım (önce çözülmesi gereken):** Data leakage araştırması — `build_dataset.py`'de split stratejisi pathway bazlı, PMID bazlı değil. Aynı PMID'den gelen abstract ve full-text window'ları farklı split'lere düşebiliyor. Düzeltme: split'i **PMID bazlı** yapmak; tüm aynı PMID kayıtları aynı split'e gitsin, sonra Run 005'i yeniden başlat.

---

---

# Phase 3 — LLM-Based Variation-Aware Silver Labeling

**Motivation:** Distant supervision (exact matching) only captures ~37% of pathway
mentions in dense review abstracts; the golden set showed ~63% are surface
variations exact matching misses. Phase 3 replicates the golden-set annotation
approach at scale with a local LLM to generate **variation-aware silver labels**
for the whole corpus, then routes them through human review (doccano).

**Design (user-approved):**
- Guided prompt: full abstract in one call; hint the article's query pathway(s)
  + optionally the 98 Recon vocabulary. LLM returns **surface strings only**.
- **Canonical mapping done by us** (embedding + threshold), not the LLM.
- **Precision measured first** on the golden set before any scaling.
- Feasibility ladder: golden benchmark → 1k pilot → 10k full.
- Silver kept strictly separate from gold (`data/silver/` vs `playground/golden_set/`).

Related: `playground/golden_set/README.md`, `playground/exact_match_analysis.md`.

## Phase 3 Steps

### ✅ P3-0a — Silver data folder
- Created `data/silver/` with `README.md` documenting silver-vs-gold separation and
  span provenance (`source="llm_silver"`, `model`, `match_type`, `canonical`).

### ✅ P3-0b — Guided extraction (`llm/prompts/pathway_extraction_guided.py`, `llm/extract_guided.py`)
- Whole-abstract, single-call prompt hinting the article's query pathway(s) + optional
  98-name vocab block. Model returns **surface strings only**; canonical mapping deferred.
- `extract_guided()` grounds every surface to char offsets (verbatim, all occurrences),
  drops non-verbatim (hallucination filter). `temperature=0, seed=42` → deterministic.

### ✅ P3-0c — Precision baseline on golden set (`playground/golden_set/eval_llm_guided.py`)
- Offset-based scoring vs `golden_set.json`: TP (overlaps a gold pathway), FP_neg
  (overlaps a metabolite/out-of-vocab), UNLABELED (neither).
- Model: `qwen2.5:7b` (only model installed). Two prompt variants compared.

| Variant | Precision (distinct surface) | span:exact recall | span:variation recall | Verdict |
|---|---|---|---|---|
| no-vocab, **strict** rule | 0.82 / 0.90 | 11/11 (100%) | 2/6 (33%) | superseded |
| **no-vocab, lenient rule** | 0.82 / 0.90 | 11/11 (100%) | **4/6 (67%)** | **chosen** |
| with-vocab, strict rule | 1.00 | 11/11 (100%) | 0/6 (0%) | too conservative |
| with-vocab, lenient rule | 1.00 | 11/11 (100%) | 1/6 (17%) | too conservative |

Full 2×2 grid run (reports in `data/silver/eval_qwen7b_*.json`). The lenient rule lifts
variation recall in both vocab settings, but the 98-name list is the dominant recall-killer
(precision 1.00 at the cost of near-zero variation recall) — so no-vocab + lenient wins.

**Chosen config baked as default** (`extract_guided(..., lenient=True)`, `vocab=None`,
prompt "synonyms" wording): **no-vocab + lenient + synonyms**. Adding "synonyms (including a
compound's alternative chemical name)" to the task line recovered span:synonym 0→1/1 and
span:umbrella (conceptually right; the one synonym test case now passes); span-level catch
15→17/19, precision flat. `eval_llm_guided.py` default is now this config; `--strict`
reproduces the old baseline.

**Determinism caveat:** ollama is NOT fully deterministic run-to-run even at
`temperature=0, seed=42` (GPU batching). Same config varies by ±1-2 mentions between runs
(e.g. span:umbrella flips 0/1↔1/1). Robust, large-margin conclusions hold (no-vocab ≫
with-vocab; lenient > strict on variation); single-mention category deltas are run noise.
The 5-abstract golden set is too small to arbitrate them — firm numbers need the 1k pilot
or a larger golden set.

- **Chosen: no-vocab + lenient rule.** The 98-name list makes the 7B model over-conservative
  (recall collapses — same failure mode as the V3 few-shot regression). Query-pathway hints
  alone give the best balance.
- **Compound-name rule fix (user-spotted):** the strict rule "Do NOT return … metabolite or
  compound names" was wrongly suppressing pathway phrases *built from* a compound name. The
  lenient rule (`RULES_LENIENT`) keeps excluding a *bare* metabolite but explicitly keeps
  "<compound> metabolism / biosynthesis / synthesis of <compound> / formation of <compound>".
  Effect: **span:variation recall 33% → 67%** (now catches `formation of prostaglandin`,
  `cholecalciferol metabolism`) with **no precision change** and **zero new false positives**.
  Report: `data/silver/eval_qwen7b_novocab_lenient.json`.
- Precision is high: of 21 distinct surfaces, only genuine miss is `oxidative stress and
  inflammation`; the 2 FP_neg (`aminoacyl-tRNA biosynthesis`, `mitochondrial metabolism`)
  are exactly the two terms we deliberately scoped out — scope disagreement, not hallucination.
- **Remaining variation misses (2/6, after the lenient fix):** `arginine biosynthesis`
  (model returns only the canonical `arginine and proline metabolism` in the same sentence —
  a redundancy/dedup behaviour, not the compound rule) and `metabolism of androgens`
  (word-order reversal). These need the Phase 1 recall booster: a deterministic
  token-overlap / word-order fallback (cf. "Option B" in `pathway_extraction.py`) and/or a
  per-query-pathway synonym pass using the old vocab-guided V1 prompt.
- Reports: `data/silver/eval_qwen7b_novocab.json`, `data/silver/eval_qwen7b_vocab.json`.
### ✅ P3-0d — Larger-model benchmark (`qwen2.5:14b` vs `qwen2.5:7b`)
Pulled `qwen2.5:14b` (~9GB q4); ran the chosen config (no-vocab + lenient + synonyms) on
the golden set. Fits VRAM well enough — ~7s/abstract (36s for 5), feasible at scale
(1k ≈ 2h, 10k ≈ 20h). Report: `data/silver/eval_qwen14b_novocab_lenient.json`.

| Metric | qwen2.5:7b | qwen2.5:14b |
|---|---|---|
| span:exact recall | 11/11 | 11/11 |
| **span:variation recall** | **4/6 (67%)** | **4/6 (67%)** |
| precision (lenient) | ~0.90–0.92 | **0.95** |
| UNLABELED (borderline noise) | 9 | 3 |
| total mentions | ~33 | ~22 |
| run-to-run stability | noisy (±1–2) | very stable (identical) |

- **The bigger model does NOT close the variation gap** — same 4/6 on the core metric. The
  recall lever is the deterministic word-order/dedup fallback, needed regardless of model.
- **14b is cleaner/more precise** (0.95 vs 0.90; UNLABELED 9→3): it does not emit borderline
  terms like `oxidative stress and inflammation` or repeated `energy metabolism` → less noise
  for human review. Also far more stable run-to-run.
- **Decision: `qwen2.5:14b` chosen** for the pilot (cleaner silver → less doccano noise).

---

## Phase 3 / Faz 1 — 1k pilot
Plan: `~/.claude/plans/eventual-imagining-hippo.md`. Steps 1a→1d, golden-gated.

### ✅ P3-1a — Deterministic recall booster (`llm/booster.py`)
Model-free fallback for the two variation types both 7b and 14b miss. For each Recon
canonical it strips process words to get **content phrases**
(`arginine and proline metabolism` → `[arginine, proline]`), then scans for:
`<content> <process>` (→ `arginine biosynthesis`) and `<process> of <content>`
(→ `metabolism of androgens`). Requiring an adjacent process word is what preserves
precision — a bare metabolite (`...arginine, and aspartate levels`) never matches.

- **Scans all 90 Recon names, not just the article's query pathways.** Measured reason:
  PMID 11469814 mentions `metabolism of androgens` but was never retrieved by
  `androgen and estrogen synthesis and metabolism` — that canonical is absent from its 21
  query pathways, so a query-only scan structurally cannot find it. **Query pathways are an
  incomplete hint.**
- Refactor: `RECON_BLOCKLIST` / `RECON_SYNONYMS` extracted to **`preprocessing/recon_vocab.py`**
  (dependency-free single source of truth) so `llm/booster.py` reuses them without pulling in
  spacy. `match_exact.py` now imports from it — verified unchanged (`load_recon()` → 90).

**Gate result (14b, golden, `--booster`):** recall up, precision flat → **passed**.

| Metric | 14b | 14b + booster |
|---|---|---|
| **span:variation** | 4/6 (67%) | **5/6 (83%)** |
| enum:variation | 1/6 (17%) | 4/6 (67%) |
| precision (lenient) | 0.95 | 0.95 |
| TP / FP_neg / UNLABELED | 18 / 1 / 3 | 20 / 1 / 3 |

- **+2 TP, zero new false positives.** Report: `data/silver/eval_qwen14b_booster.json`.
- **Remaining miss (1/6): `formation of prostaglandin` → `eicosanoid metabolism`.** The
  booster structurally cannot bridge this: the canonical's content phrase is `eicosanoid`,
  the text says `prostaglandin` — a biochemical hyponym, not a string relation (same class as
  `cholecalciferol` = vitamin D3, which the LLM happened to catch). Closing it would mean
  hand-adding `prostaglandin` to `RECON_SYNONYMS` **because we saw it in the golden set** —
  i.e. fitting to the 5-abstract eval. **User decision: left open; 83% is enough.**

### ✅ P3-1b — Canonicalizer (`llm/canonicalize.py`)
Maps an **LLM** surface → one of the 90 Recon canonicals + match_type (booster spans already
carry their canonical, so only LLM spans go through this). Layers: exact → `RECON_SYNONYMS`
→ content-phrase overlap (reuses `booster.content_phrases`, handles the `<process> of X`
word order) → `unmapped`. No embeddings (see plan rationale).

**Gate result (19 golden `spans`): passed.**

| | |
|---|---|
| Correct when it commits | **16/16 (100%)** — zero wrong mappings |
| Coverage | 16/19 (84%) |
| `unmapped` (abstained) | 3/19 (16%) |

- ~~**Failure mode is abstention, not error** — it never maps to a wrong canonical.~~
  **⚠️ This claim was false — see the direction bug in P3-1e.** It held only because the
  19 golden spans happen to contain no synthesis/catabolism pair. A textbook case of the
  "5 abstracts cannot arbitrate" caveat.
- The 3 abstentions are exactly the predicted string-unbridgeable classes: chemical synonym
  (`cholecalciferol metabolism` → vitamin d), biochemical hyponym (`formation of
  prostaglandin` → eicosanoid), lipid subtype (`lysophospholipid metabolism` →
  glycerophospholipid). Umbrella terms (`neurotransmitter metabolism`) correctly abstain too.
- **Golden `unmapped` rate = 16%** — baseline for the embedding decision; compare against the
  pilot's rate before considering `sentence-transformers`.
- Tested on the 19 contiguous `spans`; enumeration parts have no standalone surface
  (`histidine metabolism` is factored inside `histidine and glutathione metabolism`), so they
  are not directly testable here.

### ✅ P3-1c — 1k pilot run (`llm/run_silver.py`)
1.000 abstract, `qwen2.5:14b`, chosen config + booster. **5 golden PMID excluded** (they were
all in the candidate pool; silver becomes training data, so including them would train on our
own eval set). Stratified by disease category, seed=42, abstract-only, resumable per-pmid
cache (`data/raw/llm_cache_silver/`, gitignored).

| Metric | Value |
|---|---|
| Runtime | 39 min (**2.4s/abstract**) — the 2h estimate was inflated by model load time |
| Spans | 1.996 (2.0 per abstract) |
| Source | 1.824 LLM / 172 booster (booster adds ~9%) |
| match_type | exact 999 (50%) · **unmapped 572 (29%)** · variation 251 (13%) · synonym 174 (9%) |
| `maybe_partial` | 31 (2%) — booster artifact stays marginal |

- **The payoff: variation + synonym = 425 spans (21%)** are mentions exact matching would miss
  entirely — plus an unknown share of `unmapped`. This is what the whole pipeline buys.
- **`unmapped` rose to 29%** (golden 16%, smoke20 22%). Inspected the 353 distinct surfaces:
  mostly **real pathway mentions we simply cannot name** — `kynurenine pathway` (24),
  `lipid metabolism` (18), `amino acid metabolism` (16), umbrella terms — all valid positives
  for a binary tagger. A minority are cheap canonicalizer gaps (`tricarboxylic acid (tca)
  cycle` + `citrate cycle` = 12 → citric acid cycle synonyms; `linoleic acid metabolism` (11)
  → Recon *has* `linoleate metabolism`; `oxidative phosphorylation (oxphos)` (10)). A small
  tail is genuine noise for the human to reject (`urea cycle disorders` (4) — a *disease*,
  `reductive stress` (5), `mnms` (4)).
- Since canonical drives no training label, these gaps are **analysis-only** and stay deferred.

**Output:** `data/silver/pilot_1k.jsonl`

### ✅ P3-1d — doccano export + annotation guide
- `llm/export_doccano.py` → `data/silver/pilot_1k_doccano.jsonl`: 1.000 documents, 1.996
  labels, single label type `Pathway`. Offset guard fired **zero** mismatches. `canonical` /
  `match_type` / `source` ride in `meta` as context only.
- **Review model:** annotators accept / reject / fix boundaries and may add missed spans.
  They do **not** assign canonical names (expert-level work, and irrelevant to a binary tagger).
- **`data/silver/ANNOTATION_GUIDE.md`** — derived from the golden set's scope rule.
  **One deliberate divergence:** golden files `biosynthesis of unsaturated fatty acids` under
  `out_of_vocab_pathways` because it does not map onto a Recon name — that is a *vocabulary*
  concern, not a *"is this a pathway mention"* concern. For the binary tagger such subtype
  names are **accepts**; only genuinely non-metabolic items (`aminoacyl-tRNA biosynthesis`,
  `mitochondrial metabolism`) are rejects.

**Gate → 10k decision:** pending human review of a sample (real span precision).

### ✅ P3-1e — Silver 1k analysis (`playground/silver_1k_analysis.py` → `playground/silver_1k_analyses.md`)

Descriptive analysis of the pilot. **Not an evaluation** — no ground truth on these 1,000
abstracts, so it says nothing about correctness; precision comes only from doccano.

**Headline — the near-lookup problem is broken.** Both sides counted on the *same* 1,000
abstracts, abstract-only (the 105-form figure in `exact_match_analysis.md` is corpus-wide
incl. full text, so it is not a fair comparator):

| | Exact matching | Silver (LLM + booster) |
|---|---|---|
| Spans | 1,343 | 1,996 |
| **Unique surface forms** (case-folded) | **81** | **532 (6.6×)** |
| Abstracts with ≥1 span | 840 | 915 |
| Distinct Recon pathways named | 60 | 64 |

- **457 surface forms (86% of the silver vocabulary) are new** — never produced by exact
  matching on these abstracts. Only 6 exact-matching surfaces are missing from silver.
- Per-pathway variation richness now visible, e.g. `fatty acid oxidation` appears as 9
  distinct forms (`beta-oxidation`, `fao`, `fatty acid beta-oxidation`, …).

#### 🐞 Direction bug found and fixed (canonicalizer + booster)
The analysis surfaced semantically **opposite** mappings: `purine biosynthesis` →
`purine catabolism`, `heme catabolism` → `heme synthesis`, `pyrimidine biosynthesis` →
`pyrimidine catabolism`.

- **Cause:** both `canonicalize.py` (layer 3) and `booster.py` strip the process word and
  match on content phrases only. `purine biosynthesis` → `{purine}` ties against *both*
  `purine synthesis` and `purine catabolism`; whichever came first in the vocabulary won.
  Recon distinguishes the two — we were throwing that information away.
- **Evidence it was in two places:** the same surface `purine biosynthesis` resolved to
  `purine synthesis` via the LLM path but `purine catabolism` via the booster path.
- **Fix:** `booster.process_class()` / `direction_ok()` classify a phrase as
  anabolic / catabolic / neutral by its process word; a non-neutral surface may never match
  a canonical of the opposite direction. Defined once in `booster.py` (which owns
  `PROCESS_WORDS`) and imported by `canonicalize.py` — avoids a circular import.
- **Impact:** **zero on training labels** (the canonical never enters a `0/1/2` label), so
  the decision to deprioritize canonicalization stands. It corrupted the *analysis* and
  would have been a serious error in the future pathway↔disease DB.
- After the fix: `exact` 999→1,012, `variation` 251→238 (13 spans were mislabeled
  `variation` while actually exact matches of a *different* canonical). Golden gates
  re-run, no regression: canonicalizer 16/19, booster eval `span:variation` 5/6, precision 0.95.
- **Lesson:** the 19-span golden set contains no synthesis/catabolism pair, so it certified
  a canonicalizer that inverted meaning. Small golden sets certify what they contain.

`llm/run_silver.py --recanonicalize` re-derives canonical/match_type over the cache with no
LLM calls (the booster is re-run from scratch since its canonical is baked into the cache).

### ✅ P3-1f — `doccano/` folder + preview
All doccano-related data/code/docs consolidated into `doccano/`: `pilot_1k_doccano.jsonl`
(import file), `ANNOTATION_GUIDE.md`, `export_doccano.py`, `preview.py` → `preview.html`,
`README.md` (import steps + format spec).

- **Format verified against doccano source**, not guessed: `backend/data_import/pipeline/
  catalog.py` → `ArgColumn` defaults `column_data="text"`, `column_label="label"`. So
  `label` is **singular** on import: `{"text": ..., "label": [[start, end, "Pathway"]]}`.
  doccano's *export* uses `labels` (plural) — an asymmetry in their own docs.
- Extra keys flattened to top level (`pmid`, `model`, `query_pathways`, `span_info`) since
  doccano stores non-text/label columns as example metadata; the previous nested `meta`
  object would have become `meta.meta`.
- `preview.py` renders the import file to static HTML using the exact offsets doccano will
  read — lets us check the spans without installing doccano.

#### 🐞 `maybe_partial` removed — it was 100% false alarms
Building the preview exposed it: the flag marked `arachidonic acid metabolism` (a complete
canonical name) as a boundary error.
- **Measured:** true partial spans in the 1k = **0**. The flag fired on **23** correct spans.
- **Why zero:** `merge()` already resolves the artifact — the LLM reliably returns the full
  canonical name and the longer span wins over the booster's fragment. The problem the flag
  was built for does not survive the pipeline.
- **Why it misfired:** the heuristic ("a content phrase of the canonical appears just
  before") fires on normal enumerations — `gluconeogenesis` in "glycolysis, gluconeogenesis,
  and …" looks incomplete against the combined canonical `glycolysis/gluconeogenesis`, but
  the span is correct.
- Removed from the pipeline, export, preview and guide rather than push annotators to
  "fix" 23 good boundaries. Earlier "maybe_partial 2%" figures in P3-1c/e are superseded.

Also fixed: `load_query_pathways()` was leaking `pathway_id: null` rows from
`exact_matches.jsonl` into prompt hints and export metadata (`"query_pathways": [null]`).

#### P3-1f addendum — aligned with the existing doccano workspace
An established doccano workspace already exists **outside this repo** at
`/home/enes/annotations`: its own venv with doccano installed, a live `doccano-home/
db.sqlite3`, `scripts/export_to_doccano.py` + `import_from_doccano.py` (+ relation
variants), and a 15KB `DOCCANO_GUIDE.md`. It was not found when `doccano/` was first built
here, so some of that work was reinvented.

Reconciled against it:
- **Label `Pathway` → `PATHWAY`** — what that workspace's guide and existing project use.
  The string never reaches the model (`train.py` hardcodes `{"O", "B-Pathway", "I-Pathway"}`;
  `tag_bio.py` derives BIO from spans) — it only has to match the label defined in the
  doccano project.
- **`meta` un-flattened back to nested.** The earlier flattening was reasoned from doccano's
  source (extra columns → metadata) but the workspace's nested `meta` is the *proven* shape —
  488 records imported with it. Untested theory should not override working precedent.

Scope decisions (user):
- **Annotators review Phase 3 silver only.** The Phase-1 export there (488 docs from
  `all_matches.jsonl`) is ignored: it has **zero review done** (556 spans are all machine
  pre-fill, 0 documents complete) and shares just **3 PMIDs** with Phase 3 — different
  corpus (KEGG/Reactome reference articles vs the PubMed corpus), different vocabulary,
  1.1 vs 2.0 spans/document.
- **New doccano project** for Phase 3; the Phase-1 project is left untouched.
- `meta` contents follow Phase 3 (`pmid`, `model`, `query_pathways`, `spans`), not the
  Phase-1 shape. A silver round-trip script (the `import_from_doccano.py` equivalent) is
  still needed — the existing one targets the Phase-1 `all_matches.jsonl` schema. Deferred
  until after review.

Related finding (analysis only, **not** actioned by user decision): 28 of the 353 distinct
`unmapped` surfaces (62 spans) are verbatim **KEGG/Reactome** pathway names absent from
Recon's 98 — e.g. `ascorbate and aldarate metabolism`, `pentose and glucuronate
interconversions`, and `biosynthesis of unsaturated fatty acids`. Independent confirmation
that the unmapped bucket holds real pathways rather than hallucinations, and evidence for
the annotation guide's decision to accept non-Recon pathway names. Most of the rest are
synonym/normalisation gaps against vocabularies we already have (`kynurenine pathway` ≈
`tryptophan catabolism`; `alanine, aspartate, and glutamate metabolism` misses KEGG's entry
on the Oxford comma alone) or umbrella terms. Left as-is: the canonical never enters a label.

### ✅ P3-1g — Per-annotator batch split + Turkish annotator steps
Local-install annotation workflow: each annotator installs doccano and imports one slice.
- `doccano/split_batches.py` splits `pilot_1k_doccano.jsonl` into fixed-size batches (default
  200) → `doccano/batches/pilot_1k_doccano_batch_NN_TOTAL.jsonl`. Each batch is a verbatim
  slice — self-contained and directly importable, same format as the full file. Verified: 5
  batches × 200 docs preserve all 1,000 docs / 1,996 spans (378–430 spans per batch).
- `doccano/ANNOTATOR_STEPS.md` (**Turkish**) — post-install steps: new Sequence Labeling
  project → add label `PATHWAY` → import batch JSONL → annotate per `ANNOTATION_GUIDE.md` →
  export. Assumes doccano already installed.
- Per annotator, send: their batch file + `ANNOTATOR_STEPS.md` (TR) + `ANNOTATION_GUIDE.md`
  (accept/reject rules, currently EN).
- Annotation model of record: **Qwen2.5-14B-Instruct, Q4_K_M (4-bit)** via Ollama, tag
  `qwen2.5:14b` (14.8B params) — recorded in every silver record's `model` field — plus the
  rule-based booster (`llm/booster.py`, ~9% of spans; not a model).

**Still open (deferred until review returns):** a round-trip script to merge the annotators'
doccano exports back into a corrected silver set (the existing
`/home/enes/annotations/scripts/import_from_doccano.py` targets the Phase-1 `all_matches`
schema, not this one). `ANNOTATION_GUIDE.md` is EN while `ANNOTATOR_STEPS.md` is TR — translate
the former if annotators need Turkish.

### ✅ Golden set v2 — pathway-type diversity (`playground/golden_set/build_golden_set.py`)
Grew the gold set 5 → 10 abstracts. v1 was amino-acid/lipid heavy; v2 adds 5 abstracts
picked for pathway-*type* coverage (ranked candidates by distinct under-represented Recon
themes in `exact_matches.jsonl`): energy/central-carbon, carbohydrate, nucleotide, urea
cycle, vitamin/cofactor, bile acid, drug/xenobiotic.
- New PMIDs: 34376485 (HPV/smoking HNSCC — OXPHOS/glycolysis, bile acid, FA-oxidation,
  galactose, vitamin B6), 42299101 (glioblastoma review — Warburg/glycolysis, PPP,
  nucleotide, folate, glutamine; dense variations), 28587170 (arginine deprivation HCC —
  **urea cycle**, pyrimidine, TCA), 38669820 (goose astrovirus — drug/cytochrome-P450,
  retinol→vitamin A, ascorbate→vitamin C, carbohydrate), 37807318 (colon-cancer central
  carbon — glycolysis, TCA, PPP, galactose, butanoate + clean sugar/nucleotide negatives).
- Recon-resolvable mentions 38 → 76; exact-match catch rate 37% → 51% (added central-carbon
  articles name pathways verbatim), still ~49% variations missed. Umbrella mentions 4 → 9.
- All offsets recomputed from `(surface, occ)` and every match_type validated OK by the
  build script. Same schema/consumers — `golden_set.json` now carries `version: "v2"`.
- **Integrity:** the 5 new PMIDs are absent from silver/doccano (verified); updated the
  hardcoded exclusion `GOLDEN_PMIDS` in `llm/run_silver.py` (5 → 10) so silver never trains
  on them if regenerated. Doc counts updated (README, doccano guides).

### 🐞 Silent LLM failures could be cached forever (`llm/extract_guided.py`, `llm/run_silver.py`)
`call_llm` swallowed every exception into `return []`, so a timeout, a dropped connection or
a non-JSON reply was indistinguishable from "the model found no pathway". `run_silver.py`
then wrote that empty result to the per-pmid cache — and since the cache file *is* the resume
key, the abstract was lost for good: no later run would ever retry it.

- `call_llm` now raises `LLMCallError` on transport failure, HTTP error, missing/malformed
  JSON, or a non-list `mentions`. An empty list means one thing only: the model genuinely
  found nothing. `extract_guided()` propagates it (an eval that dies loudly beats one that
  scores a broken run).
- `process_one()` returns `None` on `LLMCallError`: **no cache write**, pmid dropped from the
  output, warning logged. A re-run retries exactly those pmids. Summary gained an
  `LLM FAILURES / OUTPUT IS INCOMPLETE` line.
- **Audited the existing pilot** — all 91 zero-LLM-span records re-queried: **0 call errors**,
  87/91 identical, 4 differed from run-to-run nondeterminism (not recovery). The 39-min
  runtime already implied this: one 120 s timeout would eat 5% of it. Of the 8 spans the
  re-query produced, 6 were bare metabolites/proteins/enzymes that `RULES_LENIENT` explicitly
  forbids (`cAMP`, `BDNF`, `GSK-3β`, `glutathione-converting enzymes`) — so the refill was
  reverted from backup and `pilot_1k.jsonl` is byte-identical to before. Conclusion: no silent
  loss ever occurred; the fix is insurance for the slower models Phase 3+ may use, where the
  120 s margin (now 1.9–2.4 s/abstract) closes.

### ✅ Frozen silver samples (`llm/run_silver.py`, `data/silver/pilot_1k_pmids.txt`)
`select_sample()` is **not** stable across vocabulary changes: widening `GOLDEN_PMIDS`
5 → 10 (golden set v2) re-proportioned every disease category and re-walked the shared RNG,
shifting the 1k draw by **49% at the same seed=42**. The pilot the doccano batches were built
from could therefore no longer be regenerated by running the script — a model swap would have
re-labelled a *different* thousand abstracts than the annotators are reviewing.

Sample selection is now either frozen or sampled, never both:

| Flag | Meaning |
|---|---|
| `--pmids FILE [FILE…]` | run exactly these pmids, no sampling (union, de-duped, file order kept) |
| `--exclude FILE [FILE…]` | never sample these; rejected together with `--pmids` |
| `--number-of-articles N` (`--n`) | how many to sample; ignored with `--pmids` |

- `data/silver/pilot_1k_pmids.txt` — the pilot's 1,000 pmids in original order. Verified:
  `--pmids` reproduces `pilot_1k.jsonl` **byte-for-byte from cache, 0 LLM calls**.
- `playground/golden_set/golden_pmids.txt` — the 10 gold pmids, for `--exclude`.
- Golden is dropped from `--pmids` input too, not just from sampling: an explicit list is the
  one path that skips the sampler, and eval data must never reach silver by either route.
- Pmid files take `#` comments and blank lines; unknown/abstract-less pmids are warned and
  skipped rather than crashing.

**Reproducibility is frozen artefacts, not determinism.** Ollama is not deterministic even at
`temperature=0, seed=42` (measured again here: 4/91 re-queried abstracts changed). Everything
else in the pipeline — `booster.py`, `canonicalize.py`, `ground()`, `merge()` — is pure. So the
single stochastic step is pinned by the cache, and the sample by the pmid file.

### 📄 Model & hardware research (`reports/llm_selection_and_hardware_2026-07.md`)
Literature/web survey (July 2026) answering "is there a better annotator than qwen2.5:14b,
and is the hardware the limit?" Headline findings:

- **Medical-domain LLMs are a trap for this task.** Biomedically fine-tuned models do not beat
  general ones at information extraction and often lose (`Llama-3-8B-UltraMedical`, `PMC-Llama
  13B` < base `Llama-3.1-8B`); MedGemma's technical report carries no NER/IE benchmark at all.
  The task needs instruction-following + verbatim spans + JSON, not medical knowledge — the
  query pathways are already in the prompt and canonicalisation is ours.
- **Highest-ROI alternative is not an LLM: `GLiNER-BioMed`** (434M encoder, MIT). Zero-shot
  59.8 F1, **50-shot 76.0** — matching our data scale. Selects spans instead of generating
  them, so hallucination is structurally impossible; runs in minutes on 8 GB. Different error
  profile from a decoder → a third annotation source next to LLM + booster.
- **`qwen2.5` is two generations old** — Qwen3.5 (Feb–Mar 2026) and Gemma 4 (Apr 2026, Apache
  2.0) shipped. `qwen3.5:9b` fits VRAM fully, unlike the current 9.0 GB 14b which already runs
  partly CPU-offloaded on this 8 GB card.
- **Hardware is not the bottleneck; the eval set is.** 15 GB system RAM binds harder than the
  8 GB VRAM, and a ~$130 SO-DIMM upgrade unlocks CPU-offloaded MoE models — but 7b → 14b never
  moved `span:variation` (4/6 → 4/6), so buy evidence before hardware: a few dollars of cloud
  GPU or frontier API measures the ceiling first. Full 10k corpus via API ≈ $3–15.
- **Blocking caveat (§7):** the golden set is 10 abstracts / 76 mentions and the deciding
  metric rests on **6 cases**. Model comparisons cannot be arbitrated at that size — carve a
  ~150-abstract hold-out from the human-reviewed doccano 1k before spending on model choice.

### ✅ Batch 05 review — all 200 docs (`analysis/batch_05_5_review.json`)
`doccano/batches/pilot_1k_doccano_batch_05_5.jsonl` scored against `ANNOTATION_GUIDE.md`.
Two provenances in one file: **docs 1–50** are the human annotator's doccano export
(`admin.jsonl`) with 16 assistant-applied corrections, so its final labels are the gold
standard there; **docs 51–200** are the assistant's own review.
Every span classified TP / FP / FN; boundary errors recorded as an FP + a corrected FN so
span-exact metrics stay honest. All offsets machine-verified (`text[start:end]` matches),
so the FN entries are directly importable as doccano labels.

- **All 200 docs: 378 machine spans → 337 TP, 41 FP, 146 FN. Precision 0.892, recall 0.698,
  F1 0.783.** Split by half: docs 1–50 (human) P 0.854 / R 0.800 / F1 0.826; docs 51–200
  (assistant) P 0.906 / R 0.668 / F1 0.769. The recall gap is a sweep-depth difference, not a
  model difference — the assistant half counted umbrella terms and repeat mentions the human
  half largely left alone.
  Precision is close to the 0.90 the pilot assumed; recall is the real gap.
- **Human-half corrections applied to `admin.jsonl`** (backup `admin.jsonl.bak`): removed
  signalling/cell-death pathways the guide excludes (`PPARα/PGC-1α signaling pathway`,
  `sphingolipid signaling pathway`, `necroptosis pathway`), an enzyme-inhibition phrase
  (`nicotinamide phosphoribosyltransferase inhibition`), a compartment term
  (`mitochondrial oxidative pathway`), a disease pathway (`lipid and atherosclerosis`), a
  transport term (`cholesterol efflux`), a non-enzymatic damage term (`Lipid peroxidation`)
  and two broken/adjectival spans (`lipid metabolic`, `glycolytic function`); added
  `polyol pathway`, `glucose metabolism`, `lipogenesis`, `NAD salvage pathway`; merged
  `linoleic acid` + `glycerophospholipid metabolism` into one coordination span. Left as
  annotated by explicit decision: `degradation of fructose` / `production of fructose` stay
  rejected in doc 17, `cholesterol homeostasis` stays accepted in doc 8.
- **FP classes:** bare metabolites (`TCA intermediates`, `pyrimidine pools`, `thiamine`),
  disease names (`urea cycle disorders`, `inborn errors of metabolism`), signalling pathways
  (`calcium signaling pathways`, `sphingolipid signaling pathway`), the guide's own named
  reject (`aminoacyl-tRNA biosynthesis`), and boundary slips (`cell glycolysis`, dropped
  `de novo`, two pathways in one span).
- **FN classes:** umbrella terms are the dominant miss (`lipid/energy/glucose/carbohydrate
  metabolism`), then the spelled-out first mention when an abbreviation is caught later
  (`nicotinamide adenine dinucleotide (NAD) metabolism`), then whole zero-span documents
  that do contain a mention (docs 102, 141).

**Conventions applied that the guide does not state.** Recorded in the JSON's `conventions`
field only — **deliberately not added to `ANNOTATION_GUIDE.md`**: these are edge cases, and
annotators are trusted to judge them from the guide's existing rules.
1. Shared-head coordination (`calcium and vitamin D metabolism`) is one span. Test: delete the
   other conjunct — if what remains is not a pathway name on its own, do not split. A list of
   distinct heads (`glycolysis and the pentose phosphate pathway`) must be split.
2. If a coordination is only partly marked, the narrow span stays a TP **and** the full string
   is recorded as an FN carrying the correct boundary (10 such FNs added, docs 64, 107, 111,
   134, 144, 149, 151 ×2, 168, 187; 2 existing FNs widened, docs 83, 169).
3. A trailing `pathway`/`pathways` may stay inside the span; a trailing `metabolites`,
   `intermediates`, `genes` or `disorders` changes the referent and must be excluded.
4. When a disease phrase embeds a nameable pathway, span the pathway part
   (`urea cycle disorder` → `urea cycle`).

**Cross-check against an independent Gemini pass** (which covered docs 51–159): 16 of 26 FPs
corroborated verbatim, 6 genuine conflicts — all resolvable from the guide's own text and
kept as reviewed here. Gemini also mislabelled an FN as TP (doc 136), silently widened two
machine spans instead of flagging the boundary (docs 134, 155), and reported one span that
does not exist in the labels (doc 157).

**Open — non-English abstract bodies.** Some records carry a translated abstract after the
English one (doc 92 Chinese `糖酵解`/`氧化磷酸化`, doc 157 Russian `глутатионового обмена`).
Neither the silver model nor this review annotated them. Decide the policy and state it in
`ANNOTATION_GUIDE.md`; if they are in scope, the FN lists for those two documents grow.

### ✅ Model registry + per-model cache + frozen sample (`llm/models.py`)
Groundwork for swapping the annotator model, done before any swap so the comparison is
measurable rather than assumed.

- **`llm/models.py` — one `ModelSpec` per model**, carrying the ollama tag, sampling
  options, top-level payload keys and a cache slug. `resolve()` accepts a registry key
  or any raw tag (unregistered tags still run, on greedy defaults, with a cache of their
  own). `extract_guided.call_llm()` now builds its request body from the spec, so the
  call site no longer hardcodes `{"temperature": 0, "seed": 42}`.
  Registered: `qwen2.5:14b` (default), `qwen2.5:7b`, `qwen3.5:9b`, `qwen3.5:4b`.
- **Thinking mode is a per-model flag.** Qwen3+ emits a chain of thought that costs
  latency and can push the JSON object out of the response; the 3.5 entries carry
  `think: false` (verified accepted by ollama 0.30.10, and ignored harmlessly by models
  without the mode). This was the concrete blocker to trying Qwen3.5 at all.
- **🐞 The silver cache was keyed on pmid alone.** Swapping the model would have replayed
  the previous model's cached answers for every abstract already seen — a run that looks
  successful, changes nothing, and cannot re-label the pilot. Cache is now
  `data/raw/llm_cache_silver/<model slug>/<pmid>.json`; the existing 1,000 files were
  moved to `qwen2.5_14b/`. Verified: re-running batch 05 reproduces 378 spans from cache,
  0 LLM calls.
- **`--pmids` freezing is now automatic.** Every run writes `<output stem>_pmids.txt` —
  the *effective* sample in output order, after golden leaks, abstract-less pmids and
  failed calls are dropped. Skipped for `--limit` (a partial head of the sample, freezing
  it would pin a list nobody meant to draw) and for `--no-freeze`.
- `venv310` is a symlink to the existing `.venv`, so the paths in every docstring resolve.

### ✅ Annotator A/B harness (`analysis/score_against_review.py`)
Scores any silver run against `analysis/batch_05_5_review.json` — 200 abstracts, 483 gold
spans. This replaces the golden set as the model-selection metric: §7 of the model report
flagged that 10 abstracts / 76 mentions cannot arbitrate a model choice when the deciding
metric rests on 6 cases.

- Reports span-exact and lenient (overlap) P/R/F1, split by the human half (docs 1–50) and
  the assistant half (51–200), plus the top FP/FN strings.
- Absolute recall is pessimistic by construction — the reference sweep counts umbrella and
  repeat mentions the guided prompt never targeted — but equally so for every model, which
  is what an A/B needs.
- **Baseline `qwen2.5:14b` reproduces the review exactly**: 378 spans → 337 TP / 41 FP /
  146 FN, P 0.892 R 0.698 F1 0.783 (lenient 0.934 / 0.748 / 0.831). Human half P 0.854
  R 0.800; assistant half P 0.905 R 0.668.
- The 200 evaluation pmids are frozen at `data/silver/batch05_eval_pmids.txt`.

### 📊 A/B result — `qwen3.5:9b` does not replace `qwen2.5:14b`
First use of the batch-05 harness. 200 abstracts, 483 gold spans.

| run | spans | P | R | F1 | lenient P/R/F1 |
|---|---|---|---|---|---|
| `qwen2.5:14b` | 378 | 0.892 | 0.698 | **0.783** | 0.934 / 0.748 / **0.831** |
| `qwen3.5:9b` | 398 | 0.791 | 0.652 | 0.715 | 0.889 / 0.752 / 0.815 |

- **Recall is a wash** (lenient 0.752 vs 0.748); the whole gap is precision. Qwen3.5 emits
  more spans (398 vs 378) and more of them are wrong.
- **Read span-exact with suspicion — the gold is seeded by qwen2.5.** For docs 51–200 the
  gold TPs *are* qwen2.5's spans that the review accepted, so qwen2.5 has a home-field
  advantage on exact boundaries. Boundary-only FPs (right region, wrong edges) are 39/83
  for qwen3.5 against 16/41 for qwen2.5 — e.g. `inositol phosphate metabolism pathway`
  (×5) and `pentose phosphate pathway` (×2), both arguably *better* spans than the
  recorded gold. Lenient scoring is the fairer read, and qwen2.5 still wins there.
- Genuine content FPs (no overlap with any gold span): 44 for qwen3.5 vs 25 for qwen2.5.
  Its characteristic errors are the guide's named rejects — `mitochondrial metabolism`
  (×3), `mitochondrial respiration` (×2), `glucose turnover` (×3).
- Unmapped spans (no Recon canonical) rise 25% → 30%.
- **Qwen3.5 is ~4× faster**: 1.8 s/abstract measured, so a 1k run is ~0.5 h against the
  documented ~2 h. It fits the 8 GB card fully; qwen2.5:14b is CPU-offloaded.
- **🐞 `think: false` is not sufficient.** On PMID 42121260 qwen3.5 deterministically
  breaks the JSON contract by reasoning *inside* the array:
  `"fatty acid synthesis" (implied by context but exact phrase check: wait, looking at
  text...`. Disabling the thinking channel does not stop inline chain-of-thought, and at
  `temperature=0, seed=42` the failure repeats on every retry. 1/200 abstracts lost.

#### Follow-up: structured output fixes the format, not the judgement
Probed on the failing abstract plus a working control, then re-run over all 200.

| variant | latency | JSON |
|---|---|---|
| `think: False` (as measured above) | 78 s on the failing abstract, 1.8 s on the control | 1/2 parse |
| `think: True` | 78–82 s | **0/2** — `response` empty, all ~14k chars go to `thinking` |
| `format: "json"` | 1.3 s | 2/2 |
| `format: <schema>` | 1.2 s | 2/2 |

- **`think: True` is unusable**: ~45× slower and it never emits a final answer.
- **The schema is a free win for robustness**: over the 200, 200/200 abstracts complete
  (was 199/200) at 1.3 s/abstract (was 1.8) — the rambling was the slow part.
- **It changes qwen3.5's scores by nothing at all**: F1 0.715 → 0.715 span-exact,
  0.815 → 0.814 lenient, 398 → 401 spans, 315 → 316 TP. So qwen3.5's precision deficit is
  a judgement difference, not a formatting artefact — worth knowing, because a
  malformed-JSON model could otherwise look unfairly penalised.
- **On `qwen2.5:14b` the schema is a strict no-op.** Re-run over the same 200 with the
  schema on: identical scores, and the span output is byte-identical — 0 of 200 abstracts
  differ by a single offset. Kept in `llm/models.py` for every entry: it costs nothing and
  makes the "reasoning inside the JSON array" failure class structurally impossible.
  Measured 2.5 s/abstract (1k ≈ 0.7 h), well under the ~2 h the docstring assumed — though
  there is no like-for-like schema-off timing on this machine to attribute the difference.
- **Cache hygiene for that re-run**: the 200 eval pmids were deleted from
  `llm_cache_silver/qwen2.5_14b/` (leaving the pilot's other 800 intact) and regenerated
  under the schema, so the directory now mixes pre- and post-change records. Proven
  harmless: regenerating the whole pilot from that mixed cache reproduces
  `data/silver/pilot_1k.jsonl` **byte-for-byte**, 1000/1000 from cache, 0 LLM calls.
- The prompt was never the problem: it already says *"Return ONLY a JSON object … Do not
  explain. Do not add text outside the JSON."* The model read that and violated it anyway.
  This belongs at the decoding layer.

**Decision: keep `qwen2.5:14b` for the wave-2 1k.** Same recall, cleaner output, and the
annotator workflow is accept/reject — extra false positives are annotator burden with no
upside. Qwen3.5's only real edge is speed (0.4 h/1k vs ~2 h).

**Known sharp edge, deliberately not fixed:** the cache slug derives from the model tag
only, so it does not notice a changed request shape *or a changed prompt*. Editing
`llm/prompts/pathway_extraction_guided.py` today would silently replay the old prompt's
answers for every cached abstract. Until that changes, altering a model's request shape or
the prompt means deleting that model's cache directory by hand.

---

# Phase 4 — Base-encoder survey

Started 2026-07-29. Motivation: hyperparameter tuning plateaued at **gold-008**
(test F1 0.8197), teacher `qwen2.5:14b` sits at 0.864, and the remaining levers
are more reviewed data (wave-3) or a different base encoder. This phase is the
encoder axis; the annotator-LLM axis is Phase 3 and independent.

## Research — `reports/base_model_expansion_analysis_2026-07.md`

Widened the earlier five-candidate note (`base_model_survey_2026-07.md`) to every
usable encoder family, with the papers' own numbers rather than assumptions.

**The headline is negative and worth stating plainly.** The whole BLURB NER column
spans 86.13 (our current base) to 86.89 (the leaderboard's best) — 0.76 points,
averaged over six corpora with thousands of training documents each. A 2026 paper
(arXiv 2605.12438) measures a 396M 8192-context bio-ModernBERT at **parity with
110M PubMedBERT** on BC5CDR / JNLPBA / NCBI / AnatEM. Realistic gain from an
encoder swap: **+0.005 … +0.02 F1**, against a measured seed band of ±0.007.

Two candidates were dropped on evidence rather than intuition:
- **BioClinical-ModernBERT**, which the earlier note ranked second, is 1.0–4.1
  points *below* 110M PubMedBERT on literature NER. Its SOTA is on clinical notes
  (DEID, Social History); our corpus is PubMed abstracts.
- Decoder LLMs with a token-classification head — the teacher is already an LLM;
  a distilled student exists to be cheap.

Two candidates emerged that the earlier note missed, and they are the only ones
whose expected gain exceeds the noise band:
- **GLiNER-biomed** (arXiv 2504.00676) — LLM annotation ability distilled into a
  span-scoring model, structurally the same idea as this project at a scale we
  cannot reach. 10-shot 70.4 → 50-shot 76.0 → full-supervision ~84.9 F1. Our 860
  documents sit inside that curve.
- **Task-adaptive pretraining** (OpenMed NER, arXiv 2508.01630) — SOTA on 10 of 12
  biomedical NER benchmarks from ordinary backbones plus DAPT and LoRA, under 12
  GPU-hours. We already hold a large unlabelled on-topic corpus in `data/raw/`.

## Tier 0 — comparison harness (done)

Infrastructure only; details and measurements in
`knowledge_base/model_experiments.md` § *Tier 0*.

Three defects would have made every cross-encoder number meaningless:
1. **The split was tokenizer-dependent.** `build_dataset.py` dropped label-free
   records *after* tokenization (1083 → 1076 under BiomedBERT, 7 lost to 512-token
   truncation) and then shuffled the survivors. A ModernBERT at 8192 tokens loses
   none of the 7 and would shuffle a different-length list into an unrelated
   train/val/test assignment — every encoder scored on a different test set, with
   every log line still reading "Test: 109".
2. The model name was hardcoded in two files with no link between the `input_ids`
   on disk and the model consuming them. Vocabularies overlap in range, so a
   mismatch trains silently on nonsense.
3. `train.py` could only load `BertForTokenClassification`, and used fp16 — a
   known NaN source for ModernBERT.

New: `encoders.py` (registry, shaped like `llm/models.py`),
`preprocessing/make_splits.py`, `preprocessing/check_alignment.py`,
`scripts/run_matrix.py`, `scripts/aggregate_runs.py`, and
`data/processed/gold/splits.json` — the frozen split, tracked in git.

**Gate: the regenerated dataset is byte-identical to the one gold-001…008 used**,
and the gold-008 recipe re-run under bf16 and transformers 5.10.2 gives **F1
0.8199** against the recorded 0.8197. The historical series is continuous.

### The most important number produced by Tier 0

Three seeds of the gold-008 recipe on the frozen split: 0.7947 / 0.8199 / 0.8282
→ **0.8143 ± 0.0175**.

The ±0.007 noise band that every earlier conclusion leaned on was measured at
**lr 3e-5** (gold-004/005/006). At 5e-5 the band is **2.5x wider**. So:

- **gold-008's 0.8197 was a lucky seed** — the recipe's mean is 0.8143, and
  gold-004's 0.8154 at 3e-5 is indistinguishable from it. "5e-5 beats 3e-5 by
  +0.004" compared two single seeds and means nothing.
- **5 seeds is not enough to run the survey.** At σ = 0.0175, two 5-seed
  configurations separate only at ≈0.022 F1 — the very top of what an encoder swap
  is predicted to give. Resolving 0.015 needs **11 seeds** (~7.3 GPU-hours for five
  configurations; an overnight run on the 4060, so this is affordable, not
  blocking).
- Worth one cheap check first: if 3e-5 really is the quieter setting, running the
  whole sweep there buys statistical power for free.

### Measurements that contradicted the plan's assumptions

- **ModernBERT's 50k vocabulary fragments biomedical terms *more*, not less** —
  14.8% continuation subwords against BiomedBERT's 7.4%. Its vocabulary is
  general-domain; BiomedBERT's 30k WordPiece was built on PubMed. Whatever a
  ModernBERT wins here, it will not be through tokenization.
- **`trim_offsets: true` does not exclude the leading space.** `Ġfatty` reports
  offsets covering `' fatty'`. The old per-character label lookup would have
  silently dropped those spans; alignment now tests the token's whole range.
- **Long context is not free.** Bio-ModernBERT-*base* (150M) OOMs at batch 16 on
  the 8 GB card, because an 8192-token model pads a batch to its longest document
  (~2750 tokens here) rather than to 512. It needs batch 2 × grad-accum 8.
- **Four candidates share one vocabulary** — BioLinkBERT base/large,
  BiomedBERT-large-abstract and BioELECTRA ship byte-identical 28895-token
  PubMedBERT `vocab.txt` files. BiomedBERT-*base*'s own 30522-token vocabulary is
  a *different* vocabulary of a similar size, which is exactly the pairing that
  fails silently. The guard compares vocabulary fingerprints, not model ids.

### Findings handed to wave-3 review

`analysis/alignment_*.json`, both tokenizer-independent:
- **83 nested span pairs** — shared-head enumerations annotated twice
  (`cholesterol and fatty acid synthesis` *and* `fatty acid synthesis`). Flat BIO
  cannot represent nesting; the inner span's start opens a new `B` and truncates
  the outer mention. Plausibly feeds the boundary errors in
  `analysis/error_analysis.json`.
- **12 boundary-error spans** — 6 starting mid-word (`biopterin metabolism` inside
  `tetrahydrobiopterin metabolism`), 6 dropping a plural. The mid-word starts
  produce a dangling `I` with no `B`.

## Phase 4b — first-stage grid (paused 2026-07-31)

Five encoders chosen for the first stage, picked for the widest expected spread at
the lowest cost; the other twelve stay in reserve with datasets already built and
validated, so any of them joins a later sweep with no preparation.

| model | role | why it is in the first five |
|---|---|---|
| `biomedbert-base` | anchor | the baseline every other number is read against |
| `bert-base` | domain floor | BLURB NER 82.99 vs 86.13 — the widest gap in the grid |
| `bio-clinicalbert` | domain mismatch | brackets the baseline from the opposite side |
| `bioelectra-base` | objective | best BLURB NER per parameter (86.67), byte-identical vocabulary to the PubMedBERT group, so the contrast is RTD vs MLM alone |
| `bio-modernbert-base` | architecture | the only architecture, tokenizer and 8192-context change in the set |

Grid: 5 models × 2 learning rates × 3 seeds = 30 cells, fixed gold-004+ recipe.

### Completed (`runs/summary.jsonl`, 7 cells)

| model | lr | seed 42 | seed 1 | seed 7 | mean |
|---|---|---|---|---|---|
| `biomedbert-base` | 5e-05 | 0.8199 | 0.7947 | 0.8282 | 0.8143 |
| `biomedbert-base` | 3e-05 | 0.8191 | 0.8125 | 0.8053 | 0.8123 |
| `bio-modernbert-base` | 5e-05 | 0.7857 | — | — | — |

The `biomedbert-base` lr 5e-05 row reproduces the recorded 0.8143 ± 0.0175 exactly
— a regression test on the harness, not a new result. The two learning rates are
0.002 apart against σ = 0.0175, i.e. indistinguishable at three seeds.

### Why 18 cells failed, and the fix

`bert-base`, `bio-clinicalbert` and `bioelectra-base` aborted immediately:

```
OSError: google-bert/bert-base-uncased does not appear to have a file named
pytorch_model.bin or model.safetensors.
```

Dataset preparation only ever pulls tokenizer and config, so the weights were
never in the cache, and `HF_HUB_OFFLINE=1` turned the miss into a hard failure
instead of a download. **Resolved** — all three sets of weights are now cached,
load into `AutoModelForTokenClassification`, and their vocabulary fingerprints
still match the datasets built earlier. `bio-clinicalbert` still tokenizes
`Alzheimer` whole, so the casing fix survived the re-download.

**Ten of the seventeen registry models still have no weights cached**, all of them
in reserve: `modernbert-bio-base`, `scibert`, `biobert`, `biomed-roberta`,
`modernbert-base`, `bioclinical-modernbert-base`, `bio-modernbert-large`,
`modernbert-bio-large`. Check before launching a sweep that includes them — disk
is at 89% with 15 GB free.

### Training is not reproducible at a fixed seed

Re-running the oldest cell (`biomedbert-base`, lr 5e-05, seed 42) twice did not
reproduce its recorded 0.8199:

| run | test F1 | test P | test R | best val F1 | best epoch | epochs run | seconds |
|---|---|---|---|---|---|---|---|
| 29 Jul (recorded) | 0.8199 | 0.7897 | 0.8526 | — | — | — | 549 |
| replicate 1 | 0.7662 | 0.6984 | 0.8486 | 0.8080 | 7 | 15 | 292 |
| replicate 2 | 0.7736 | 0.7348 | 0.8167 | 0.8223 | 16 | 24 | 469 |

The two replicates differ from each other as well as from the original, so the
pipeline is nondeterministic at a fixed seed. Every field in `test_results.json`
was compared: `lr`, `seed`, `class_weights`, `epochs`, `patience`,
`frozen_layers`, `precision_mode`, `batch_size`, `grad_accum`, `n_train`,
`n_val`, `n_test_effective`, `data_dir` and `hf_id` are identical; the only
differences are schema fields absent from the older file. The dataset has not
changed since 29 July (`train.jsonl` mtime 23:19, before the run), and
torch 2.12.0 / transformers 5.10.2 have been installed since 7 June.

`set_seed` is called but `torch.use_deterministic_algorithms` is not, so cuDNN
kernel selection and atomic accumulation order vary between runs. Early stopping
turns those small numeric differences into a discrete decision — which epoch is
best — and the trajectories then diverge: replicate 1 peaked at epoch 7,
replicate 2 at epoch 16.

**Consequences.** The σ = 0.0175 recorded as *seed* variance is really seed plus
run-to-run noise, so the grid resolves less than planned. The assumption that
retraining a best configuration reproduces its swept number is false — Phase 5
(`models/encoders/`) needs a different rule for which checkpoint is authoritative.

**Unresolved.** Both replicates fall below all three recorded lr 5e-05 runs
(0.7947 / 0.8199 / 0.8282). Two samples cannot separate an unlucky draw from a
systematic shift. Against a shift: the three lr 3e-05 cells ran on 31 July under
the *current* code and produced 0.8191 / 0.8125 / 0.8053, which are not depressed.
The only cells predating the 31 July 11:03 `train.py` edit are the three at
lr 5e-05, and that edit was the `tokenizer_kwargs` work, which is a no-op for
`biomedbert-base` (empty kwargs, uncased model).

Replicates live in `runs/_recheck/` and are excluded from `summary.jsonl`.

### Resuming

`scripts/run_matrix.py` skips any cell that already holds `test_results.json`, so
the same command picks up the 23 remaining cells (~4 hours):

```bash
HF_HUB_OFFLINE=1 venv310/bin/python3 scripts/run_matrix.py --seeds 42 1 7 --models \
  biomedbert-base bert-base bio-clinicalbert bioelectra-base bio-modernbert-base
```

The interrupted `bio-modernbert-base` lr 5e-05 seed 1 cell left a 1.7 GB
checkpoint behind; it has been deleted, and that cell restarts from scratch.

## Next

- **Tier 1** (local, ~7.3 GPU-hours): `bioelectra-base`, `biolinkbert-base`,
  `bio-modernbert-base`, `modernbert-bio-base` against the baseline, **11 seeds
  each** per the variance measurement above. Answers cheaply whether the encoder
  family matters at all on 860 documents.
- **Tier 2** (TRUBA): the 340–396M candidates, only if Tier 1 separates. bf16 rules
  out `akya-cuda` (V100) for ModernBERT.
- **Tier 3** (highest expected value): fine-tune GLiNER-biomed on the same 860
  documents; TAPT on the unlabelled pathway corpus.
- Wave-3 review remains the dominant lever — an encoder swap is a complement to
  more data, not a substitute.
