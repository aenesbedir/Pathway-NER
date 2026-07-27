# Gold dataset (review-corrected)

Training dataset built from the **reviewed** silver labels — not raw silver. Each
span is the silver output with review corrections applied: false positives dropped,
false negatives added, true positives kept (gold = `tp + fn` per document).

Two sources feed this dataset (no PMID overlap):

| source | reviewed labels | docs |
|--------|-----------------|------|
| wave-2 silver (qwen2.5:14b) | `analysis/wave2_batch0[1-5]_review.json` | 1000 |
| pilot-1k batch 05 | `analysis/batch_05_5_review.json` (docs 1–50 human, 51–200 assistant review) | 200 |

## Provenance chain

```
data/silver/wave2_1k.jsonl                         raw machine output (SILVER)
  └─ doccano/export_doccano.py  → doccano/wave2_1k_doccano.jsonl
       └─ doccano/split_batches.py → doccano/batches/wave2_1k_doccano_batch_NN_5.jsonl
            └─ review (drop FP, add FN) → analysis/wave2_batchNN_review.json
                 └─ doccano/build_gold_from_review.py → doccano/wave2_1k_gold.jsonl   (GOLD = tp+fn)
pilot: analysis/batch_05_5_review.json               → doccano/pilot_1k_batch05_gold.jsonl
                 └─ (gold → matches + articles) → preprocessing/tag_bio.py → bio_tags.jsonl
                      └─ preprocessing/build_dataset.py → {train,val,test}.jsonl
```

## Files

| file | rows | note |
|------|------|------|
| `matches.jsonl` | 1083 | gold spans as `tag_bio` input (`source="abstract"`, `pathway_id="gold"`); docs with ≥1 span only |
| `articles.jsonl` | 1200 | pmid → abstract text (all docs, incl. span-free) |
| `bio_tags.jsonl` | 1083 | BIO-tagged, BiomedBERT tokenizer |
| `train.jsonl` | 860 pmids / 5943 pos tokens | 80% |
| `val.jsonl` | 107 pmids / 673 pos tokens | 10% |
| `test.jsonl` | 109 pmids / 709 pos tokens | 10% |

`build_dataset.py` drops docs with no positive labels: 1200 docs → 1083 with spans
→ 1076 with B/I tokens after tokenization (7 lost to 512-token truncation) → split.
Split is PMID-stratified, seed 42.

## Regenerate

```bash
# 1. reviews → doccano gold
venv310/bin/python3 doccano/build_gold_from_review.py

# 2. gold → matches + articles (both sources, into data/processed/gold/)
python3 - <<'PY'
import json
from pathlib import Path
srcs = ["doccano/wave2_1k_gold.jsonl", "doccano/pilot_1k_batch05_gold.jsonl"]
matches, articles, seen = [], [], set()
for s in srcs:
    for line in open(s, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line); pmid = str(r["meta"]["pmid"])
        assert pmid not in seen, f"duplicate pmid {pmid}"
        seen.add(pmid)
        articles.append({"pmid": pmid, "abstract": r["text"], "full_text": ""})
        spans = [{"start": a, "end": b, "source": "abstract"} for a, b, _ in r["label"]]
        if spans:
            matches.append({"pmid": pmid, "pathway_id": "gold", "spans": spans})
Path("data/processed/gold/matches.jsonl").write_text(
    "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in matches), encoding="utf-8")
Path("data/processed/gold/articles.jsonl").write_text(
    "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in articles), encoding="utf-8")
PY

# 3. matches + articles → BIO tags (needs transformers; model cached)
HF_HUB_OFFLINE=1 venv310/bin/python3 preprocessing/tag_bio.py \
    --matches  data/processed/gold/matches.jsonl \
    --articles data/processed/gold/articles.jsonl \
    --output   data/processed/gold/bio_tags.jsonl \
    --db ""

# 4. BIO tags → train/val/test
venv310/bin/python3 preprocessing/build_dataset.py \
    --input  data/processed/gold/bio_tags.jsonl \
    --outdir data/processed/gold
```
