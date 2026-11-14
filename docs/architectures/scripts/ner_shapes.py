"""Trace tensor shapes of the final pathway NER model on one gt_125 abstract.

Documentation source for docs/architectures. Paths are hard-coded to the author's machine and
the relation script imports from the sibling pathway-re-synth repository, so each records how the figures'
numbers were produced rather than serving as a reproducible entry point.
"""
import json, torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
M = "/home/enes/artifacts/checkpoints/ner_pathway-10k-missing/pathway-10k-missing/biom-electra-large/lr3e-05/seed42"
PMID = "32732914"
gt = [json.loads(l) for l in open("/home/enes/NER-pipeline/doccano/golden_dataset/gt_125/gt_125.jsonl")]
r = [x for x in gt if str(x.get("meta", {}).get("pmid", x.get("pmid", x.get("id")))) == PMID or PMID in json.dumps(x.get("meta", {}))]
print("found", len(r), list(gt[0].keys()), gt[0].get("meta"))
r = r[0]
text = r["text"]
labs = r.get("label") or r.get("labels") or r.get("entities")
gold = sorted((s, e) for s, e, *rest in ([(l[0], l[1], l[2]) for l in labs] if isinstance(labs[0], list) else [(l["start_offset"], l["end_offset"], l["label"]) for l in labs]) if "ath" in str(rest[0]))
tok = AutoTokenizer.from_pretrained(M)
model = AutoModelForTokenClassification.from_pretrained(M, attn_implementation="eager").eval()
enc = tok(text, max_length=512, truncation=True, return_offsets_mapping=True)
ids = torch.tensor([enc["input_ids"]])
with torch.no_grad():
    out = model(input_ids=ids, output_hidden_states=True, output_attentions=True)
logits = out.logits[0]
pred = logits.argmax(-1).tolist()
wids = enc.word_ids(); offs = enc["offset_mapping"]
first = [i for i, w in enumerate(wids) if w is not None and (i == 0 or wids[i - 1] != w)]
id2 = model.config.id2label
spans, cur = [], None
for i in first:
    t = id2[pred[i]]; s, e = offs[i]
    if t == "B-Pathway":
        if cur: spans.append(tuple(cur))
        cur = [s, e]
    elif t == "I-Pathway":
        cur = [s, e] if cur is None else [cur[0], e]
    else:
        if cur: spans.append(tuple(cur)); cur = None
if cur: spans.append(tuple(cur))
cls = [ (n, list(p.shape)) for n, p in model.named_parameters() if "classifier" in n]
emb = [ (n, list(p.shape)) for n, p in model.named_parameters() if "embeddings" in n and "weight" in n]
res = {
 "chars": len(text), "L": ids.shape[1], "n_words": len(first), "vocab": tok.vocab_size, "vocab_len": len(tok),
 "hidden_last": list(out.hidden_states[-1].shape), "n_hidden_states": len(out.hidden_states),
 "attention_one_layer": list(out.attentions[0].shape), "n_layers": len(out.attentions),
 "ffn": model.config.intermediate_size, "heads": model.config.num_attention_heads,
 "classifier": cls, "embeddings": emb, "logits": list(out.logits.shape),
 "pred_tag_counts": {id2[k]: sum(1 for i in first if pred[i] == k) for k in id2},
 "pred_spans": [(s, e, text[s:e]) for s, e in spans],
 "gold_spans": [(s, e, text[s:e]) for s, e in gold],
 "n_params": sum(p.numel() for p in model.parameters()),
}
print(json.dumps(res, indent=1, ensure_ascii=False))
