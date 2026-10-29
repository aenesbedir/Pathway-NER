# Pathway NER model scores — gt_100 and pathway-10k test

Date: 2026-08-25

Two evaluation sets for the same nine checkpoints:

- **gt_100** — 100 manually curated abstracts, 279 gold PATHWAY spans
  (`doccano/golden_dataset/gt_100.jsonl`). Scores read from
  `doccano/golden_dataset/gt_100_scores.json`.
- **pathway-10k test** — the 1,013-document test split of the 10,125-document
  silver corpus, whose labels come from query-vocabulary matching rather than
  manual curation. Scores produced by `scripts/eval_on_10k_test.py`
  (`analysis/eval_10k_test.json`).

Both use the entity-level seqeval metric of `train.py`, so the two columns are
computed the same way; only the reference labels differ. The gt_100 file also
reports a `partial` metric — gold-coverage F1 at threshold 0.5, where a
predicted span counts when it covers at least 50 % of the gold span's
characters, matched greedily one-to-one. Partial never replaces exact.

Parameter counts were read from each `model.safetensors` header and include the
token-classification head.

## Models on gt_100

Ordered by seqeval F1.

| # | Model | Params | L / H | vocab | max_tok | seq F1 | seq P | seq R | part F1 | part P | part R |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | pathway-10k/biom-electra-large lr3e-05 s7 | 332.4M | 24 / 1024 | 28895 | 512 | 0.8358 | 0.8682 | 0.8058 | 0.8939 | 0.9302 | 0.8602 |
| 2 | pathway-10k/bioelectra-base lr3e-05 s7 | 108.9M | 12 / 768 | 30522 | 512 | 0.8194 | 0.8494 | 0.7914 | 0.8922 | 0.9266 | 0.8602 |
| 3 | pathway-10k/biomedbert-base lr5e-05 s1 | 108.9M | 12 / 768 | 30522 | 512 | 0.8141 | 0.8423 | 0.7878 | 0.8980 | 0.9308 | 0.8674 |
| 4 | gold-wave4-random-all-biomedbert-base | 108.9M | 12 / 768 | 30522 | 512 | 0.8126 | 0.8391 | 0.7878 | 0.8926 | 0.9234 | 0.8638 |
| 5 | pathway-10k/biolinkbert-base lr5e-05 s7 | 107.6M | 12 / 768 | 28895 | 512 | 0.8059 | 0.8289 | 0.7842 | 0.9004 | 0.9278 | 0.8746 |
| 6 | gold-wave4-biomedbert-base-min30 | 108.9M | 12 / 768 | 30522 | 512 | 0.7970 | 0.8182 | 0.7770 | 0.8913 | 0.9167 | 0.8674 |
| 7 | pathway-10k/biolinkbert-large lr3e-05 s1 | 332.4M | 24 / 1024 | 28895 | 512 | 0.7815 | 0.8053 | 0.7590 | 0.8835 | 0.9122 | 0.8566 |
| 8 | gold-wave4-biomedbert-base | 108.9M | 12 / 768 | 30522 | 512 | 0.7537 | 0.7829 | 0.7266 | 0.8529 | 0.8876 | 0.8208 |
| 9 | gold-wave4-random-all-bio-modernbert-base | 149.6M | 22 / 768 | 50368 | 8192 | 0.7394 | 0.7266 | 0.7527 | 0.8451 | 0.8304 | 0.8602 |

All 100 gt_100 PMIDs fall in the *test* split of `data/processed/pathway-10k`,
so the `runs-truba-checkpoints/pathway-10k/*` models never trained on them. A
PMID with no prediction counts as zero predictions rather than being dropped.

Parameter count does not predict rank: the 332.4M biolinkbert-large sits at #7,
below every 108.9M base model. Within the identical 108.9M BiomedBERT body the
spread is 0.7537–0.8194, so the difference comes from the training data
(10k silver vs gold-wave4), not the architecture.

## Span sources on gt_100

Not models — these are the raw span sets the training data was built from,
scored by exact character-offset match.

| Source | PMIDs with predictions | pred spans | exact F1 | exact P | exact R | part F1 | part P | part R |
|---|---|---|---|---|---|---|---|---|
| 10k dataset (`data/processed/pathway-10k/matches.jsonl`) | 91/100 | 261 | 0.8815 | 0.9119 | 0.8530 | 0.9259 | 0.9579 | 0.8961 |
| local LLM silver, qwen2.5:14b (`data/silver/pathway_remaining_6125.jsonl`) | 87/100 | 223 | 0.7689 | 0.8655 | 0.6918 | 0.8008 | 0.9013 | 0.7204 |

The LLM silver bottleneck is recall: 223 predicted spans against 279 gold, and
76 gold spans have no overlapping LLM span at all. The misses are systematically
free-text pathway mentions outside the query vocabulary — "production of
reactive oxygen species", "AA cascade", "DNPS pathway", "energy metabolism". By
match type the produced spans are near-perfect (exact 69/70, synonym 7/7,
variation 25/26 land on gold); only `unmapped` lags at 92/120.

An earlier 10k figure of exact F1 0.8848 was scored on only the 91 PMIDs present
in `matches.jsonl`; that basis dropped exactly the recall failures and has been
superseded by the 100-PMID basis above.

## Models on the pathway-10k test split

1,013 records. Recomputed F1 for the five sweep checkpoints matches their
recorded `test_results.json` exactly, which validates the evaluation script.

| Model | Params | F1 | P | R | Contamination |
|---|---|---|---|---|---|
| gold-wave4-random-all-biomedbert-base | 108.9M | 0.9231 | 0.9201 | 0.9262 | 292 records seen in training |
| gold-wave4-biomedbert-base-min30 | 108.9M | 0.8953 | 0.8871 | 0.9037 | 274 seen |
| gold-wave4-biomedbert-base | 108.9M | 0.8953 | 0.8939 | 0.8968 | 274 seen |
| pathway-10k/biom-electra-large | 332.4M | 0.8858 | 0.8803 | 0.8914 | clean |
| pathway-10k/biolinkbert-base | 107.6M | 0.8822 | 0.8735 | 0.8910 | clean |
| pathway-10k/bioelectra-base | 108.9M | 0.8812 | 0.8727 | 0.8898 | clean |
| pathway-10k/biomedbert-base | 108.9M | 0.8790 | 0.8689 | 0.8894 | clean |
| pathway-10k/biolinkbert-large | 332.4M | 0.8780 | 0.8620 | 0.8947 | clean |
| gold-wave4-random-all-bio-modernbert-base | 149.6M | 0.8063 | 0.7584 | 0.8607 | unknown, see below |

### Contamination-corrected subset

The pathway-10k splits are random over the same 10,125 documents the gold-wave4
sets were drawn from, so the gold-trained checkpoints have already seen part of
the 10k test split — 264 of its 1,013 PMIDs appear in gold-wave4 train, plus a
handful in val. Removing those records gives:

| Model | clean n | F1 | P | R | Δ F1 vs full |
|---|---|---|---|---|---|
| gold-wave4-random-all-biomedbert-base | 721 | 0.8998 | 0.8966 | 0.9031 | −0.0233 |
| gold-wave4-biomedbert-base | 739 | 0.8670 | 0.8682 | 0.8658 | −0.0283 |
| gold-wave4-biomedbert-base-min30 | 739 | 0.8639 | 0.8543 | 0.8737 | −0.0314 |

Even on the clean subset the `random-all` gold checkpoint stays ahead of every
10k-trained model at 0.8998 — a model trained on manually curated labels scores
higher on the silver test set than models trained on the silver labels
themselves.

`gold-wave4-random-all-bio-modernbert-base` has no `test_results.json` (only
`checkpoint-160/`), so its training PMIDs could not be recovered and no clean
subset was computed; its 0.8063 is the uncorrected number.

## Reading the two tables together

The rankings partly invert between gt_100 and pathway-10k test, and that is
expected: the 10k labels are silver, produced by query-vocabulary matching, so
that column measures agreement with the matcher, not correctness against
curated spans. gt_100 is the accuracy measure; pathway-10k test is a consistency
measure against the silver-generation process.

## Reproducing

```bash
venv310/bin/python3 scripts/eval_on_10k_test.py      # writes analysis/eval_10k_test.json
venv310/bin/python3 scripts/score_gt_100.py          # writes doccano/golden_dataset/gt_100_scores.json
```

The bio-modernbert tokenized 10k dataset did not exist and was generated with
the same steps `scripts/prepare_pathway_10k.sh` runs for the other tokenizers,
against the same `data/processed/pathway-10k/splits.json`:

```bash
venv310/bin/python3 preprocessing/tag_bio.py \
    --matches data/processed/pathway-10k/matches.jsonl \
    --articles data/processed/pathway-10k/articles.jsonl \
    --output data/processed/pathway-10k-bio-modernbert-base/bio_tags.jsonl \
    --db "" --model bio-modernbert-base --include-span-free

venv310/bin/python3 preprocessing/build_dataset.py \
    --input data/processed/pathway-10k-bio-modernbert-base/bio_tags.jsonl \
    --outdir data/processed/pathway-10k-bio-modernbert-base \
    --splits data/processed/pathway-10k/splits.json --keep-span-free
```
