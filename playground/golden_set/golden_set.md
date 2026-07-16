# Golden Set — variation-aware pathway annotations

Hand-curated over the 5 abstracts richest in distinct Recon pathways (most-distinct-pathway PMIDs from `data/processed/exact_matches.jsonl`). Abstract text from `data/raw/articles.json`. Vocabulary: the 98 canonical Recon subsystems (`unique_pathways_from_recon.json`).

`match_type`: **exact**/**synonym** = exact matching already catches it; **variation** = a real in-vocab pathway mention exact matching MISSES (the whole point of this set).

## PMID 11469814 — Steroid metabolism in metabolic syndrome X.

> Preceding chapters in this volume describe relatively rare conditions associated with qualitative rather than quantitative changes in enzymes involved in steroid synthesis and metabolism. In this chapter, several examples show how more subtle variations in activities of the same enzymes may be important in the pathophysiology of common diseases of complex aetiology. This chapter reviews evidence for deranged steroid metabolism in patients with the 'insulin resistance syndrome'. In summary, patients with essential hypertension may have subtle 11beta-hydroxylase or 11beta-hydroxysteroid dehydrogenase type 2 deficiency resulting in mild mineralocorticoid excess. Patients with obesity, and/or associated hirsutism or hyperglycaemia, have evidence of altered peripheral metabolism of androgens (increased 5alpha-reductase) and glucocorticoids (altered 11beta-hydroxysteroid dehydrogenase type 1, resulting in enhanced cortisol levels in adipose tissue). Some of these changes in steroid metabolism lend themselves to therapeutic manipulation which may provide novel strategies to reduce cardiovascular risk.

**Counts:** 3 spans (2 exact, 0 synonym, **1 variation**), 1 shared-head enumerations, 0 out-of-vocab, 2 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `steroid metabolism` | 412–430 | steroid metabolism | exact | 'deranged steroid metabolism' |
| `steroid metabolism` | 983–1001 | steroid metabolism | exact | 'changes in steroid metabolism' |
| `metabolism of androgens` | 774–797 | androgen and estrogen synthesis and metabolism | variation | word-order reversal of 'androgen metabolism'; also plural |

### Shared-head enumerations

- **`steroid synthesis and metabolism`** (154–186) — 'enzymes involved in steroid synthesis and metabolism' — umbrella phrase
    - → `steroid metabolism` (variation): synthesis+metabolism factored; core is steroid metabolism

### Metabolite negatives (must NOT be tagged)

- `cortisol` (922–930) — hormone, not a pathway
- `glucocorticoids` (831–846) — hormone class

## PMID 39934780 — Distinct metabolic perturbations link liver steatosis and incident CVD in lean but not obese PWH.

> BACKGROUND: Metabolic dysfunction-associated steatotic liver disease (MASLD) is a key risk factor for cardiovascular disease (CVD), potentially driven by shared metabolic mechanisms. Metabolic perturbations associated with MASLD and CVD remain underexplored in people with HIV (PWH). METHODS: We used data from the longitudinal multicenter 2000HIV study comprising 1895 virally suppressed PWH, out of which 970 had available liver and carotid artery measurements. Transient elastography with controlled attenuation parameter (CAP) was performed for the assessment of liver steatosis (CAP > 263 dB/m) and fibrosis (LSM ≥ 7.0). Historic and future incident CVD within 2-year follow-up, defined as myocardial infarction, stroke, peripheral arterial disease, and angina pectoris, were extracted from the medical files, while atherosclerotic plaque(s) in the carotid arteries were assessed using ultrasonography. Metabolic perturbations were analyzed using mass spectrometry-based untargeted metabolomics (n = 500 metabolites) and nuclear magnetic resonance spectroscopy for targeted lipids and other metabolites (n = 246 metabolites). RESULTS: PWH with liver steatosis were more likely to have arterial plaques (47% vs. 36%; P value = 0.003) and CVD history (11% vs. 6.8%; P value = 0.021) than PWH without liver steatosis. These associations were only significant in lean PWH, in contrast to those with BMI ≥ 25 kg/m2. Metabolic pathways associated with liver steatosis and fibrosis primarily involved lipid and amino acid metabolism, and they were validated by targeted lipoproteomic measurements. Interestingly, metabolomic pathways and lipoproteomic signatures associated with MASLD were mostly distinct from those associated with CVD parameters. However, several metabolic pathways were shared, especially in lean PWH. These include arachidonic acid metabolism and formation of prostaglandin, purine metabolism, cholecalciferol metabolism, and glycine, serine, alanine, and threonine metabolism. CONCLUSION: Metabolic disturbances linked to liver steatosis and CVD diverge across BMI categories in PWH. Lean PWH, unlike their overweight/obese counterparts, show common metabolic perturbations between MASLD and CVD, particularly involving arachidonic acid metabolism. This suggests that lean PWH with liver steatosis may face a heightened risk of CVD due to shared metabolic pathways, potentially opening avenues for targeted interventions, such as aspirin therapy, to mitigate this risk.

**Counts:** 5 spans (3 exact, 0 synonym, **2 variation**), 2 shared-head enumerations, 0 out-of-vocab, 0 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `arachidonic acid metabolism` | 1834–1861 | arachidonic acid metabolism | exact | 'These include arachidonic acid metabolism' |
| `arachidonic acid metabolism` | 2240–2267 | arachidonic acid metabolism | exact | 'particularly involving arachidonic acid metabolism' |
| `cholecalciferol metabolism` | 1913–1939 | vitamin d metabolism | variation | cholecalciferol = vitamin D3; chemical-synonym of 'vitamin d metabolism' |
| `glycine, serine, alanine, and threonine metabolism` | 1945–1995 | glycine, serine, alanine, and threonine metabolism | exact | verbatim canonical Recon name |
| `formation of prostaglandin` | 1866–1892 | eicosanoid metabolism | variation | prostaglandins are eicosanoids; specific product-formation -> Recon 'eicosanoid metabolism' |

### Shared-head enumerations

- **`lipid and amino acid metabolism`** (1499–1530) — shared-head umbrella; both halves included as non-Recon metabolic processes
    - → `lipid metabolism` (umbrella): umbrella category; no single Recon subsystem
    - → `amino acid metabolism` (umbrella): umbrella category; no single Recon subsystem
- **`purine metabolism`** (1894–1911) — umbrella term spanning both Recon purine subsystems
    - → `purine synthesis` (variation): umbrella 'purine metabolism' -> Recon child
    - → `purine catabolism` (variation): umbrella 'purine metabolism' -> Recon child

## PMID 40225847 — Discovery of biological markers for schizophrenia based on metabolomics: a systematic review.

> INTRODUCTION AND METHODS: To discover biomarkers for schizophrenia (SCZ) at the metabolomics level, we registered this systematic review (CRD42024572133 (https://www.crd.york.ac.uk/PROSPERO/home)) including 56 qualified articles, and we identified the characteristics of metabolites, metabolite combinations, and metabolic pathways associated with SCZ. RESULTS: Our findings showed that decreased arachidonic acid, arginine, and aspartate levels, and the increased levels of glucose 6-phosphate and glycylglycine were associated with the onset of SCZ. Metabolites such as carnitine and methionine sulfoxide not only helped to identify SCZ in Miao patients, but also were different between Miao patients and Han patients. The decrease in benzoic acid and betaine and the increase in creatine were the notable metabolic characteristics of first-episode schizophrenia (FESCZ). The metabolite combination formed by metabolites such as methylamine, dimethylamine and other metabolites had the best diagnostic effect. Arginine and proline metabolism and arginine biosynthesis had a clear advantage in identifying SCZ and acute SCZ. Butanoate metabolism played an important role in identifying SCZ, toxoplasma infection and SCZ comorbidity. Biosynthesis of unsaturated fatty acids was also significantly enriched in the diagnosis and treatment of SCZ. DISCUSSION: This study summarizes the current progress in clinical metabolomic research related to SCZ, deepens understanding of the pathogenesis of SCZ, and lays a foundation for subsequent research on SCZ-related metabolites. SYSTEMATIC REVIEW REGISTRATION: https://www.crd.york.ac.uk/PROSPERO/home, identifier CRD42024572133.

**Counts:** 3 spans (2 exact, 0 synonym, **1 variation**), 0 shared-head enumerations, 1 out-of-vocab, 5 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `Arginine and proline metabolism` | 1012–1043 | arginine and proline metabolism | exact | verbatim canonical (capitalized) |
| `Butanoate metabolism` | 1126–1146 | butanoate metabolism | exact | verbatim canonical (capitalized) |
| `arginine biosynthesis` | 1048–1069 | arginine and proline metabolism | variation | KEGG 'arginine biosynthesis'; Recon folds it into 'arginine and proline metabolism' |

### Out-of-vocab pathway mentions (not scored in-scope)

- `Biosynthesis of unsaturated fatty acids` (1234–1273) — excluded: subtype 'unsaturated' absent from Recon's generic 'fatty acid synthesis'

### Metabolite negatives (must NOT be tagged)

- `arachidonic acid` (397–413) — metabolite (not 'arachidonic acid metabolism')
- `arginine` (415–423) — amino acid metabolite
- `glucose 6-phosphate` (475–494) — metabolite
- `carnitine` (572–581) — metabolite
- `creatine` (782–790) — metabolite

## PMID 29615816 — Distinct Metabolic features differentiating FLT3-ITD AML from FLT3-WT childhood Acute Myeloid Leukemia.

> Acute myeloid leukemia (AML) is a heterogeneous disease with dismal response warranting the need for enhancing our understanding of AML biology. One prognostic feature associated with inferior response is the presence of activating mutations in FMS-like tyrosine kinase 3 (FLT3) especially occurrence of internal tandem duplication (FLT3-ITD). Although poorly understood, differential metabolic and signaling pathways associated with FLT3-ITD might contribute towards the observed poor prognosis. We performed a non-targeted global metabolic profiling of matched cell and plasma samples obtained at diagnosis to establish metabolic differences within FLT3-ITD and FLT3-WT pediatric AML. Metabolomic profiling by Ultra-High Performance-Liquid-Chromatography-Mass Spectrometry identified differential abundance of 21 known metabolites in plasma and 33 known metabolites in leukemic cells by FLT3 status. These metabolic features mapped to pathways of significant biological importance. Of interest were metabolites with roles in cancer, cell progression and involvement in purine metabolism and biosynthesis, cysteine/methionine metabolism, tryptophan metabolism, carnitine mediated fatty acid oxidation, and lysophospholipid metabolism. Although validation in a larger cohort is required, our results for the first time investigated global metabolic profile in FLT3-ITD AML.

**Counts:** 4 spans (2 exact, 0 synonym, **2 variation**), 1 shared-head enumerations, 0 out-of-vocab, 1 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `tryptophan metabolism` | 1139–1160 | tryptophan metabolism | exact | verbatim canonical |
| `fatty acid oxidation` | 1181–1201 | fatty acid oxidation | exact | core term inside 'carnitine mediated fatty acid oxidation' |
| `cysteine/methionine metabolism` | 1107–1137 | methionine and cysteine metabolism | variation | order swapped + '/' separator vs canonical 'methionine and cysteine metabolism' |
| `lysophospholipid metabolism` | 1207–1234 | glycerophospholipid metabolism | variation | specific lipid subtype -> Recon parent 'glycerophospholipid metabolism' |

### Shared-head enumerations

- **`purine metabolism and biosynthesis`** (1071–1105) — 'involvement in purine metabolism and biosynthesis'
    - → `purine synthesis` (variation): 'purine metabolism' umbrella + 'purine biosynthesis' both cover purine synthesis
    - → `purine catabolism` (variation): 'purine metabolism' umbrella also covers purine catabolism

### Metabolite negatives (must NOT be tagged)

- `carnitine` (1162–1171) — metabolite (modifier in 'carnitine mediated fatty acid oxidation')

## PMID 36294866 — Metabolomic Signatures of Autism Spectrum Disorder.

> Autism Spectrum Disorder (ASD) is associated with many variations in metabolism, but the ex-act correlates of these metabolic disturbances with behavior and development and their links to other core metabolic disruptions are understudied. In this study, large-scale targeted LC-MS/MS metabolomic analysis was conducted on fasting morning plasma samples from 57 children with ASD (29 with neurodevelopmental regression, NDR) and 37 healthy controls of similar age and gender. Linear model determined the metabolic signatures of ASD with and without NDR, measures of behavior and neurodevelopment, as well as markers of oxidative stress, inflammation, redox, methylation, and mitochondrial metabolism. MetaboAnalyst ver 5.0 (the Wishart Research Group at the University of Alberta, Edmonton, Canada) identified the pathways associated with altered metabolic signatures. Differences in histidine and glutathione metabolism as well as aromatic amino acid (AAA) biosynthesis differentiated ASD from controls. NDR was associated with disruption in nicotinamide and energy metabolism. Sleep and neurodevelopment were associated with energy metabolism while neurodevelopment was also associated with purine metabolism and aminoacyl-tRNA biosynthesis. While behavior was as-sociated with some of the same pathways as neurodevelopment, it was also associated with alternations in neurotransmitter metabolism. Alterations in methylation was associated with aminoacyl-tRNA biosynthesis and branched chain amino acid (BCAA) and nicotinamide metabolism. Alterations in glutathione metabolism was associated with changes in glycine, serine and threonine, BCAA and AAA metabolism. Markers of oxidative stress and inflammation were as-sociated with energy metabolism and aminoacyl-tRNA biosynthesis. Alterations in mitochondrial metabolism was associated with alterations in energy metabolism and L-glutamine. Using behavioral and biochemical markers, this study finds convergent disturbances in specific metabolic pathways with ASD, particularly changes in energy, nicotinamide, neurotransmitters, and BCAA, as well as aminoacyl-tRNA biosynthesis.

**Counts:** 4 spans (2 exact, 1 synonym, **0 variation**), 6 shared-head enumerations, 2 out-of-vocab, 1 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `glutathione metabolism` | 897–919 | glutathione metabolism | exact | contiguous tail of 'histidine and glutathione metabolism' |
| `glutathione metabolism` | 1555–1577 | glutathione metabolism | exact | 'Alterations in glutathione metabolism' |
| `nicotinamide metabolism` | 1515–1538 | nad metabolism | synonym | 'BCAA and nicotinamide metabolism' — 'nicotinamide metabolism' is a current RECON_SYNONYM |
| `neurotransmitter metabolism` | 1370–1397 | neurotransmitter metabolism | umbrella | umbrella metabolic-process term; no single Recon subsystem |

### Shared-head enumerations

- **`histidine and glutathione metabolism`** (883–919) — 'Differences in histidine and glutathione metabolism'
    - → `histidine metabolism` (variation): head 'histidine' factored from shared 'metabolism' — exact-match misses
    - → `glutathione metabolism` (exact): contiguous; already a span
- **`nicotinamide and energy metabolism`** (1042–1076) — 'NDR was associated with disruption in nicotinamide and energy metabolism'
    - → `nad metabolism` (variation): 'nicotinamide' split from 'metabolism' by 'and energy' — synonym form broken by shared head
    - → `energy metabolism` (umbrella): umbrella metabolic-process term; no single Recon subsystem
- **`branched chain amino acid (BCAA) and nicotinamide metabolism`** (1478–1538) — 'BCAA and nicotinamide metabolism'
    - → `valine, leucine, and isoleucine metabolism` (variation): BCAA = valine/leucine/isoleucine; 'BCAA metabolism' shared-head + abbreviation
    - → `nad metabolism` (synonym): 'nicotinamide metabolism' contiguous; already a span
- **`glycine, serine and threonine, BCAA and AAA metabolism`** (1609–1663) — 'changes in glycine, serine and threonine, BCAA and AAA metabolism'
    - → `glycine, serine, alanine, and threonine metabolism` (variation): subset (no alanine) + shared 'metabolism' factored across the list
    - → `valine, leucine, and isoleucine metabolism` (variation): 'BCAA metabolism' via shared head
    - → `phenylalanine metabolism` (variation): 'AAA metabolism' -> Recon child (aromatic aa)
    - → `tyrosine metabolism` (variation): 'AAA metabolism' -> Recon child (aromatic aa)
    - → `tryptophan metabolism` (variation): 'AAA metabolism' -> Recon child (aromatic aa)
- **`aromatic amino acid (AAA) biosynthesis`** (931–969) — umbrella 'aromatic amino acid biosynthesis' -> three Recon aromatic-aa subsystems
    - → `phenylalanine metabolism` (variation): AAA -> Recon child
    - → `tyrosine metabolism` (variation): AAA -> Recon child
    - → `tryptophan metabolism` (variation): AAA -> Recon child
- **`purine metabolism`** (1192–1209) — umbrella term spanning both Recon purine subsystems
    - → `purine synthesis` (variation): umbrella -> Recon child
    - → `purine catabolism` (variation): umbrella -> Recon child

### Out-of-vocab pathway mentions (not scored in-scope)

- `aminoacyl-tRNA biosynthesis` (1214–1241) — translation pathway; not a Recon metabolic subsystem
- `mitochondrial metabolism` (674–698) — compartment term, not a metabolic process

### Metabolite negatives (must NOT be tagged)

- `L-glutamine` (1880–1891) — amino acid metabolite (not 'glutamate metabolism')
