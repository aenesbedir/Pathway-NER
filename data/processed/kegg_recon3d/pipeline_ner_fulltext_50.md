# The parametrized pipeline over 50 PMC full texts

`llm/run_silver.py --model runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7`
run over `data/raw/kegg_recon3d/fulltext_50/articles_fulltext_50.json` with
`--text-field full_text --all`, output
`data/processed/kegg_recon3d/pathway_spans_fulltext_50.jsonl`.

Two questions, both answered by `scripts/compare_span_sets.py`; the numbers live in
`opus_vs_pipeline_fulltext_50.json` rather than in a table here.

## 1. Does the pipeline reproduce the earlier direct-inference run?

Against `pathway_predictions_fulltext_50.jsonl` (the same checkpoint driven by
`playground/model_005_analysis/predict_abstracts.py`): 238 agreed names, **zero**
exclusive to the old run, one exclusive to the pipeline — Jaccard 0.996, document
agreement 50/50. The one addition is the deterministic booster's single span.

That is the expected result and it is worth stating plainly: both paths window at
512 tokens with stride 64, so the pipeline changes nothing about the inference. What
it adds is the booster, `canonicalize()` and a resumable per-text cache.

## 2. How does it compare to the Opus full-text annotation?

Against `opus_prediction_fulltext_50_revised.jsonl` (an LLM reading each full text
end-to-end and listing distinct pathway names, revised against
`doccano/ANNOTATION_GUIDE.md`): 169 agreed, 67 Opus-only, 70 pipeline-only, Jaccard
0.552, document-level agreement 48/50. Both find pathways in the same 37 of 50
documents and report a near-identical number of distinct names (161 vs 166).

Neither side is ground truth here, so this is not precision or recall. The
exclusives are the content:

* **Opus-only** is led by umbrella and process terms — `intermediary metabolism`,
  `anaplerosis`, `carbohydrate metabolism`, `phospholipid biosynthesis`. Broad
  category names the checkpoint tends not to tag.
* **Pipeline-only** is led by prose paraphrases of names Opus normalized —
  `synthesis of glycogen`, `catabolism of purines`, `fatty acid synthesis`,
  `energy metabolism`. The model tags the phrase as it appears in the sentence,
  which is what a span annotator should do; the set comparison counts that as a
  disagreement even when both saw the same mention.

The earlier three-way report (`opus_vs_model_fulltext_50.md`) measured against the
*unrevised* Opus output — 391 distinct forms against the revised file's 161 — so its
Jaccard of 0.386 is not comparable to the 0.552 here. The revision, not the pipeline,
moved that number.

## Booster on full text

One span in 481. The concern that the booster would fire heavily on full text — it
scans all 90 Recon canonicals and full text repeats them — did not materialize:
`merge()` keeps the longer span on overlap, and the checkpoint had already found
essentially everything the booster looks for. Same picture as on gt_100 (one added
span in 260) and on the KEGG abstracts (three in 818).
