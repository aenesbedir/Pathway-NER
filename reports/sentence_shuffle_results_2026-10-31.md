# Sentence-shuffle augmentation: first local result

Date: 2026-10-31
Status: One local seed at 40 epochs, plus three TRUBA seeds at 20 epochs (see
"TRUBA, 20 epochs, three seeds").

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

## TRUBA, 20 epochs, three seeds (added 2026-11-08)

The 40-epoch TRUBA job 6875351 never left the queue and was cancelled. It was
replaced by job 6901057, which caps training at 20 epochs so that it fits a
6.5-hour slot (`slurm/sweep_10k_missing_shuffle_e20.slurm`).

- Model: `biomedbert-base`, lr 3e-5, seeds 42, 1, 7, 20 epochs maximum,
  patience 8.
- Code: commit `3c79a39`, the same for all three seeds.
- Corpus: `pathway-10k-missing-shuffle`, shuffle version 1 (`k2_n2_seed42`),
  recorded in `data/processed/pathway-10k-missing-shuffle/manifest.json`.
- Environment: TRUBA akya-cuda, V100, bf16. About 5.0 hours per seed.
- All three ran the full 20 epochs; best epochs 17, 19 and 12.
- Scores: `analysis/gt_100_10k_missing_shuffle_e20.json` and
  `analysis/gt_125_10k_missing_shuffle_e20.json`. Each row carries a `training`
  block with the data paths, their sha256 and the corpus manifest.

| Metric | Baseline, 3-seed mean | Shuffle 40 ep, seed 42 (local) | Shuffle 20 ep, 3-seed mean (range) |
|---|---|---|---|
| Test F1 | 0.8908 (0.8885-0.8933) | 0.8984 | 0.8968 (0.8943-0.8997) |
| gt_100 exact F1 | 0.8076 (0.8066-0.8088) | 0.8214 | 0.8123 (0.7948-0.8296) |
| gt_100 partial F1 | 0.8995 (0.8926-0.9088) | 0.9024 | 0.8978 (0.8955-0.9017) |
| gt_125 exact F1 | not available | 0.8159 | 0.7988 (0.7834-0.8101) |
| gt_125 partial F1 | not available | 0.8895 | 0.8808 (0.8783-0.8859) |

Per seed (42 / 1 / 7): test 0.8963 / 0.8943 / 0.8997, gt_100 exact
0.7948 / 0.8126 / 0.8296, gt_125 exact 0.7834 / 0.8030 / 0.8101.

### Reading

- Test F1 is above every baseline seed for all three shuffle seeds; the mean
  gain is 0.006.
- gt_100 exact varies by 0.035 across seeds, more than the gain being measured.
  The mean is 0.005 above the baseline mean, and the range overlaps it on both
  sides, so the clean set shows no clear gain.
- gt_100 partial is level with the baseline.
- These runs differ from the baseline in epoch cap as well as data. The learning
  rate decays linearly over the cap, so 20 epochs is a different schedule from
  the baseline's 40, not a shortened copy of it. A 20-epoch baseline would
  separate the two effects.

## Pending

- A 20-epoch baseline on `pathway-10k-missing` for the same three seeds, if a
  matched comparison is wanted.
- A gt_125 baseline still needs a retrain (see Limits).

Every TRUBA command needs the user's approval first (AGENTS.md).

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

The 20-epoch TRUBA runs (no weights: predictions, results, logs, scores) are in
`truba-e20/` under the same directory; their original directory is
`runs-truba-10k-missing-shuffle-e20/` in the main checkout (git-ignored).
