# Golden Set (v2) — variation-aware pathway annotations

Hand-curated. **v1** = the 5 abstracts richest in distinct Recon pathways (most-distinct-pathway PMIDs from `data/processed/exact_matches.jsonl`). **v2** = +5 abstracts chosen for pathway-*type* diversity (energy/central-carbon, carbohydrate, nucleotide, urea cycle, vitamin/cofactor, bile acid, drug/xenobiotic) to balance v1's amino-acid/lipid skew. Abstract text from `data/raw/articles.json`. Vocabulary: the 98 canonical Recon subsystems (`unique_pathways_from_recon.json`).

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

## PMID 34376485 — Plasma Metabolic Phenotypes of HPV-Associated versus Smoking-Associated Head and Neck Cancer and Patient Survival.

> BACKGROUND: Metabolic differences between human papillomavirus (HPV)-associated head and neck squamous cell carcinoma (HNSCC) and smoking-associated HNSCC may partially explain differences in prognosis. The former relies on mitochondrial oxidative phosphorylation (OXPHOS) while the latter relies on glycolysis. These differences have not been studied in blood. METHODS: We extracted metabolites using untargeted liquid chromatography high-resolution mass spectrometry from pretreatment plasma in a cohort of 55 HPV-associated and 82 smoking-associated HNSCC subjects. Metabolic pathway enrichment analysis of differentially expressed metabolites produced pathway-based signatures. Significant pathways (P < 0.05) were reduced via principal component analysis and assessed with overall survival via Cox models. We classified each subject as glycolytic or OXPHOS phenotype and assessed it with survival. RESULTS: Of 2,410 analyzed metabolites, 191 were differentially expressed. Relative to smoking-associated HNSCC, bile acid biosynthesis (P < 0.0001) and octadecatrienoic acid beta-oxidation (P = 0.01), were upregulated in HPV-associated HNSCC, while galactose metabolism (P = 0.001) and vitamin B6 metabolism (P = 0.01) were downregulated; the first two suggest an OXPHOS phenotype while the latter two suggest glycolytic. First principal components of bile acid biosynthesis [HR = 0.52 per SD; 95% confidence interval (CI), 0.38-0.72; P < 0.001] and octadecatrienoic acid beta-oxidation (HR = 0.54 per SD; 95% CI, 0.38-0.78; P < 0.001) were significantly associated with overall survival independent of HPV and smoking. The glycolytic versus OXPHOS phenotype was also independently associated with survival (HR = 3.17; 95% CI, 1.07-9.35; P = 0.04). CONCLUSIONS: Plasma metabolites related to glycolysis and mitochondrial OXPHOS may be biomarkers of HNSCC patient prognosis independent of HPV or smoking. Future investigations should determine whether they predict treatment efficacy. IMPACT: Blood metabolomics may be a useful marker to aid HNSCC patient prognosis.

**Counts:** 9 spans (3 exact, 4 synonym, **2 variation**), 0 shared-head enumerations, 0 out-of-vocab, 0 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `oxidative phosphorylation` | 238–263 | oxidative phosphorylation | exact | verbatim canonical; 'mitochondrial oxidative phosphorylation (OXPHOS)' |
| `OXPHOS` | 265–271 | oxidative phosphorylation | synonym | abbreviation; 'oxphos' is a current RECON_SYNONYM |
| `glycolysis` | 300–310 | glycolysis/gluconeogenesis | synonym | 'glycolysis' is a current RECON_SYNONYM of 'glycolysis/gluconeogenesis' |
| `bile acid biosynthesis` | 1016–1038 | bile acid synthesis | synonym | 'bile acid biosynthesis' is a current RECON_SYNONYM of 'bile acid synthesis' |
| `bile acid biosynthesis` | 1356–1378 | bile acid synthesis | synonym | 'First principal components of bile acid biosynthesis' |
| `octadecatrienoic acid beta-oxidation` | 1056–1092 | fatty acid oxidation | variation | specific fatty acid + 'beta-oxidation' -> Recon parent 'fatty acid oxidation' |
| `octadecatrienoic acid beta-oxidation` | 1454–1490 | fatty acid oxidation | variation | second occurrence in survival analysis |
| `galactose metabolism` | 1153–1173 | galactose metabolism | exact | verbatim canonical |
| `vitamin B6 metabolism` | 1190–1211 | vitamin b6 metabolism | exact | verbatim canonical (capitalized B) |

## PMID 42299101 — Posttranscriptional Regulation of Metabolism in Glioblastoma: A Multipathway Review.

> Glioblastoma (GBM) is the most aggressive and lethal form of primary brain tumor. A hallmark of GBM metabolism is the Warburg effect, whereby tumor cells preferentially utilize aerobic glycolysis despite oxygen availability, producing ATP inefficiently but supporting anabolic processes. Concurrently, the pentose phosphate pathway (PPP), amino acid metabolism, lipid biosynthesis, and nucleotide synthesis are rewired to meet the energetic and biosynthetic demands of GBM cells. Recent discoveries underscore the role of microRNAs (miRNAs) as master regulators orchestrating these metabolic rewiring events. Acting posttranscriptionally, miRNAs target key transporters, enzymes, and signaling molecules involved in glycolysis, glutaminolysis, lipid biosynthesis, and oxidative metabolism. This review explores how miRNA networks modulate metabolic plasticity in GBM. Specific miRNAs, such as miR-153, miR-451, miR-940, and miR-200b, suppress glutamine metabolism, regulate glucose transporters (e.g., GLUT1/3), inhibit lactate dehydrogenase, and disrupt mitochondrial folate metabolism. Others, such as miR-29 and miR-183, control lipid and nucleotide metabolism via the SREBP1 and IDH2 pathways. Furthermore, regulatory interactions among miRNAs, long non-coding RNAs (lncRNAs), and circular RNAs (circRNAs), such as the XIST/miR-126 or circ-CREBBP/miR-375 axes, create complex feedback loops that fine-tune metabolic pathways and enhance tumor survival under stress. We also discuss therapeutic strategies targeting these miRNA-metabolism circuits, including nanoparticle delivery, dietary restriction, and combination therapies that re-sensitize tumors to temozolomide and radiation. Understanding and therapeutically exploiting these networks presents a powerful approach to overcoming GBM's metabolic resilience, thereby opening new avenues for precision oncology.

**Counts:** 13 spans (1 exact, 3 synonym, **5 variation**), 1 shared-head enumerations, 0 out-of-vocab, 1 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `Warburg effect` | 118–132 | glycolysis/gluconeogenesis | synonym | 'warburg effect' is a current RECON_SYNONYM (aerobic glycolysis) |
| `aerobic glycolysis` | 177–195 | glycolysis/gluconeogenesis | variation | 'aerobic' subtype modifier on glycolysis; exact-match misses the phrase |
| `pentose phosphate pathway` | 306–331 | pentose phosphate pathway | exact | verbatim canonical |
| `PPP` | 333–336 | pentose phosphate pathway | synonym | abbreviation; 'ppp' is a current RECON_SYNONYM |
| `amino acid metabolism` | 339–360 | amino acid metabolism | umbrella | umbrella metabolic-process term; no single Recon subsystem |
| `lipid biosynthesis` | 362–380 | lipid metabolism | umbrella | generic lipid umbrella; no single Recon subsystem |
| `nucleotide synthesis` | 386–406 | nucleotide metabolism | variation | generic 'nucleotide synthesis' -> Recon parent 'nucleotide metabolism' |
| `glycolysis` | 716–726 | glycolysis/gluconeogenesis | synonym | standalone 'glycolysis' in 'involved in glycolysis, glutaminolysis' |
| `glutaminolysis` | 728–742 | glutamate metabolism | variation | glutamine catabolism to glutamate/a-KG; Recon folds into 'glutamate metabolism' |
| `lipid biosynthesis` | 744–762 | lipid metabolism | umbrella | second occurrence; generic lipid umbrella |
| `glutamine metabolism` | 943–963 | glutamate metabolism | variation | Recon has no 'glutamine metabolism'; folded into 'glutamate metabolism' |
| `oxidative metabolism` | 768–788 | oxidative metabolism | umbrella | vague energy-related umbrella; no single Recon subsystem |
| `mitochondrial folate metabolism` | 1055–1086 | folate metabolism | variation | compartment qualifier 'mitochondrial' on 'folate metabolism' |

### Shared-head enumerations

- **`lipid and nucleotide metabolism`** (1132–1163) — 'control lipid and nucleotide metabolism' — shared 'metabolism' head
    - → `lipid metabolism` (umbrella): generic lipid umbrella; no single Recon subsystem
    - → `nucleotide metabolism` (exact): verbatim canonical after shared-head split

### Metabolite negatives (must NOT be tagged)

- `ATP` (235–238) — energy metabolite, not a pathway

## PMID 28587170 — The Combination of Arginine Deprivation and 5-Fluorouracil Improves Therapeutic Efficacy in Argininosuccinate Synthetase Negative Hepatocellular Carcinoma.

> Argininosuccinate synthetase (ASS), a key enzyme to synthesize arginine is down regulated in many tumors including hepatocellular carcinoma (HCC). Similar to previous reports, we have found the decrease in ASS expression in poorly differentiated HCC. These ASS(-) tumors are auxotrophic for arginine. Pegylated arginine deiminase (ADI-PEG20), which degrades arginine, has shown activity in these tumors, but the antitumor effect is not robust and hence combination treatment is needed. Herein, we have elucidated the effectiveness of ADI-PEG20 combined with 5-Fluorouracil (5-FU) in ASS(-)HCC by targeting urea cycle and pyrimidine metabolism using four HCC cell lines as model. SNU398 and SNU387 express very low levels of ASS or ASS(-) while Huh-1, and HepG2 express high ASS similar to normal cells. Our results showed that the augmented cytotoxic effect of combination treatment only occurs in SNU398 and SNU387, and not in HepG2 and Huh-1 (ASS(+)) cells, and is partly due to reduced anti-apoptotic proteins X-linked inhibitor of apoptosis protein (XIAP), myeloid leukemia cell differentiation protein (Mcl-1) and B-cell lymphoma-2 (Bcl-2). Importantly, lack of ASS also influences essential enzymes in pyrimidine synthesis (carbamoyl-phosphate synthetase2, aspartate transcarbamylase and dihydrooratase (CAD) and thymidylate synthase (TS)) and malate dehydrogenase-1 (MDH-1) in TCA cycle. ADI-PEG20 treatment decreased these enzymes and made them more vulnerable to 5-FU. Transfection of ASS restored these enzymes and abolished the sensitivity to ADI-PEG20 and combination treatment. Overall, our data suggest that ASS influences multiple enzymes involved in 5-FU sensitivity. Combining ADI-PEG20 and 5-FU may be effective to treat ASS(-)hepatoma and warrants further clinical investigation.

**Counts:** 3 spans (2 exact, 1 synonym, **0 variation**), 1 shared-head enumerations, 0 out-of-vocab, 1 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `urea cycle` | 606–616 | urea cycle | exact | verbatim canonical; 'targeting urea cycle and pyrimidine metabolism' |
| `pyrimidine synthesis` | 1208–1228 | pyrimidine synthesis | exact | verbatim canonical; 'essential enzymes in pyrimidine synthesis' |
| `TCA cycle` | 1384–1393 | citric acid cycle | synonym | 'tca cycle' is a current RECON_SYNONYM of 'citric acid cycle' |

### Shared-head enumerations

- **`pyrimidine metabolism`** (621–642) — umbrella term spanning both Recon pyrimidine subsystems
    - → `pyrimidine synthesis` (variation): umbrella 'pyrimidine metabolism' -> Recon child
    - → `pyrimidine catabolism` (variation): umbrella 'pyrimidine metabolism' -> Recon child

### Metabolite negatives (must NOT be tagged)

- `arginine` (63–71) — amino acid metabolite (deprivation-therapy target), not a pathway

## PMID 38669820 — Primary goose kidney tubular epithelial cells for goose astrovirus genotype 2 infection: establishment and RNA sequencing analysis.

> Goose astrovirus genotype 2 (GAstV-2) mainly causes gout in goslings; therefore, it is a major pathogen threatening to goose flocks. However, the mechanisms underlying host-GAstV-2 interactions remain unclear because host cells suitable for GAstV-2 replication have been unavailable. We previously noted that GAstV-2 is primarily located in goose renal epithelial cells, where it causes kidney damage. Therefore, here, we derived goose primary renal tubular epithelial (RTE) cells (GRTE cells) from the kidneys of goose embryos after collagenase I digestion. After culture in Dulbecco's modified Eagle medium/Nutrient mixture F-12 with 10% fetal bovine serum (FBS), the isolated cells had polygonal with roadstone-like morphology; they were identified to be epithelial cells based on the presence of cytokeratin 18 expression detected through immunofluorescence assay (IFA). GAstV-2 infection in GRTE cells led to no obvious cytopathic effects; the maximum amounts of infectious virions were observed 48 h post infection through IFA and quantitative PCR. Next, RNA-seq was performed to identify and map post-GAstV-2 infection differentially expressed genes. The downregulated pathways were mainly related to metabolism, including tryptophan metabolism, drug metabolism by cytochrome P450, xenobiotic metabolism by cytochrome P450, retinol metabolism, butanoate metabolism, starch and sucrose metabolism, ascorbate and aldarate metabolism, and drug metabolism by other enzymes and peroxisome. In contrast, the upregulated pathways were mostly related to the host cell defense and proliferation, including extracellular matrix-receptor interaction, complement and coagulation cascades, phagosome, PI3K-Akt signaling pathway, human T-lymphotropic virus 1 infection, lysosome, and tumor necrosis factor signaling pathway. In conclusion, we developed a GRTE cell line for GAstV-2 replication and analyzed the potential host-GAstV-2 interactions through RNA-seq; our results may aid in further investigating the pathogenic mechanisms underlying GAstV-2 infection and provide strategies for its prevention and control.

**Counts:** 9 spans (5 exact, 0 synonym, **4 variation**), 0 shared-head enumerations, 2 out-of-vocab, 0 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `tryptophan metabolism` | 1230–1251 | tryptophan metabolism | exact | verbatim canonical |
| `drug metabolism` | 1253–1268 | drug metabolism | exact | verbatim canonical core of 'drug metabolism by cytochrome P450' |
| `cytochrome P450` | 1272–1287 | cytochrome metabolism | variation | 'cytochrome P450' -> Recon 'cytochrome metabolism' |
| `xenobiotic metabolism` | 1289–1310 | drug metabolism | variation | xenobiotic = foreign-compound metabolism; Recon 'drug metabolism' |
| `retinol metabolism` | 1331–1349 | vitamin a metabolism | variation | retinol = vitamin A; chemical-synonym of 'vitamin a metabolism' |
| `butanoate metabolism` | 1351–1371 | butanoate metabolism | exact | verbatim canonical |
| `starch and sucrose metabolism` | 1373–1402 | starch and sucrose metabolism | exact | verbatim canonical |
| `ascorbate and aldarate metabolism` | 1404–1437 | vitamin c metabolism | variation | ascorbate = vitamin C -> 'vitamin c metabolism'; 'aldarate' has no Recon subsystem |
| `drug metabolism` | 1443–1458 | drug metabolism | exact | 'drug metabolism by other enzymes' |

### Out-of-vocab pathway mentions (not scored in-scope)

- `PI3K-Akt signaling pathway` (1695–1721) — signaling pathway, not a metabolic process (contains 'pathway' — precision trap)
- `peroxisome` (1480–1490) — organelle, not a metabolic pathway

## PMID 37807318 — UHPLC-MS/MS-based central carbon metabolism unveils the biomarkers related to colon cancer.

> Even though colon cancer ranks among the leading causes of cancer mortality, early detection dramatically increases survival rates. Many studies have been conducted to determine whether altered metabolite levels may serve as a potential biomarker of cancer that affects key metabolic pathways. The goal of the study was to detect metabolic biomarkers in patients with colon cancer using liquid chromatography-mass spectrometry (LC-MS). This study consisted of 30 patients with colon cancer. An analysis of the metabolomes of cancer samples and para-carcinoma tissues was conducted. We identified a series of important metabolic changes in colon cancer by analyzing metabolites in cancerous tissues compared to their normal counterparts. They are mainly involved in the pentose phosphate pathway, the TCA cycle, glycolysis, galactose metabolism, and butanoate metabolism. As well, we observed dysregulation of AMP, dTMP, fructose, and D-glucose in colon cancer. Additionally, the AUCs for AMP, dTMP, fructose, and D-glucose were greater than 0.7 for the diagnosis of colon cancer. In conclusion, AMP, dTMP, fructose, and D-glucose showed excellent diagnostic performance and could serve as novel disease biomarkers for colon cancer diagnosis.

**Counts:** 5 spans (3 exact, 2 synonym, **0 variation**), 0 shared-head enumerations, 0 out-of-vocab, 4 metabolite negatives.

### Contiguous spans

| span text | offsets | canonical pathway | match_type | note |
|---|---|---|---|---|
| `pentose phosphate pathway` | 769–794 | pentose phosphate pathway | exact | verbatim canonical |
| `TCA cycle` | 800–809 | citric acid cycle | synonym | 'tca cycle' is a current RECON_SYNONYM of 'citric acid cycle' |
| `glycolysis` | 811–821 | glycolysis/gluconeogenesis | synonym | 'glycolysis' is a current RECON_SYNONYM of 'glycolysis/gluconeogenesis' |
| `galactose metabolism` | 823–843 | galactose metabolism | exact | verbatim canonical |
| `butanoate metabolism` | 849–869 | butanoate metabolism | exact | verbatim canonical |

### Metabolite negatives (must NOT be tagged)

- `AMP` (909–912) — nucleotide metabolite
- `dTMP` (914–918) — nucleotide metabolite
- `fructose` (920–928) — sugar metabolite (not 'fructose and mannose metabolism')
- `D-glucose` (934–943) — sugar metabolite
