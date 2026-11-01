# Sentence-shuffle augmentation: first local result

Date: 2026-10-31
Status: One seed, local run. The comparison is not final until the three TRUBA
seeds finish (see "Pending").

## Question

Does adding sentence-shuffle copies to the training split improve pathway NER
over the plain 10k + missing corpus?

## Run

- Model: `biomedbert-base`, lr 3e-5, seed 42, 40 epochs maximum, patience 8.
- Code: commit `5f3d407` on `feat/sentence-shuffle`.
- Corpus: `pathway-10k-missing-shuffle`, built with k=2, n=2, seed 42.
- Split: 26,175 train / 1,087 val / 1,088 test. Validation and test lists are
  those of `pathway-10k-missing`; only the training data changed.
- Environment: RTX 4060 Laptop, torch 2.12.0+cu130, transformers 5.10.2, bf16.
- Stopped at epoch 29; best epoch 21 (val F1 0.8982). Runtime about 4.5 hours.

## Results

| Metric | Baseline, seed 42 | Baseline, 3-seed mean | Shuffle, seed 42 |
|---|---|---|---|
| Test F1 (1,088 docs) | 0.8885 | 0.8908 (0.8885-0.8933) | 0.8984 |
| gt_100 exact F1 | 0.8088 | 0.8076 (0.8066-0.8088) | 0.8214 |
| gt_100 partial F1 | 0.8971 | 0.8995 (0.8926-0.9088) | 0.9024 |
| gt_125 exact F1 | not available | not available | 0.8159 |
| gt_125 partial F1 | not available | not available | 0.8895 |

Baseline is `biomedbert-base`, lr 3e-5, on `pathway-10k-missing`, trained on
TRUBA. Its gt_100 scores come from `analysis/gt_100_from_predictions.json`.

## Reading

- Test F1 is above all three baseline seeds, by 0.005 over the best one.
- gt_100 exact is above the baseline range by 0.013, about 3-4 spans.
- gt_100 partial is inside the baseline range, so it shows no clear gain.
- `biom-electra-large` lr 3e-5 on the plain corpus stays ahead on the clean sets:
  gt_100 exact 0.8379, gt_125 exact 0.8297.

## Limits

- One seed against three.
- Different environment: this run used transformers 5.10.2 on an RTX 4060, the
  baseline used transformers 5.14.1 on a V100, so part of the gap may be the
  environment.
- The test split includes silver documents. gt_100 and gt_125 are the clean sets.
- gt_125 has no baseline for this model, because the baseline
  `test_predictions.jsonl` files were deleted. A retrain is needed to get one.

## Pending

TRUBA job 6875351 must be checked. It holds the same model and corpus for seeds
42, 1 and 7, writing to `runs-truba-10k-missing-shuffle/`. It was still pending
(reason `Priority`) at the last check on 2026-11-01. Once it finishes, fetch the
results, score test, gt_100 and gt_125, and compare with this run. Every TRUBA
command needs the user's approval first (AGENTS.md).

## Locations

All under `/home/enes/artifacts/checkpoints/ner_pathway-10k-missing-shuffle/`:

- Model and run files:
  `pathway-10k-missing-shuffle/biomedbert-base/lr3e-05/seed42/`
- Provenance: `provenance.json`
- gt_100 and gt_125 scores: `gt_100_scores.json`, `gt_125_scores.json`
- Run summary and training log: `summary-local.jsonl`,
  `train_10k_shuffle_local.log`

The original run directory is `runs/10k-missing-shuffle-local/` in the main
checkout (git-ignored).
