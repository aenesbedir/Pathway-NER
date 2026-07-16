"""
Guided whole-abstract pathway surface extraction prompt.

Unlike pathway_extraction.py (one pathway per call, vocab-blind), this prompt
processes a full abstract in a single call and hints:
  - the query pathway(s) that retrieved the article, and
  - optionally the full Recon vocabulary (98 canonical names).

The model returns ONLY surface strings as they appear in the text. Canonical
mapping to the 98 Recon names is done downstream by us, not the model.

Two variants are compared on the golden set (see eval_llm_guided.py):
  - without the vocab block (query-pathway hints only)
  - with the vocab block
to decide whether the 98-name list helps precision or just adds noise (long
prompts hurt smaller models — cf. V3 few-shot regression in pathway_extraction.py).
"""

GUIDED = """\
Text:
\"\"\"{text}\"\"\"

You are extracting metabolic pathway mentions to build NER training data.

Pathways already known to be relevant to this article (look for these first, but \
also find any others that appear):
{query_pathways}
{vocab_block}
Task: Return every string in the text that explicitly NAMES a metabolic pathway \
or metabolic process. Include abbreviations, alternative names, synonyms \
(including a compound's alternative chemical name), and word-order variants \
(e.g. "metabolism of X" for "X metabolism"), and umbrella terms \
(e.g. "amino acid metabolism").

Rules:
{rules}

Return ONLY a JSON object: {{"mentions": ["exact string as in text", ...]}} \
or {{"mentions": []}} if none are found. Do not explain. Do not add text outside \
the JSON."""

# Rule variants (compared on the golden set to test whether the compound-name
# exclusion wrongly suppresses pathway phrases that contain a compound name).
RULES_STRICT = """\
- Return each mention exactly as it appears in the text (verbatim substring).
- Do NOT return enzyme, protein, gene, metabolite, or compound names — even if \
they are related to a pathway.
- Do NOT return a string that does not appear verbatim in the text."""

# LENIENT: a bare metabolite/compound on its own is still excluded, but a pathway
# phrase is kept even when it is built from a compound name. Examples are schematic
# (no golden surface strings) to avoid leaking eval answers.
RULES_LENIENT = """\
- Return each mention exactly as it appears in the text (verbatim substring).
- Do NOT return a bare enzyme, protein, gene, metabolite, or compound name on its \
own (a molecule mentioned by itself, e.g. a single amino acid, an acid, a hormone).
- BUT DO return the full pathway phrase even when it is built from a compound name \
— e.g. "<compound> metabolism", "<compound> biosynthesis", "synthesis of <compound>", \
"formation of <compound>". The metabolic process word (metabolism / synthesis / \
biosynthesis / catabolism / oxidation / degradation / formation) makes it a pathway.
- Do NOT return a string that does not appear verbatim in the text."""

# Inserted into {vocab_block} when the vocab variant is used.
VOCAB_BLOCK = """
Canonical pathway vocabulary for reference (mentions in the text may be surface \
variants of these — do NOT restrict yourself to these exact spellings, and do NOT \
invent names that are not supported by the text):
{vocab_list}
"""
