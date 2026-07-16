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

- **Failure mode is abstention, not error** — it never maps to a wrong canonical. A wrong
  canonical would silently corrupt scope filtering; `unmapped` just routes to the human.
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
