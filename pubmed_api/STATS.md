# Pipeline Statistics

Auto-updated by `compute_stats.py` after each run. Edit header sections manually if needed.

---

## Disease Corpus

| Source | Tree | Descriptors |
|---|---|---|
| Metabolic / Nutritional | C18 | 334 |
| Neoplasms (Cancer) | C04 | 455 |
| Neurodegenerative | C10.574 | 77 |
| **Total unique (combined)** | — | **834** |

### Selected diseases (`selected_diseases.json`)

| Category | Count |
|---|---|
| Cancer | 37 |
| Metabolic | 33 |
| Neurodegenerative | 28 |
| **Total** | **98** |

<details>
<summary>Cancer (37)</summary>

Adenocarcinoma, Brain Neoplasms, Breast Neoplasms, Carcinoma, Carcinoma, Hepatocellular, Carcinoma, Pancreatic Ductal, Carcinoma, Renal Cell, Carcinoma, Squamous Cell, Cholangiocarcinoma, Colorectal Neoplasms, Hereditary Nonpolyposis, Endometrial Neoplasms, Esophageal Neoplasms, Glioblastoma, Glioma, Head and Neck Neoplasms, Hodgkin Disease, Kidney Neoplasms, Leukemia, Leukemia, Lymphocytic, Chronic, B-Cell, Leukemia, Myeloid, Acute, Liver Neoplasms, Lung Neoplasms, Lymphoma, Lymphoma, Non-Hodgkin, Melanoma, Mesothelioma, Multiple Myeloma, Neoplasms, Hormone-Dependent, Neuroblastoma, Ovarian Neoplasms, Pancreatic Neoplasms, Prostatic Neoplasms, Sarcoma, Stomach Neoplasms, Thyroid Neoplasms, Urinary Bladder Neoplasms, Uterine Cervical Neoplasms

</details>

<details>
<summary>Neurodegenerative (28)</summary>

Alzheimer Disease, Amyotrophic Lateral Sclerosis, Attention Deficit Disorder with Hyperactivity, Autism Spectrum Disorder, Bipolar Disorder, Brain Diseases, Brain Ischemia, Charcot-Marie-Tooth Disease, Dementia, Vascular, Epilepsy, Friedreich Ataxia, Frontotemporal Dementia, Huntington Disease, Lewy Body Disease, Major Depressive Disorder, Multiple Sclerosis, Multiple System Atrophy, Muscular Dystrophies, Muscular Dystrophy, Duchenne, Neurodegenerative Diseases, Parkinson Disease, Prion Diseases, Schizophrenia, Spastic Paraplegia, Hereditary, Spinal Muscular Atrophies of Childhood, Spinocerebellar Ataxias, Stroke, Supranuclear Palsy, Progressive

</details>

<details>
<summary>Metabolic (33)</summary>

Anemia, Iron-Deficiency, Anemia, Sickle Cell, Atherosclerosis, Coronary Artery Disease, Cystic Fibrosis, Diabetes Mellitus, Type 1, Diabetes Mellitus, Type 2, Fabry Disease, Fatty Liver, Galactosemias, Gaucher Disease, Glycogen Storage Disease, Gout, Hemochromatosis, Hepatolenticular Degeneration, Homocystinuria, Hypercholesterolemia, Hyperlipidemias, Hypertension, Hypertriglyceridemia, Hyperuricemia, Insulin Resistance, Liver Cirrhosis, Maple Syrup Urine Disease, Metabolic Syndrome, Mucopolysaccharidoses, Niemann-Pick Diseases, Non-alcoholic Fatty Liver Disease, Obesity, Phenylketonurias, Porphyrias, Scurvy, Vitamin D Deficiency

</details>


---

## Pathways

| Source | Count |
|---|---|
| Recon3D unique pathways | 98 |

---

## Pair Search (`fetch_pathway_disease_pairs.py`)

| Metric | Value |
|---|---|
| Total pair hits (≥1 PMID) | 1959 |
| Unique PMIDs collected | 10329 |
| Max PMIDs per pair (cap) | 20 |

### Hits by disease category

| Category | Pair hits | Unique PMIDs |
|---|---|---|
| Cancer | 601 pairs | 3531 PMIDs |
| Neurodegenerative | 573 pairs | 2667 PMIDs |
| Metabolic | 785 pairs | 4399 PMIDs |


---

## Article Fetch (`fetch_articles.py`)

| Metric | Value |
|---|---|
| Total articles fetched | 10329 |
| Has full text (PMC) | 5837 |
| Abstract only | 4492 |
| Has abstract | 10044 |
| Has MeSH headings | 7506 |
| Has DOI | 9507 |
| Full text rate | 56.5% |

### Top publication types

| Type | Count |
|---|---|
| Journal Article | 9862 |
| Research Support, Non-U.S. Gov't | 2679 |
| Review | 1832 |
| Research Support, N.I.H., Extramural | 718 |
| Case Reports | 259 |


---

## Last updated

<!-- updated by compute_stats.py -->
2026-07-06
