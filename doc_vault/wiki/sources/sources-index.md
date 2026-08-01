---
type: meta
title: Sources
status: evergreen
created: 2026-08-01
updated: 2026-08-01
tags:
  - pathway-ner
  - index
  - provenance
project: pathway-ner
source_repo: aenesbedir/Pathway-NER
source_branch: annotator-model-registry
source_commit: 5e7e3f1145d7625855ce8c4fd120a0baba1184a3
last_reviewed: 2026-08-01
---

# Sources

Thirteen repository documents were captured into this vault on **2026-08-01**
from `aenesbedir/Pathway-NER`, branch `annotator-model-registry`, commit
`5e7e3f1145d7625855ce8c4fd120a0baba1184a3`. Each has an immutable
content-addressed copy under `.raw/captured/` and a record in
`wiki/meta/ledgers/source-ledger.json` carrying its SHA-256, locator and review
state.

| Repository path | Feeds |
|---|---|
| `project_tracking.md` | project, pipelines, decisions, lessons |
| `knowledge_base/model_experiments.md` | every run note |
| `knowledge_base/nlp_concepts.md` | [[span\|Span]], [[tokenization\|Tokenization]], [[bio-labeling\|BIO labeling]] |
| `lessons_learned/challenges.md` | [[data-leakage-from-split-strategy\|leakage]] |
| `playground/exact_match_analysis.md` | [[distant-supervision\|Distant supervision]] |
| `playground/silver_1k_analyses.md` | [[phase-3-silver-labeling\|Phase 3]] |
| `reports/base_model_survey_2026-07.md` | [[base-encoder-candidates\|encoder candidates]] |
| `reports/base_model_expansion_analysis_2026-07.md` | [[base-encoder-candidates\|encoder candidates]] |
| `reports/llm_selection_and_hardware_2026-07.md` | [[annotator-llm-and-hardware\|annotator research]] |
| `reports/golden_set_gold-008_results.md` | [[gold-008-vs-teacher-llm\|student vs teacher]] |
| `analysis/data_summary.md` | [[phase-1-original-corpus\|Phase 1]], [[phase-2-pubmed-corpus\|Phase 2]] |
| `analysis/pubmed_year_distribution.md` | [[phase-1-original-corpus\|Phase 1]] |
| `annotation_handoff.md` | [[annotation-strategy\|Annotation strategy]] (historical) |

## Not captured, on purpose

- `CLAUDE.md` — agent instructions, not knowledge. Its rules were applied to this
  migration.
- Runbooks and dataset READMEs that must change in the same commit as their code
  (`pubmed_api/`, `doccano/`, `data/*/README.md`) — referenced by locator only.
- Generated artefacts (`pubmed_api/STATS.md`,
  `playground/golden_set/golden_set.md`) — they regenerate from scripts.
- All datasets, model checkpoints, caches and JSON/JSONL analysis outputs.

The full classification of every Markdown file in the repository is
`documentation-migration-map.yaml` at the vault root.

## Locator convention

Notes cite repository-relative paths. Where a source document contains an
absolute local path in a command block, the note uses the portable
repository-relative form instead.
