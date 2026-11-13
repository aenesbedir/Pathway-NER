# How Kev decides a relation: one gt_100 pair through the network

Kev is the decision model we fine-tune for pathway–disease relation
classification (`relation_extraction/decision_models/`). It does not generate
text. It reads the abstract and the question as one token sequence, then
*points* at one of the answer options. This document follows one real gt_100
pair through every step and gives the shape and meaning of each tensor
that is passed on.

![Kev-4B forward pass for one gt_100 pair](kev_architecture.svg)

The editable source of the figure is `kev_architecture.excalidraw` (open it at
excalidraw.com).

## Where the numbers come from

| What | Source | Exact? |
|---|---|---|
| Layer sizes | `config.json` and the safetensors headers of `Qwen/Qwen3.5-4B-Base@1001bb4d` | yes |
| Model code | Kev at `2074cc44` (`kev/model.py`, `kev/api.py`, `kev/data.py`) | yes |
| Token counts and positions | Qwen3.5-4B tokenizer at the same revision, applied with Kev's encoding rules to the record that `build_kev_data.py --gt100` writes | yes (see note) |
| Probabilities | `gt_100_predictions.json` of the TRUBA run `kev-4b_silver_6893708` (Kev-4B, 1 epoch on the old `silver_2k_full` split) | yes, from that run |
| Values of intermediate vectors | not measured; only their shapes are given | no |

Note on tokens: the counts were computed locally with `tokenizers` 0.22.2 from
the model's own `tokenizer.json`; Kev runs `tokenizers` 0.23.2 through
transformers. Both read the same tokenizer file, so the counts should match,
but they were not checked inside Kev itself.

The probabilities are for illustration only. They come from one run on the old
data, not from the current `silver_2k_10kplusmissing` sweep, and are not a
result to cite.

## The example

gt_100 pair `c20f1d81558adc64`, stratum `same_sentence`:

- pathway: `heme degradation`
- disease: `renal disease`
- reference label (Fable teacher): `downregulation`

The abstract says that *increasing* heme oxygenase activity, which drives heme
degradation, is beneficial in renal disease. Under the labelling rule for
interventions, "activating the pathway helps" means `downregulation`.

## Step by step

Notation: `[n]` is a vector of n numbers, `[a × b]` is a matrix of a rows of
b numbers each. `L = 444` is the length of this example's token row, and
`d = 2560` is the model's hidden size.

| # | Tensor | Shape | Meaning |
|---|---|---|---|
| 1 | labelled request | JSON | state (abstract, pathway, disease) and one `choice` question with 5 criteria |
| 2 | `ids` | `[444]` integers | token ids of state + instruction + 5 options + `<decide>` |
| 3 | `X` | `[444 × 2560]` | one embedding vector per token, looked up from a 248,320 × 2560 table |
| 4 | layer outputs | `[444 × 2560]` each | after every one of the 32 layers, one context-aware vector per token |
| 5 | `H` | `[444 × 2560]` | the final layer's output after RMSNorm (`last_hidden_state`) |
| 6 | `h_decide`, `H_opt` | `[2560]`, `[5 × 2560]` | the vectors at `<decide>` and at the five `</opt>` tokens |
| 7 | `q`, `K`, `z` | `[256]`, `[5 × 256]`, `[5]` | query, keys and one score (logit) per option |
| 8 | `p` | `[5]` | probabilities over the five labels; the answer is the largest |
| 9 | loss | scalar | cross-entropy against the label (training only) |

### 1. Labelled request

`build_kev_data.py` writes one JSON record per pair:

```
state:
  abstract: <abstract with [[PATHWAY]]heme degradation[[/PATHWAY]] and
             [[DISEASE]]renal disease[[/DISEASE]] marked>
  pathway: heme degradation
  disease: renal disease
questions:
  relation:
    type: choice
    instructions: Which relation between the marked pathway and the marked
                  disease does this abstract claim? ...
    criteria: {upregulation: ..., downregulation: ..., association: ...,
               no_association_stated: ..., none: ...}
    label: downregulation
```

Kev's `api.to_record` turns the state into plain text, with the field names
kept as labels (`abstract: ...`, `pathway: ...`, `disease: ...`). Each
criterion becomes one option string `"<name>: <description>"`. The label is
replaced by its index (here 1, `downregulation`).

### 2. Tokens: one row of 444 ids

`kev.model.encode` packs the record with five reserved Qwen tokens as
delimiters. They are existing vocabulary entries, so no new embedding rows are
added:

| Delimiter | Qwen token | id |
|---|---|---|
| `<state>` | `<\|fim_prefix\|>` | 248060 |
| `<q>` | `<\|fim_middle\|>` | 248061 |
| `<opt>` | `<\|box_start\|>` | 248049 |
| `</opt>` | `<\|box_end\|>` | 248050 |
| `<decide>` | `<\|fim_suffix\|>` | 248062 |

The row for this example:

| Segment | Tokens | Positions |
|---|---|---|
| `<state>` + state text | 1 + 223 = 224 | 0–223 |
| `<q>` + instruction | 1 + 27 = 28 | 224–251 |
| option 1 `upregulation: ...` | `<opt>` + 43 + `</opt>` = 45 | 252–296 |
| option 2 `downregulation: ...` | 46 | 297–342 |
| option 3 `association: ...` | 37 | 343–379 |
| option 4 `no_association_stated: ...` | 21 | 380–400 |
| option 5 `none: ...` | 42 | 401–442 |
| `<decide>` | 1 | 443 |
| **total** | **444** | |

Two limits apply. The state is capped at 2,200 tokens in our runs
(`--max_state 2200`). Over gt_100, states have a median of 392 tokens and a
maximum of 790, so none is cut. Text typed by the user can never produce a
delimiter token, because `<|...|>` in the input is rewritten before
tokenizing.

**Why one row per question.** Qwen3.5 is a hybrid model. Its recurrent
DeltaNet layers cannot apply the block mask that would let several questions
share one packed sequence. So every question runs as its own causal row: the
state followed by that question's branch. We ask exactly one question per
pair, so there is one row.

### 3. Embedding: `[444] → [444 × 2560]`

Each id selects one row of the embedding table `E` (248,320 × 2560, frozen).
The result `X` holds one 2560-number vector per token. At this point a vector
only says *which token* it is. Context is added by the layers.

### 4. Backbone: 32 layers, `[444 × 2560] → [444 × 2560]`

The layers alternate in a fixed 3 : 1 pattern: layers 3, 7, 11, …, 31 use full
attention, and the other 24 use Gated DeltaNet. Every layer has the same
structure:

```
x = x + Mixer(RMSNorm(x))        # mixes information across tokens
x = x + MLP(RMSNorm(x))          # transforms each token on its own
```

The shape stays `[444 × 2560]` throughout. What changes is the content: each
token's vector absorbs information from the tokens before it. That is how the
vector at `<decide>` comes to "know" the abstract, the question and all five
options.

**Gated DeltaNet mixer (24 layers).** Per token, with shapes from the
checkpoint:

| Projection | Shape | Meaning |
|---|---|---|
| `in_proj_qkv` | 2560 → 8192 | query 16 × 128, key 16 × 128, value 32 × 128 |
| `conv1d` | depthwise over those 8192 channels, kernel 4 | short local mixing over the last 4 tokens |
| `in_proj_z` | 2560 → 4096 | output gate (32 heads × 128) |
| `in_proj_a` | 2560 → 32 | per-head decay: how much memory to keep |
| `in_proj_b` | 2560 → 32 | per-head write strength β |
| `out_proj` | 4096 → 2560 | back to the hidden size |

Each of the 32 value heads keeps a running memory matrix `S` of 128 × 128
numbers. For every token, the memory is decayed, the old value stored under
the current key is partly erased, and the new value is written (the "delta
rule"). The token's output is its query read out of that memory. Cost grows
linearly with sequence length, which is what makes long abstracts cheap. Two
value heads share one key head (16 key heads, 32 value heads).

**Gated full attention (8 layers).**

| Projection | Shape | Meaning |
|---|---|---|
| `q_proj` | 2560 → 8192 | 16 query heads × 256, plus a same-size output gate |
| `k_proj`, `v_proj` | 2560 → 1024 each | 4 key/value heads × 256 (each shared by 4 query heads) |
| `o_proj` | 4096 → 2560 | back to the hidden size |

Every token attends to every earlier token exactly, at a cost quadratic in
length. These layers let precise long-range lookups through, for example from
`<decide>` back to the marked `[[DISEASE]]` span.

**MLP (every layer).** `gate_proj` and `up_proj` 2560 → 9216, a gated
activation, then `down_proj` 9216 → 2560.

**LoRA.** The base weights stay frozen. Fine-tuning adds a rank-16 update
`B·A` (`A`: r × in, `B`: out × r, scaled by α = 32) to every projection listed
above, in both mixer types and in the MLP. Together with the pointer head this
is 33.8M trainable parameters, against about 4B frozen ones.

### 5. Final norm: `H = [444 × 2560]`

After layer 31, one RMSNorm gives `last_hidden_state`. Kev loads the backbone
without its vocabulary head (`AutoModelForCausalLM(...).model`), because it
never predicts the next token.

### 6. Gather: 6 of the 444 vectors

Only six positions are read:

- `h_decide = H[443]`, `[2560]`. The `<decide>` token comes last, so it has
  seen everything: the abstract, the question and every option. Its vector is
  the model's summary of *what is being asked about this pair*.
- `H_opt = H[[296, 342, 379, 400, 442]]`, `[5 × 2560]`. Each `</opt>` closes
  one option. Its vector summarises *that option, read in the context of this
  abstract*. The `</opt>` of option 1 has not yet seen options 2–5, which is
  one reason option order matters and why training shuffles it.

The other 438 vectors are discarded.

### 7. Pointer head: `[2560] + [5 × 2560] → [5]`

`kev.model.PointerHead`, trained from Kev's release and then fine-tuned:

```
q = W_q · h_decide + b_q        W_q: 256 × 2560   q: [256]
K = W_k · H_opt   + b_k         W_k: 256 × 2560   K: [5 × 256]
z = K · q / sqrt(256)                              z: [5]
```

`q` is the question projected into a 256-dimensional matching space, and each
row of `K` is one option projected into the same space. The logit `z_i` is
their scaled dot product: how well option i answers the question. This is
attention with a single query, used as a pointer. Because the options are
scored by matching rather than by a fixed output layer, the same head works
for any number of options and any label names.

The probabilities recover the logits up to a common constant:
`z_i − z_max = ln p_i − ln p_max`. For this example, relative to
`downregulation`:

| Option | `z_i − z_down` |
|---|---|
| upregulation | −7.9 |
| downregulation | 0 |
| association | −5.3 |
| no_association_stated | −11.9 |
| none | −6.8 |

### 8. Softmax: `p = [5]`

```
upregulation           0.0004
downregulation         0.9935   <- argmax
association            0.0050
no_association_stated  0.00001
none                   0.0011
```

At inference, a checkpoint may carry a calibration temperature. The logits
are divided by it, which changes confidence but never the argmax.
`eval_kev.py` reports the argmax as `pred` and keeps all five probabilities.

### 9. Training (not part of inference)

The loss is cross-entropy between `z` and the gold index; the `score` question
type uses an ordinal objective instead, which we do not use. Gradients update
only the LoRA matrices and the pointer head. Each epoch, `kev.train` builds a
fresh variant of every record: the option order is permuted, and with small
probabilities a "none of these" option or a distractor is added
(`--p_none 0.1`, `--p_none_distract 0.12`, `--p_distract 0.15`). This keeps
the model from learning option *positions* instead of option *meanings*. The
learning rate follows one OneCycle schedule over the whole run (10 % warm-up,
then annealing), which is why a 3-epoch run cannot be cut into a 1-epoch
model.

Run settings of our sweep: `slurm/kev_altay.slurm` and
`relation_extraction/decision_models/train_kev.sh`.
