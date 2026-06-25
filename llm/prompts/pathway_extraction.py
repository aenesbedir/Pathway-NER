"""
Prompt templates for pathway name extraction from biomedical text.

Benchmarked on 450 records from extracted_disease_pathway_db using qwen2.5:7b.
Active prompt is V1. Switch by changing ACTIVE in extract_pathway_from_db.py.
"""

# ── V1 — Zero-shot with rules (ACTIVE) ───────────────────────────────────────
# Result: 296/450 found (65.8%) — best precision, fewest false positives.
V1_ZERO_SHOT = """\
Text:
\"\"\"{text}\"\"\"

Task: Does the text above explicitly name the metabolic pathway "{pathway_name}" \
or use an abbreviation or alternative name FOR THE PATHWAY ITSELF?

Rules:
- Only return the name of the pathway as it appears in the text.
- Do NOT return enzyme names, protein names, gene names, metabolite names, or \
compound names — even if they are related to this pathway.
- Do NOT return a string that does not appear verbatim in the text.
- If the pathway is not explicitly named, return {{"matches": []}}.

Return ONLY a JSON object: {{"matches": ["exact pathway name as in text"]}} \
or {{"matches": []}} if not found.
Do not explain. Do not add any text outside the JSON."""


# ── V2 — Zero-shot + word-order variant rule ──────────────────────────────────
# Added explicit instruction to catch inverted forms like "metabolism of X"
# for "X metabolism" (motivated by PMID 41998452).
# Result: 294/450 found (65.3%) — slight regression vs V1. The extra rule
# confused the model on edge cases more than it helped.
V2_WORD_ORDER = """\
Text:
\"\"\"{text}\"\"\"

Task: Does the text above explicitly name the metabolic pathway "{pathway_name}" \
or use an abbreviation or alternative name FOR THE PATHWAY ITSELF?

Rules:
- Only return the name of the pathway as it appears in the text.
- Do NOT return enzyme names, protein names, gene names, metabolite names, or \
compound names — even if they are related to this pathway.
- Do NOT return a string that does not appear verbatim in the text.
- If the pathway is not explicitly named, return {{"matches": []}}.
- Also look for inverted word-order variants such as "metabolism of X" when the \
pathway is "X metabolism", and cases where the pathway components appear with \
additional terms (e.g. "metabolism of alanine, aspartate, and glutamate" for \
"Alanine and aspartate metabolism").

Return ONLY a JSON object: {{"matches": ["exact pathway name as in text"]}} \
or {{"matches": []}} if not found.
Do not explain. Do not add any text outside the JSON."""


# ── V3 — Few-shot with entity definition and labeled examples ─────────────────
# Based on research: static few-shot prompting improves F1 by ~12% on GPT-4/
# LLaMA-70B (arxiv 1810.06818, PMC12408026). Added entity definition + 5
# examples (3 positive, 2 negative).
# Result: 198/450 found (44.0%) — significant regression on qwen2.5:7b.
# Negative examples made the model overly conservative; longer prompt confused
# the smaller model. Revisit with GPT-4, Llama 3.1 70B, or Qwen2.5 72B.
V3_FEW_SHOT = """\
You are an expert biomedical annotator creating NER training data. Your task is \
to find mentions of a specific metabolic pathway in a text.

ENTITY DEFINITION:
A metabolic pathway mention is any string in the text that explicitly names the \
pathway itself — including standard names, abbreviations, and inverted word-order \
forms (e.g. "TCA cycle" or "cycle of tricarboxylic acids" for "Citric acid cycle", \
"metabolism of alanine and aspartate" for "Alanine and aspartate metabolism"). \
It is NOT an enzyme name, gene name, protein name, or metabolite/compound name, \
even if those are involved in the pathway.

EXAMPLES:

Example 1 — exact match found:
Pathway: "Arachidonic acid metabolism"
Text: "...Arachidonic acid metabolism plays a central role in inflammatory signaling..."
Answer: {{"matches": ["Arachidonic acid metabolism"]}}

Example 2 — abbreviation found:
Pathway: "Citric acid cycle"
Text: "...flux through the TCA cycle was significantly elevated in tumor cells..."
Answer: {{"matches": ["TCA cycle"]}}

Example 3 — inverted word-order found:
Pathway: "Alanine and aspartate metabolism"
Text: "...alterations in the metabolism of alanine, aspartate, and glutamate were observed..."
Answer: {{"matches": ["metabolism of alanine, aspartate, and glutamate"]}}

Example 4 — pathway implied but NOT named (enzyme/metabolite only):
Pathway: "Pentose phosphate pathway"
Text: "...PRPP synthase and ribose-1-phosphate were analyzed in E. coli..."
Answer: {{"matches": []}}

Example 5 — wrong entity type (metabolite, not pathway):
Pathway: "Hippurate metabolism"
Text: "...elevated hippuric acid levels were detected in urine samples..."
Answer: {{"matches": []}}

NOW YOUR TASK:
Pathway: "{pathway_name}"
Text:
\"\"\"{text}\"\"\"

Return ONLY a JSON object: {{"matches": ["exact string as it appears in text"]}} \
or {{"matches": []}} if the pathway is not explicitly named.
Do not explain. Do not add any text outside the JSON."""


# ── Option B (not yet implemented) ───────────────────────────────────────────
# Token overlap post-processing as a deterministic fallback after LLM.
# For each sentence in the abstract, check if ≥N key tokens from the pathway
# name appear. If yes, extract the span. Catches word-order variants and
# supersets (e.g. "metabolism of alanine, aspartate, and glutamate") without
# relying on the model to interpret prompt instructions.
# Recommended next step for improving recall without hurting precision.


# Active prompt used by extract_pathway_from_db.py
ACTIVE = V1_ZERO_SHOT
