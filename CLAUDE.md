# Project rules

## Every recorded run must be traceable to a code snapshot

Before starting any run whose numbers will be kept — a grid cell, a gold-00N
training run, an evaluation that lands in a report — the pipeline must be
committed. "The pipeline" means every file the run reads or executes:

    train.py  encoders.py  preprocessing/*.py  scripts/*.py

`scripts/run_matrix.py` stamps each summary row with `git_sha`, but that field
only identifies the run if the working tree was clean when it started. With
uncommitted changes the sha names a snapshot that never produced the result, and
the only remaining evidence is file mtimes.

This is not hypothetical. On 2026-07-31 a `biomedbert-base` cell recorded at F1
0.8199 on 29 July failed to reproduce — two replicates gave 0.7662 and 0.7736.
Deciding whether the cause was a code change or run-to-run nondeterminism meant
comparing `stat` timestamps of `train.py` against run directories, because the
changes between the two dates had never been committed. A clean tree would have
answered it with `git diff <sha1> <sha2>`.

Practically:

- `git status --porcelain` returns nothing for the pipeline files before a sweep
  starts. Commit the work first, however small.
- A run interrupted mid-sweep resumes on the same commit. If the code has to
  change to fix a failure, the already-completed cells were produced by different
  code — either re-run them or record the boundary explicitly.
- Never edit a pipeline file while a sweep is running. Python reads each script
  once at process start, so an edit lands silently on the *next* cell and splits
  one table across two code versions.

## What belongs in git

Tracked: source, documentation, and the frozen split (`data/processed/gold/splits.json`)
— the split is the contract that makes two encoders comparable.

Not tracked: per-tokenizer datasets, per-run directories, model checkpoints, logs
and generated analysis dumps. All of them regenerate from tracked inputs; see
`.gitignore` for the reasoning attached to each rule.

## Results have one source of truth

Each run writes `test_results.json` into its own directory; `run_matrix.py`
copies that file verbatim into `runs/summary.jsonl` and adds `git_sha`, `wall_s`
and `run_dir`. Summary is therefore an index over the run directories, not an
independent record.

Do not maintain hand-written result tables in markdown. They drift from the run
data and there is no way to notice. Derive tables with `scripts/aggregate_runs.py`
when they are needed.

Fields belong in `test_results.json` when they are a final metric, part of the
configuration, or required to choose a model. Diagnostics that are interesting
once — early-stopping epochs, throughput — stay in the run directory.
