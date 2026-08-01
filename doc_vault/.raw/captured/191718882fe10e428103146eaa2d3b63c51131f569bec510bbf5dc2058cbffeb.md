# NLP Knowledge Base

Concepts, methods, and keywords encountered during the Metabolic Pathway NER pipeline project.

---

## Span

**Definition:** A contiguous segment of text identified by its start and end character positions within a source string.

**Structure:**
```json
{"start": 42, "end": 61, "text": "glycolytic pathway", "source": "abstract"}
```

**Purpose:** The fundamental unit of annotation in NER. Before a model can be trained, every entity mention in raw text must be recorded as a span so we know exactly where in the text the entity appears.

**Key details:**
- Offsets are **character-level**, not word or token level — `text[start:end]` always reproduces the exact matched string
- Multiple spans can exist in the same text (e.g. a pathway named twice in one abstract)
- Spans must be converted to token-level BIO labels before a BERT-style model can use them (see: BIO Tagging, Token Alignment)
- In this project, spans come from three sources: SpaCy PhraseMatcher (exact), LLM extraction (verified verbatim), and character offset resolution from the DB dataset

---

## Tokenization

**Definition:** The process of converting raw text into a sequence of integer IDs that a language model can consume, using a fixed vocabulary learned during pre-training.

**Purpose:** Neural models operate on numbers, not strings. Tokenization is the bridge between human-readable text and the numerical input the model expects. It must use the exact same vocabulary and rules the model was pre-trained with — using a different tokenizer would produce meaningless inputs.

**How it works (WordPiece — used by BERT/BiomedBERT):**
- Common words stay whole: `"glucose"` → `["glucose"]`
- Rare or long words are split into subword pieces: `"glycolytic"` → `["glyco", "##lytic"]`
- The `##` prefix marks a continuation piece (not the start of a new word)
- Special tokens are added: `[CLS]` at the start, `[SEP]` at the end

**Why it matters for NER (Step 4 specifically):**
- Your spans are character-level offsets into raw text
- After tokenization, a 5-word sentence may become 9 tokens — the offsets no longer map 1-to-1
- Step 4 uses `offset_mapping` from the HuggingFace fast tokenizer to re-align character positions to token positions, so BIO labels can be assigned correctly

**Key outputs:**
- `input_ids` — integer token IDs the model reads
- `attention_mask` — marks real tokens (1) vs padding (0)
- `offset_mapping` — maps each token back to its character range in the original text (used for span alignment, then discarded)

**In this project:** `AutoTokenizer.from_pretrained("microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext")` — must match the model exactly.

---

## Labels (Token Labels)

**Definition:** A per-token integer assigned to every token in a tokenized sequence, telling the model what class that token belongs to during training.

**Purpose:** Labels are the supervision signal — the "correct answer" the model learns to predict. For NER, each token gets its own label rather than the whole sequence getting one label (that would be text classification). This is called **token classification**.

**Label scheme used in this project:**

| Value | Name | Meaning |
|---|---|---|
| `0` | O | Outside — not part of any entity |
| `1` | B-Pathway | Beginning of a pathway mention |
| `2` | I-Pathway | Inside (continuation of) a pathway mention |
| `-100` | ignore | Special tokens (`[CLS]`, `[SEP]`) and subword continuations — loss function skips these |

**Why -100 specifically:**
PyTorch's `CrossEntropyLoss` ignores any position where the label is `-100` by default. This is a hardcoded convention in HuggingFace. It serves two purposes:
- Special tokens (`[CLS]`, `[SEP]`) have no meaningful entity label
- Subword continuations (`##lytic`) shouldn't be trained independently — only the first subword of a word is labeled, the rest are masked with `-100`

**Example:**

```
Text   :  "the  glyco ##lytic  path ##way  was"
Label  :   -100   1    -100     2    -100    0   -100
           CLS   B     ##cont  I    ##cont   O   SEP
```

**Key detail — class imbalance:** In a typical biomedical abstract, 98%+ of tokens are O. This imbalance is expected and normal for NER. It can be addressed during training with weighted loss or by ensuring enough positive examples in each batch.

---
