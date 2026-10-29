# High Disease-Span Abstract Sample

This report contains five randomly selected abstracts from the 567 documents with at least 20 `DISEASE` spans in the canonical combined corpus.

- Source: `data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl`
- Selection threshold: at least 20 detected disease spans
- Selection method: random sample of five PMIDs
- Character intervals are zero-based, half-open: `[start, end)`.
- Disease spans are bold in each abstract.
- The matched text and surrounding context are reproduced exactly from the stored abstract. These are model-derived disease annotations, so the report intentionally retains questionable spans for audit.

## PMID 3855682

- Disease spans: 21
- Pathway spans: 0
- Abstract length: 1594 characters

### Abstract

> The reported relationship of radiation exposure and **thyroid carcinoma** stimulated this retrospective study of 298 patients treated at St. Jude Children's Hospital with radiation therapy to the neck for childhood **cancer** to identify patients who developed subsequent **thyroid abnormalities**. This series includes 153 patients with **Hodgkin's disease**, 95 with **acute lymphocytic leukemia**, 28 with **lymphoepithelioma**, and 22 with **miscellaneous tumors**. Inclusion in the study required 5 years of disease-free survival following therapy for their original **tumor**, which included thyroid irradiation. Follow-up has been 100%. Most patients also received chemotherapy. Seventeen patients were found to have decreased thyroid reserve with normal levels of free triiodothyroxine (T3) or free thyroxin, (T4) and an elevated level of thyroid-stimulating hormone (TSH). In nine patients **hypothyroidism** developed, with decreased T3 or T4 levels and an elevated level of TSH. One **hyperthyroid** patient was identified. Two patients had **thyroiditis**, and seven had **thyroid neoplasms**: (**carcinoma** in two, **adenoma** in two, **colloid nodule** in one, and undiagnosed nodules in two). This survey has demonstrated an increased incidence of **thyroid dysfunction** and **thyroid neoplasia** when compared to the general population. The importance of long-term follow-up for **thyroid disease** is emphasized in patients who have received thyroid irradiation. The possible role of subclinical **hypothyroidism** with TSH elevation coupled with radiation damage to the thyroid **gland** as a model for the development of **neoplastic disease** is discussed.

### Detected disease spans

| Character range (start-end) | Matched text | Local context |
|---|---|---|
| 52-69 | `thyroid carcinoma` | The reported relationship of radiation exposure and thyroid carcinoma stimulated this retrospective study of 298 patients treated at St. Ju |
| 211-217 | `cancer` |  Children's Hospital with radiation therapy to the neck for childhood cancer to identify patients who developed subsequent thyroid abnormalities.  |
| 264-285 | `thyroid abnormalities` | ck for childhood cancer to identify patients who developed subsequent thyroid abnormalities. This series includes 153 patients with Hodgkin's disease, 95 with ac |
| 326-343 | `Hodgkin's disease` | sequent thyroid abnormalities. This series includes 153 patients with Hodgkin's disease, 95 with acute lymphocytic leukemia, 28 with lymphoepithelioma, and 2 |
| 353-379 | `acute lymphocytic leukemia` | es. This series includes 153 patients with Hodgkin's disease, 95 with acute lymphocytic leukemia, 28 with lymphoepithelioma, and 22 with miscellaneous tumors. Inclusi |
| 389-406 | `lymphoepithelioma` | s with Hodgkin's disease, 95 with acute lymphocytic leukemia, 28 with lymphoepithelioma, and 22 with miscellaneous tumors. Inclusion in the study required 5  |
| 420-440 | `miscellaneous tumors` | th acute lymphocytic leukemia, 28 with lymphoepithelioma, and 22 with miscellaneous tumors. Inclusion in the study required 5 years of disease-free survival fol |
| 544-549 | `tumor` | 5 years of disease-free survival following therapy for their original tumor, which included thyroid irradiation. Follow-up has been 100%. Most pa |
| 867-881 | `hypothyroidism` | elevated level of thyroid-stimulating hormone (TSH). In nine patients hypothyroidism developed, with decreased T3 or T4 levels and an elevated level of TS |
| 958-970 | `hyperthyroid` | ped, with decreased T3 or T4 levels and an elevated level of TSH. One hyperthyroid patient was identified. Two patients had thyroiditis, and seven had t |
| 1012-1023 | `thyroiditis` | vel of TSH. One hyperthyroid patient was identified. Two patients had thyroiditis, and seven had thyroid neoplasms: (carcinoma in two, adenoma in two,  |
| 1039-1056 | `thyroid neoplasms` | d patient was identified. Two patients had thyroiditis, and seven had thyroid neoplasms: (carcinoma in two, adenoma in two, colloid nodule in one, and undiag |
| 1059-1068 | `carcinoma` | fied. Two patients had thyroiditis, and seven had thyroid neoplasms: (carcinoma in two, adenoma in two, colloid nodule in one, and undiagnosed nodule |
| 1077-1084 | `adenoma` |  had thyroiditis, and seven had thyroid neoplasms: (carcinoma in two, adenoma in two, colloid nodule in one, and undiagnosed nodules in two). This  |
| 1093-1107 | `colloid nodule` | , and seven had thyroid neoplasms: (carcinoma in two, adenoma in two, colloid nodule in one, and undiagnosed nodules in two). This survey has demonstrated |
| 1204-1223 | `thyroid dysfunction` | dules in two). This survey has demonstrated an increased incidence of thyroid dysfunction and thyroid neoplasia when compared to the general population. The im |
| 1228-1245 | `thyroid neoplasia` | ey has demonstrated an increased incidence of thyroid dysfunction and thyroid neoplasia when compared to the general population. The importance of long-term  |
| 1329-1344 | `thyroid disease` |  to the general population. The importance of long-term follow-up for thyroid disease is emphasized in patients who have received thyroid irradiation. The  |
| 1443-1457 | `hypothyroidism` | o have received thyroid irradiation. The possible role of subclinical hypothyroidism with TSH elevation coupled with radiation damage to the thyroid gland |
| 1522-1527 | `gland` | idism with TSH elevation coupled with radiation damage to the thyroid gland as a model for the development of neoplastic disease is discussed. |
| 1562-1580 | `neoplastic disease` | diation damage to the thyroid gland as a model for the development of neoplastic disease is discussed. |

## PMID 37435496

- Disease spans: 25
- Pathway spans: 2
- Abstract length: 2258 characters

### Abstract

> Introduction: **Temporal lobe epilepsy** (**TLE**) is the most common subtype of **epilepsy** in adults and is characterized by neuronal loss, **gliosis**, and sprouting mossy fibers in the hippocampus. But the mechanism underlying neuronal loss has not been fully elucidated. A new programmed cell death, cup**rop**to**sis**, has recently been discovered; however, its role in **TLE** is not clear. Methods: We first investigated the copper ion concentration in the hippocampus tissue. Then, using the Sample dataset and E-MTAB-3123 dataset, we analyzed the features of 12 **cuproptosis**-related genes in **TLEs** and controls using the bioinformatics tools. Then, the expression of the key cup**roptosis** genes were confirmed using real-time PCR and immunohistochemical staining (IHC). Finally, the Enrichr database was used to screen the small molecules and drugs targeting key cuprop**to**sis genes in **TLE**. Results: The Sample dataset displayed four differentially expressed **cuproptosis**-related genes (DECRGs; LIPT1, GLS, PDHA1, and CDKN2A) while the E-MTAB-3123 dataset revealed seven DECRGs (LIPT1, DLD, FDX1, GLS, PDHB, PDHA1, and DLAT). Remarkably, only LIPT1 was uniformly upregulated in both datasets. Additionally, these DECRGs are implicated in the TCA cycle and pyruvate metabolism-both crucial for cell cuproptosis-as well as various immune cell infiltrations, especially macrophages and T cells, in the **TLE** hippocampus. Interestingly, DECRGs were linked to most infiltrating immune cells during **TLE**'s acute phase, but this association considerably weakened in the latent phase. In the chronic phase, DECRGs were connected with several T-cell subclasses. Moreover, LIPT1, FDX1, DLD, and PDHB were related to **TLE** identification. PCR and IHC further confirmed LIPT1 and FDX1's upregulation in **TLE** compared to controls. Finally, using the Enrichr database, we found that chlorzoxazone and piperlongumine inhibited cell cuproptosis by targeting LIPT1, FDX1, DLD, and PDHB. Conclusion: Our findings suggest that **cuproptosis** is directly related to **TLE**. The signature of **cuproptosis**-related genes presents new clues for exploring the roles of neuronal death in **TLE**. Furthermore, LIPT1 and FDX1 appear as potential targets of **neuronal cuprop**to**sis** for controlling **TLE**'s **seizures** and progression.

### Detected disease spans

| Character range (start-end) | Matched text | Local context |
|---|---|---|
| 14-36 | `Temporal lobe epilepsy` | Introduction: Temporal lobe epilepsy (TLE) is the most common subtype of epilepsy in adults and is charact |
| 38-41 | `TLE` | Introduction: Temporal lobe epilepsy (TLE) is the most common subtype of epilepsy in adults and is characterize |
| 73-81 | `epilepsy` | roduction: Temporal lobe epilepsy (TLE) is the most common subtype of epilepsy in adults and is characterized by neuronal loss, gliosis, and sprouti |
| 131-138 | `gliosis` |  subtype of epilepsy in adults and is characterized by neuronal loss, gliosis, and sprouting mossy fibers in the hippocampus. But the mechanism und |
| 293-296 | `rop` | l loss has not been fully elucidated. A new programmed cell death, cuproptosis, has recently been discovered; however, its role in TLE is not c |
| 298-301 | `sis` | s has not been fully elucidated. A new programmed cell death, cuproptosis, has recently been discovered; however, its role in TLE is not clear. |
| 354-357 | `TLE` | eath, cuproptosis, has recently been discovered; however, its role in TLE is not clear. Methods: We first investigated the copper ion concentra |
| 546-557 | `cuproptosis` | ample dataset and E-MTAB-3123 dataset, we analyzed the features of 12 cuproptosis-related genes in TLEs and controls using the bioinformatics tools. Th |
| 575-579 | `TLEs` |  dataset, we analyzed the features of 12 cuproptosis-related genes in TLEs and controls using the bioinformatics tools. Then, the expression of  |
| 660-668 | `roptosis` | ls using the bioinformatics tools. Then, the expression of the key cuproptosis genes were confirmed using real-time PCR and immunohistochemical stai |
| 849-851 | `to` |  was used to screen the small molecules and drugs targeting key cuproptosis genes in TLE. Results: The Sample dataset displayed four different |
| 864-867 | `TLE` | reen the small molecules and drugs targeting key cuproptosis genes in TLE. Results: The Sample dataset displayed four differentially expressed  |
| 937-948 | `cuproptosis` | . Results: The Sample dataset displayed four differentially expressed cuproptosis-related genes (DECRGs; LIPT1, GLS, PDHA1, and CDKN2A) while the E-MTA |
| 1376-1379 | `TLE` | immune cell infiltrations, especially macrophages and T cells, in the TLE hippocampus. Interestingly, DECRGs were linked to most infiltrating i |
| 1468-1471 | `TLE` | estingly, DECRGs were linked to most infiltrating immune cells during TLE's acute phase, but this association considerably weakened in the late |
| 1680-1683 | `TLE` | cell subclasses. Moreover, LIPT1, FDX1, DLD, and PDHB were related to TLE identification. PCR and IHC further confirmed LIPT1 and FDX1's upregu |
| 1763-1766 | `TLE` | ation. PCR and IHC further confirmed LIPT1 and FDX1's upregulation in TLE compared to controls. Finally, using the Enrichr database, we found t |
| 1979-1990 | `cuproptosis` | ing LIPT1, FDX1, DLD, and PDHB. Conclusion: Our findings suggest that cuproptosis is directly related to TLE. The signature of cuproptosis-related gene |
| 2014-2017 | `TLE` | clusion: Our findings suggest that cuproptosis is directly related to TLE. The signature of cuproptosis-related genes presents new clues for ex |
| 2036-2047 | `cuproptosis` | suggest that cuproptosis is directly related to TLE. The signature of cuproptosis-related genes presents new clues for exploring the roles of neuronal  |
| 2126-2129 | `TLE` | genes presents new clues for exploring the roles of neuronal death in TLE. Furthermore, LIPT1 and FDX1 appear as potential targets of neuronal  |
| 2190-2205 | `neuronal cuprop` | th in TLE. Furthermore, LIPT1 and FDX1 appear as potential targets of neuronal cuproptosis for controlling TLE's seizures and progression. |
| 2207-2210 | `sis` | rmore, LIPT1 and FDX1 appear as potential targets of neuronal cuproptosis for controlling TLE's seizures and progression. |
| 2227-2230 | `TLE` | 1 appear as potential targets of neuronal cuproptosis for controlling TLE's seizures and progression. |
| 2233-2241 | `seizures` | ar as potential targets of neuronal cuproptosis for controlling TLE's seizures and progression. |

## PMID 36173142

- Disease spans: 35
- Pathway spans: 4
- Abstract length: 1640 characters

### Abstract

> AIM: There are no recommended guidelines or clinical studies on safety of **COVID-19** vaccines in patients with **inborn errors of metabolism** (**IEMs**). Here, we aimed to examine the relationship between **COVID-19** vaccination and metabolic outcome in paediatric **IEM** patients. METHODS: Patients with **IEM** between the ages of 12 and 18 were enrolled. Term **metabolic decompensation** was defined as acute disruption in metabolic homeostasis due to vaccination. Clinical and biochemical markers were compared between pre- and post-vaccination periods. RESULTS: Data from a total of 36 vaccination episodes in 18 patients were included. Thirteen patients had intoxication-type **metabolic disorders** including **organic acidemia** (**OA**), **urea cycle disorders** (**UCDs**), **maple syrup urine disease** (**MSUD**) and **phenylketonuria** (**PKU**); 4 patients had **energy metabolism disorders** including **fatty acid metabolism disorders** and **LIPIN 1 deficiency**; and 1 patient had **glycogen storage disorder** (**GSD) type 5**. Seventeen patients received BNT162b2, and 1 received CoronaVac because of an underlying **long QT syndrome**. **Fatty acid metabolism disorders**, **LIPIN 1 deficiency** and **GSD type 5** were included in the same group named '**metabolic myopathies**'. In two **PKU** patients, plasma phenylalanine level increased significantly within 24 h following the second dose of vaccination. None of the **OA**, **UCD**, **MSUD** and **metabolic myopathy** patients experienced acute metabolic attack and had emergency department admission due to **metabolic decompensation** within 1 month after vaccination. CONCLUSIONS: **COVID-19** vaccines did not cause acute **metabolic decompensation** in a cohort of 18 children with **IEM**.

### Detected disease spans

| Character range (start-end) | Matched text | Local context |
|---|---|---|
| 74-82 | `COVID-19` |  There are no recommended guidelines or clinical studies on safety of COVID-19 vaccines in patients with inborn errors of metabolism (IEMs). Here, w |
| 109-136 | `inborn errors of metabolism` | s or clinical studies on safety of COVID-19 vaccines in patients with inborn errors of metabolism (IEMs). Here, we aimed to examine the relationship between COVID-19 v |
| 138-142 | `IEMs` | ty of COVID-19 vaccines in patients with inborn errors of metabolism (IEMs). Here, we aimed to examine the relationship between COVID-19 vaccina |
| 196-204 | `COVID-19` | metabolism (IEMs). Here, we aimed to examine the relationship between COVID-19 vaccination and metabolic outcome in paediatric IEM patients. METHODS |
| 253-256 | `IEM` | ship between COVID-19 vaccination and metabolic outcome in paediatric IEM patients. METHODS: Patients with IEM between the ages of 12 and 18 we |
| 290-293 | `IEM` |  metabolic outcome in paediatric IEM patients. METHODS: Patients with IEM between the ages of 12 and 18 were enrolled. Term metabolic decompens |
| 344-368 | `metabolic decompensation` | : Patients with IEM between the ages of 12 and 18 were enrolled. Term metabolic decompensation was defined as acute disruption in metabolic homeostasis due to vacci |
| 660-679 | `metabolic disorders` | in 18 patients were included. Thirteen patients had intoxication-type metabolic disorders including organic acidemia (OA), urea cycle disorders (UCDs), maple s |
| 690-706 | `organic acidemia` | Thirteen patients had intoxication-type metabolic disorders including organic acidemia (OA), urea cycle disorders (UCDs), maple syrup urine disease (MSUD) a |
| 708-710 | `OA` | had intoxication-type metabolic disorders including organic acidemia (OA), urea cycle disorders (UCDs), maple syrup urine disease (MSUD) and p |
| 713-733 | `urea cycle disorders` | ntoxication-type metabolic disorders including organic acidemia (OA), urea cycle disorders (UCDs), maple syrup urine disease (MSUD) and phenylketonuria (PKU); 4 |
| 735-739 | `UCDs` | olic disorders including organic acidemia (OA), urea cycle disorders (UCDs), maple syrup urine disease (MSUD) and phenylketonuria (PKU); 4 patie |
| 742-767 | `maple syrup urine disease` | sorders including organic acidemia (OA), urea cycle disorders (UCDs), maple syrup urine disease (MSUD) and phenylketonuria (PKU); 4 patients had energy metabolism di |
| 769-773 | `MSUD` | cidemia (OA), urea cycle disorders (UCDs), maple syrup urine disease (MSUD) and phenylketonuria (PKU); 4 patients had energy metabolism disorder |
| 779-794 | `phenylketonuria` | A), urea cycle disorders (UCDs), maple syrup urine disease (MSUD) and phenylketonuria (PKU); 4 patients had energy metabolism disorders including fatty aci |
| 796-799 | `PKU` | sorders (UCDs), maple syrup urine disease (MSUD) and phenylketonuria (PKU); 4 patients had energy metabolism disorders including fatty acid met |
| 817-844 | `energy metabolism disorders` |  syrup urine disease (MSUD) and phenylketonuria (PKU); 4 patients had energy metabolism disorders including fatty acid metabolism disorders and LIPIN 1 deficiency; and |
| 855-886 | `fatty acid metabolism disorders` | ketonuria (PKU); 4 patients had energy metabolism disorders including fatty acid metabolism disorders and LIPIN 1 deficiency; and 1 patient had glycogen storage disorder ( |
| 891-909 | `LIPIN 1 deficiency` | gy metabolism disorders including fatty acid metabolism disorders and LIPIN 1 deficiency; and 1 patient had glycogen storage disorder (GSD) type 5. Seventeen  |
| 929-954 | `glycogen storage disorder` | y acid metabolism disorders and LIPIN 1 deficiency; and 1 patient had glycogen storage disorder (GSD) type 5. Seventeen patients received BNT162b2, and 1 received Co |
| 956-967 | `GSD) type 5` |  and LIPIN 1 deficiency; and 1 patient had glycogen storage disorder (GSD) type 5. Seventeen patients received BNT162b2, and 1 received CoronaVac becau |
| 1057-1073 | `long QT syndrome` |  received BNT162b2, and 1 received CoronaVac because of an underlying long QT syndrome. Fatty acid metabolism disorders, LIPIN 1 deficiency and GSD type 5 w |
| 1075-1106 | `Fatty acid metabolism disorders` | , and 1 received CoronaVac because of an underlying long QT syndrome. Fatty acid metabolism disorders, LIPIN 1 deficiency and GSD type 5 were included in the same group na |
| 1108-1126 | `LIPIN 1 deficiency` | e of an underlying long QT syndrome. Fatty acid metabolism disorders, LIPIN 1 deficiency and GSD type 5 were included in the same group named 'metabolic myopa |
| 1131-1141 | `GSD type 5` |  QT syndrome. Fatty acid metabolism disorders, LIPIN 1 deficiency and GSD type 5 were included in the same group named 'metabolic myopathies'. In two  |
| 1181-1201 | `metabolic myopathies` | IN 1 deficiency and GSD type 5 were included in the same group named 'metabolic myopathies'. In two PKU patients, plasma phenylalanine level increased significa |
| 1211-1214 | `PKU` |  were included in the same group named 'metabolic myopathies'. In two PKU patients, plasma phenylalanine level increased significantly within 2 |
| 1342-1344 | `OA` | tly within 24 h following the second dose of vaccination. None of the OA, UCD, MSUD and metabolic myopathy patients experienced acute metaboli |
| 1346-1349 | `UCD` | within 24 h following the second dose of vaccination. None of the OA, UCD, MSUD and metabolic myopathy patients experienced acute metabolic att |
| 1351-1355 | `MSUD` | n 24 h following the second dose of vaccination. None of the OA, UCD, MSUD and metabolic myopathy patients experienced acute metabolic attack an |
| 1360-1378 | `metabolic myopathy` | llowing the second dose of vaccination. None of the OA, UCD, MSUD and metabolic myopathy patients experienced acute metabolic attack and had emergency departm |
| 1469-1493 | `metabolic decompensation` |  acute metabolic attack and had emergency department admission due to metabolic decompensation within 1 month after vaccination. CONCLUSIONS: COVID-19 vaccines did  |
| 1541-1549 | `COVID-19` | tabolic decompensation within 1 month after vaccination. CONCLUSIONS: COVID-19 vaccines did not cause acute metabolic decompensation in a cohort of  |
| 1579-1603 | `metabolic decompensation` | after vaccination. CONCLUSIONS: COVID-19 vaccines did not cause acute metabolic decompensation in a cohort of 18 children with IEM. |
| 1636-1639 | `IEM` |  cause acute metabolic decompensation in a cohort of 18 children with IEM. |

## PMID 42282152

- Disease spans: 23
- Pathway spans: 1
- Abstract length: 5342 characters

### Abstract

> BACKGROUND: **Progressive multiple sclerosis** (**MS**) is characterized by ongoing neurodegeneration and limited therapeutic options. Circulating metabolites provide insight into disease biology, yet biomarkers that predict disability progression and reflect treatment response are lacking. We aimed to identify metabolomic signatures associated with longitudinal MRI measures of **brain** atrophy and to evaluate whether ibudilast treatment was associated with metabolite trajectories over time. METHODS: We repeatedly profiled 1,726 plasma metabolites using untargeted UPLC-MS/MS in 244 participants (mean age 55.6 years; 53.3% female; 3.3% non-White) from the 96-week SPRINT-MS randomized trial of oral ibudilast (≤100 mg daily; n=123) versus placebo (n=121). Weighted gene co-expression network analysis was used to derive groups of related metabolites. Associations between baseline metabolites groups and longitudinal MRI outcomes were evaluated using linear mixed-effects models adjusted for demographic, clinical, and treatment covariates. The primary outcome was the rate of whole-**brain atrophy** measured by brain parenchymal fraction (BPF), defined as the proportion of intracranial volume occupied by brain tissue. Secondary outcomes included white matter fraction (WMF), gray matter fraction (GMF), and cortical thickness (CTH). Metabolite groups nominally associated with MRI outcomes (p<0.05) were followed by individual metabolite analyses to identify potential drivers. Significant metabolites were tested for replication in a comparable real-world observational HEAL-MS cohort with longitudinal MRI data (n=249; mean age 56.3 years; 71.1% female; 19.4% non-White). Lastly, we tested whether ibudilast treatment was associated with metabolite trajectories and performed metabolite set enrichment analysis. FINDINGS: Higher baseline levels of glycerophospholipids were associated with slower decline in both BPF and WMF, and sphingomyelins were similarly associated with slower BPF decline. For example, higher 1-palmityl-2-stearoyl-GPC (O-16:0/18:0) levels were associated with slower BPF decline in SPRINT-MS (β=0.016 [0.008, 0.024]; p=4.35×10⁻ 5 ) and replicated in HEAL-MS (β=0.108 [0.006, 0.211], p=3.90×10⁻ 2 ). Metabolites associated with GMF preservation were enriched in androgenic steroids and steroid sulfates, with consistent positive associations observed in the replication cohort, whereas metabolites inversely associated with CTH were predominantly xenobiotic-related. Ibudilast treatment was associated with increased sphingomyelin species (e.g., palmitoyl sphingomyelin (d18:1/16:0); β = 0.185 [0.085, 0.286], FDR = 1.79×10 -2 ) and decreased levels of amino acid-related metabolites (e.g., anthranilate; β = -0.270 [-0.403, -0.137]; FDR = 3.87×10 -2 ). Pathway-based analyses corroborated these findings, highlighting glycerophospholipid and sphingolipid metabolism as key pathways implicated in **brain atrophy** in **MS**. INTERPRETATION: Distinct lipid subsets were associated with slower **brain atrophy** in people with **MS**, and ibudilast treatment was associated with metabolite alterations in potentially neuroprotective directions. Metabolomics may provide prognostic and pharmacodynamic biomarkers for progressive **MS**. FUNDING: The study was supported by the National Institute of **Neurological Disorders** and **Stroke** (NINDS) grant R01NS133005 and the National Institute of Nursing Research (NINR) grants R01NR018851. RESEARCH IN CONTEXT: Evidence before this study: Circulating metabolites are altered in people with **multiple sclerosis** (**MS**). Before conducting this work, we systematically searched PubMed from database inception to March 23, 2026, for articles published in English using the search terms ("metabolomics" OR "plasma metabolites") AND ("**multiple sclerosis**" OR "MS") AND ("MRI" OR "**brain** atrophy" OR "brain parenchymal fraction" OR "gray matter" OR "white matter") AND ("longitudinal" OR "progression" OR "**brain atrophy**"). We also reviewed reference lists of relevant publications. Prior studies have linked selected metabolites to clinical disability and **brain atrophy** in **MS**. However, most studies have been cross-sectional, limited by small sample sizes, or focused on case-control comparisons. Importantly, few studies have evaluated longitudinal associations between circulating metabolites and MRI-derived measures of **brain atrophy**, and studies integrating clinical trial data, external replication, and treatment-related metabolic changes remain scarce.Added value of this study: In a multicenter randomized clinical trial with longitudinal metabolomic profiling and MRI outcomes, we identified lipid-related metabolic signatures associated with **brain atrophy**, with consistent directionality observed in an independent cohort. We further demonstrated that ibudilast treatment was associated with longitudinal changes in specific metabolites, linking metabolic pathways to both disease progression and therapeutic response.Implications of all the available evidence: These findings support circulating metabolomic signatures as potential markers of **brain atrophy** in **MS**. Metabolomics may provide a scalable approach to identify individuals at risk of progressive brain **tissue** loss and to inform future mechanistic and therapeutic investigations targeting metabolic pathways involved in disability progression.

### Detected disease spans

| Character range (start-end) | Matched text | Local context |
|---|---|---|
| 12-42 | `Progressive multiple sclerosis` | BACKGROUND: Progressive multiple sclerosis (MS) is characterized by ongoing neurodegeneration and limited therap |
| 44-46 | `MS` | BACKGROUND: Progressive multiple sclerosis (MS) is characterized by ongoing neurodegeneration and limited therapeuti |
| 373-378 | `brain` | y metabolomic signatures associated with longitudinal MRI measures of brain atrophy and to evaluate whether ibudilast treatment was associated wi |
| 1079-1092 | `brain atrophy` | , and treatment covariates. The primary outcome was the rate of whole-brain atrophy measured by brain parenchymal fraction (BPF), defined as the proporti |
| 2918-2931 | `brain atrophy` | hospholipid and sphingolipid metabolism as key pathways implicated in brain atrophy in MS. INTERPRETATION: Distinct lipid subsets were associated with sl |
| 2935-2937 | `MS` | phingolipid metabolism as key pathways implicated in brain atrophy in MS. INTERPRETATION: Distinct lipid subsets were associated with slower b |
| 3006-3019 | `brain atrophy` | S. INTERPRETATION: Distinct lipid subsets were associated with slower brain atrophy in people with MS, and ibudilast treatment was associated with metabo |
| 3035-3037 | `MS` | ipid subsets were associated with slower brain atrophy in people with MS, and ibudilast treatment was associated with metabolite alterations i |
| 3232-3234 | `MS` | may provide prognostic and pharmacodynamic biomarkers for progressive MS. FUNDING: The study was supported by the National Institute of Neurol |
| 3298-3320 | `Neurological Disorders` | ive MS. FUNDING: The study was supported by the National Institute of Neurological Disorders and Stroke (NINDS) grant R01NS133005 and the National Institute of Nu |
| 3325-3331 | `Stroke` | was supported by the National Institute of Neurological Disorders and Stroke (NINDS) grant R01NS133005 and the National Institute of Nursing Resea |
| 3532-3550 | `multiple sclerosis` | before this study: Circulating metabolites are altered in people with multiple sclerosis (MS). Before conducting this work, we systematically searched PubMed  |
| 3552-3554 | `MS` | irculating metabolites are altered in people with multiple sclerosis (MS). Before conducting this work, we systematically searched PubMed from |
| 3767-3785 | `multiple sclerosis` | using the search terms ("metabolomics" OR "plasma metabolites") AND ("multiple sclerosis" OR "MS") AND ("MRI" OR "brain atrophy" OR "brain parenchymal fractio |
| 3811-3816 | `brain` | lasma metabolites") AND ("multiple sclerosis" OR "MS") AND ("MRI" OR "brain atrophy" OR "brain parenchymal fraction" OR "gray matter" OR "white m |
| 3935-3948 | `brain atrophy` | y matter" OR "white matter") AND ("longitudinal" OR "progression" OR "brain atrophy"). We also reviewed reference lists of relevant publications. Prior s |
| 4085-4098 | `brain atrophy` | r studies have linked selected metabolites to clinical disability and brain atrophy in MS. However, most studies have been cross-sectional, limited by sm |
| 4102-4104 | `MS` | nked selected metabolites to clinical disability and brain atrophy in MS. However, most studies have been cross-sectional, limited by small sa |
| 4352-4365 | `brain atrophy` | ociations between circulating metabolites and MRI-derived measures of brain atrophy, and studies integrating clinical trial data, external replication, a |
| 4681-4694 | `brain atrophy` | mes, we identified lipid-related metabolic signatures associated with brain atrophy, with consistent directionality observed in an independent cohort. We |
| 5083-5096 | `brain atrophy` | gs support circulating metabolomic signatures as potential markers of brain atrophy in MS. Metabolomics may provide a scalable approach to identify indiv |
| 5100-5102 | `MS` | ating metabolomic signatures as potential markers of brain atrophy in MS. Metabolomics may provide a scalable approach to identify individuals |
| 5202-5208 | `tissue` | calable approach to identify individuals at risk of progressive brain tissue loss and to inform future mechanistic and therapeutic investigations  |

## PMID 16386921

- Disease spans: 20
- Pathway spans: 0
- Abstract length: 3082 characters

### Abstract

> OBJECTIVE: Primary **graft dysfunction** caused by **ischemia-reperfusion injury** is one of the most frequent causes of early morbidity and death after lung transplantation. We hypothesized that the perioperative management with aprotinin decreases the incidence of allograft **reperfusion injury** and dysfunction after clinical lung transplantation. METHODS: Lung transplant databases of two transplant centers were used to investigate the incidence of severe post-transplant **reperfusion injury** (**PTRI**). We examined data of 142 patients who underwent either single lung (81) or bilateral sequential lung (61) transplantation for **COPD**, **idiopathic pulmonary fibrosis**, **cystic fibrosis**, and miscellaneous **lung disorders** between 1997 and 2000. Thirty patients were excluded due to heart-lung transplantation or lung transplantation for **Eisenmenger's disease**, re-transplantation, rejection, or deviation from the standardized triple immunosuppression protocol. The data of remaining 112 patients (control group, 64% single lung, 36% sequential bilateral lung transplants) were compared to the prospectively collected data of 59 lung transplant patients over the last 5 years. All of these 59 patients were managed perioperatively with aprotinin infusion. In addition, Euro-Collins-aprotinin procurement solution (Apt-EC group) was used for 50 donor lungs (58% single lung, 42% sequential bilateral lung transplants). Aprotinin in combination with low-potassium dextran (LPD) flush solution (Apt-LPD group) was used for the procurement of 34 lungs (59% single lung, 41% sequential bilateral lung transplants). The International Society of Heart and Lung Transplantation (ISHLT) grade III injury score was used for the diagnosis of severe **PTRI**, which is based on a PaO(2)-FIO(2) ratio of less than 200 mmHg. RESULTS: Severe **reperfusion injury** grade III was observed in 18% of the control group. ECMO support was required in 25% of these patients. The associated mortality rate was 40%. Correlating factors for **PTRI** were donor age greater than 35 years (45%, p=0.01, mean age 38+/-8) and recipient pulmonary artery systolic pressure greater than 60 mmHg (48%, p<0.05). Lung graft ischemic times (231+/-14 min) and intraoperative techniques (cardiopulmonary bypass in 12%) were not associated with negative outcomes. Despite longer ischemic times (258+/-36 min and 317+/-85 min, respectively) and older donors (42+/-12 years and 46+/-12 years, respectively) in the aprotinin patient groups (Apt-EC and Apt-LPD group), the incidence of **PTRI** was markedly lower (6% and 9%, respectively). There was no mortality in the Apt-EC group and one patient died in the Apt-LPD group due to **PTR**I-induced **graft failure**. CONCLUSIONS: Severe **PTRI** increased short-term morbidity and mortality. The incidence of **reperfusion injury** was not dependent upon the duration of donor organ **ischemia**. The use of aprotinin in the perioperative patient management in lung transplantation had strong beneficial effects on the patient outcomes and decreased the incidence of post-transplant **ischemia-reperfusion injury** significantly.

### Detected disease spans

| Character range (start-end) | Matched text | Local context |
|---|---|---|
| 19-36 | `graft dysfunction` | OBJECTIVE: Primary graft dysfunction caused by ischemia-reperfusion injury is one of the most frequent cau |
| 47-74 | `ischemia-reperfusion injury` | OBJECTIVE: Primary graft dysfunction caused by ischemia-reperfusion injury is one of the most frequent causes of early morbidity and death after |
| 269-287 | `reperfusion injury` | rative management with aprotinin decreases the incidence of allograft reperfusion injury and dysfunction after clinical lung transplantation. METHODS: Lung tr |
| 467-485 | `reperfusion injury` | ters were used to investigate the incidence of severe post-transplant reperfusion injury (PTRI). We examined data of 142 patients who underwent either single  |
| 487-491 | `PTRI` | vestigate the incidence of severe post-transplant reperfusion injury (PTRI). We examined data of 142 patients who underwent either single lung ( |
| 619-623 | `COPD` | ingle lung (81) or bilateral sequential lung (61) transplantation for COPD, idiopathic pulmonary fibrosis, cystic fibrosis, and miscellaneous lu |
| 625-654 | `idiopathic pulmonary fibrosis` | lung (81) or bilateral sequential lung (61) transplantation for COPD, idiopathic pulmonary fibrosis, cystic fibrosis, and miscellaneous lung disorders between 1997 and 2 |
| 656-671 | `cystic fibrosis` | al lung (61) transplantation for COPD, idiopathic pulmonary fibrosis, cystic fibrosis, and miscellaneous lung disorders between 1997 and 2000. Thirty patie |
| 691-705 | `lung disorders` | PD, idiopathic pulmonary fibrosis, cystic fibrosis, and miscellaneous lung disorders between 1997 and 2000. Thirty patients were excluded due to heart-lun |
| 821-842 | `Eisenmenger's disease` | xcluded due to heart-lung transplantation or lung transplantation for Eisenmenger's disease, re-transplantation, rejection, or deviation from the standardized tr |
| 1721-1725 | `PTRI` | n (ISHLT) grade III injury score was used for the diagnosis of severe PTRI, which is based on a PaO(2)-FIO(2) ratio of less than 200 mmHg. RESUL |
| 1806-1824 | `reperfusion injury` | based on a PaO(2)-FIO(2) ratio of less than 200 mmHg. RESULTS: Severe reperfusion injury grade III was observed in 18% of the control group. ECMO support was  |
| 1992-1996 | `PTRI` | ients. The associated mortality rate was 40%. Correlating factors for PTRI were donor age greater than 35 years (45%, p=0.01, mean age 38+/-8) a |
| 2515-2519 | `PTRI` | aprotinin patient groups (Apt-EC and Apt-LPD group), the incidence of PTRI was markedly lower (6% and 9%, respectively). There was no mortality  |
| 2658-2661 | `PTR` |  in the Apt-EC group and one patient died in the Apt-LPD group due to PTRI-induced graft failure. CONCLUSIONS: Severe PTRI increased short-term |
| 2671-2684 | `graft failure` | C group and one patient died in the Apt-LPD group due to PTRI-induced graft failure. CONCLUSIONS: Severe PTRI increased short-term morbidity and mortalit |
| 2706-2710 | `PTRI` |  Apt-LPD group due to PTRI-induced graft failure. CONCLUSIONS: Severe PTRI increased short-term morbidity and mortality. The incidence of reperf |
| 2774-2792 | `reperfusion injury` | e PTRI increased short-term morbidity and mortality. The incidence of reperfusion injury was not dependent upon the duration of donor organ ischemia. The use  |
| 2844-2852 | `ischemia` | reperfusion injury was not dependent upon the duration of donor organ ischemia. The use of aprotinin in the perioperative patient management in lung |
| 3040-3067 | `ischemia-reperfusion injury` | n the patient outcomes and decreased the incidence of post-transplant ischemia-reperfusion injury significantly. |


