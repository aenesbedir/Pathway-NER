# Pathway Annotation için LLM Seçimi ve Donanım Senaryoları

**Tarih:** 2026-07-21
**Soru:** Pathway anotasyonu için qwen2.5:14b'den daha iyi bir LLM var mı? Medikal amaçlı özel LLM'ler işe yarar mı? Bu PC'de en iyi ne çalışır, ve donanım değiştirmeye değer mi?
**Yöntem:** Repo durumu + literatür/web taraması (Temmuz 2026 itibarıyla). Kaynaklar en altta.

---

## 0. Özet — 5 madde

1. **"Medikal LLM" bu görev için bir tuzak.** Literatür tutarlı biçimde şunu gösteriyor: biyomedikal fine-tune edilmiş modeller *information extraction*'da genel modelleri geçmiyor, sık sık **geriye düşüyor**. MedGemma'nın kendi teknik raporunda NER/IE benchmark'ı bile yok — QA ve görüntüleme için optimize edilmiş. (Bkz. §2)
2. **En yüksek ROI'li alternatif bir LLM değil: `GLiNER-BioMed`.** 434M parametreli encoder, zero-shot 59.8 F1, **50-shot 76.0 F1**. Senin 8GB GPU'nda saniyeler içinde koşar, halüsinasyon yapamaz (span'ları doğrudan metinden seçer), ve LLM'in yapısal olarak kaçırdığı şeyleri (word-order, dedup) farklı bir mekanizmayla yakalar → ensemble'da 3. kaynak. (Bkz. §3.1)
3. **qwen2.5 artık iki nesil eski.** Qwen3.5 (Şub–Mar 2026) ve Gemma 4 (Nis 2026, Apache 2.0) çıktı. `qwen3.5:9b` mevcut GPU'na sığar ve `qwen2.5:14b`'den güçlü olması beklenir — bedava upgrade. (Bkz. §3.2)
4. **Donanım almana gerek yok. $130'luk RAM upgrade'i, $2000'lık GPU'dan daha fazla kapı açıyor.** Laptop'un Lenovo LOQ 15APH8 (82XT), 2× SO-DIMM DDR5 slotu var, 64GB'a çıkabilir. Bu, MoE modelleri (gpt-oss-20b, Qwen3.5-35B-A3B, Gemma-4-26B-MoE) CPU offload ile çalıştırmanı sağlar — sadece 3B aktif parametre, yani yavaş ama kabul edilebilir. "Uzun süre bekleyebilirim" dediğin için bu senaryo tam sana göre. (Bkz. §4)
5. **Hiç göz ardı edilmiş en ucuz seçenek: frontier API.** Veri public PubMed abstract'ı, gizlilik engeli yok. Tüm 10.142 abstract'ı Gemini Flash-Lite ile etiketlemek **~$3**, Claude Haiku ile **~$10**. Lokal 20 saatlik run'dan hem ucuz hem büyük ihtimalle daha kaliteli. (Bkz. §5)

**Ama önce bir uyarı (§7):** golden set'in 10 abstract / 76 mention. Mevcut tracking'de bile "±1-2 mention run noise" notu var. Bu boyutta bir eval set ile "hangi model daha iyi" sorusunu **ölçemezsin**. Model seçimine para/zaman harcamadan önce eval set'i büyütmek gerek.

---

## 1. Başlangıç noktası: şu an nerede duruyorsun

Repo'dan çıkarılan mevcut durum:

| | Değer |
|---|---|
| Seçili model | `qwen2.5:14b` (q4, ~9GB) via Ollama |
| Config | no-vocab + lenient + "synonyms" wording, `temperature=0, seed=42` |
| Golden set (v2, 10 abstract) | precision_lenient **0.95**, `span:exact` 11/11, **`span:variation` 4/6** |
| Ek recall kaynağı | `llm/booster.py` — deterministik word-order/dedup fallback, span'ların ~%9'u |
| 1k pilot | 39 dk (**2.4 s/abstract**), 1.996 span, 532 unique surface form (exact matching: 81) |
| Hedef korpus | **10.142 abstract**, ortalama 1.710 karakter ≈ **4.3M token** |

Donanım:

| | |
|---|---|
| GPU | NVIDIA RTX 4060 Laptop, **8 GB VRAM** |
| CPU | AMD Ryzen 7 7840HS (8C/16T, AVX-512 destekli) |
| RAM | **15 GB** ← asıl darboğaz |
| Disk | 53 GB boş |
| Makine | Lenovo LOQ 15APH8 (82XT) |

**Kritik gözlem:** 8GB VRAM'den çok, **15GB sistem RAM'i** seni sınırlıyor. VRAM'e sığmayan modeller RAM'e offload edilir; 15GB ile bu kapı neredeyse kapalı. RAM 64GB olsaydı 20–35B sınıfı MoE modeller (yavaş da olsa) çalışırdı.

**İkinci kritik gözlem:** 14b modelin *ölçülen* zayıflığı precision değil, `span:variation` recall'ı — ve tracking'de zaten kaydedilmiş ki **7b→14b geçişi bu metriği hiç iyileştirmedi (4/6 → 4/6)**. Yani "daha büyük model" ekseni bu görevde ölçülmüş şekilde tıkanmış durumda. Model değiştirmenin bir faydası olacaksa, farklı bir *mekanizmadan* gelmeli — daha fazla parametreden değil.

---

## 2. "Medikal LLM" sorusu: cevap büyük ölçüde hayır

Aday medikal modeller ve durumları:

| Model | Boyut | Durum | Senin görevin için |
|---|---|---|---|
| **MedGemma 1.5** (Oca 2026) | 4B | Gemma 3 tabanlı, multimodal | ⚠️ Test edilebilir (GPU'na sığar) ama IE için kanıt yok |
| **MedGemma 27B-text-it** | 27B | En güçlü açık ağırlıklı medikal model, MedQA ~%91 | ❌ 8GB'a sığmaz (q4'te ~16GB) |
| **OpenBioLLM** | 8B / 70B | Llama 3 tabanlı, clinical entity recognition iddiası | ⚠️ 8B sığar; ama aşağıdaki bulguya dikkat |
| **BioMistral** | 7B | Mistral + PubMed Central continued pretraining | ⚠️ Sığar, düşük öncelik |
| **Meditron / PMC-LLaMA** | 7B–70B | Klinik odaklı | ❌ IE'de zayıf bulundu |

**Neden şüpheci olmak gerekiyor — üç bağımsız bulgu:**

1. *Diagnosing our datasets* (arXiv 2505.15024): genel-domain modeller, sadece genel internet korpusuyla eğitilmiş olmalarına rağmen, medikal fine-tune edilmiş muadilleriyle **standart benchmark'larda eşit** performans gösteriyor.
2. Klinik IE değerlendirmelerinde **`Llama-3-8B-UltraMedical` ve `PMC-Llama 13B`, base `Llama-3.1-8B`'den belirgin şekilde daha kötü** sonuç verdi. Yani medikal fine-tuning IE yeteneğini aktif olarak bozabiliyor — model tıbbi bilgi kazanırken talimat-takip ve yapılandırılmış çıktı disiplinini kaybediyor.
3. **MedGemma teknik raporunda NER veya structured extraction benchmark'ı yok.** Değerlendirmeler: MedQA/MedMCQA/PubMedQA (soru-cevap), göğüs röntgeni sınıflandırma, VQA, rapor üretimi. "Medikal" etiketi senin görevine transfer edeceğinin garantisi değil.

**Mekanik sebep:** Senin görevin tıbbi *bilgi* gerektirmiyor. Prompt zaten query pathway'leri veriyor, canonical mapping'i downstream sen yapıyorsun. Modelden istenen şey: *"bu metinde metabolik süreç adlandıran verbatim substring'leri bul ve JSON döndür."* Bu bir **talimat-takip + span disiplini + JSON formatı** görevi. Medikal fine-tuning'in optimize ettiği şey (USMLE muhakemesi, klinik not anlama) bu değil — hatta bunun tersine çalışıyor.

**Karar:** MedGemma-1.5-4B'yi *ucuz olduğu için* golden set'te bir kez ölç (yarım saatlik iş), ama medikal modellere yatırım yapma. Beklenti düşük tut.

---

## 3. Gerçekten umut vaat eden üç yön

### 3.1 GLiNER-BioMed — en yüksek ROI'li seçenek ⭐

Bu bir LLM değil, **span-seçen bir encoder**. NER'i "metin ve etiket açıklamalarını ortak temsil eden tek bir encoder içinde eşleştirme problemi" olarak kuruyor.

| | |
|---|---|
| Boyutlar | small 141M / base 184M / **large 434M** (DeBERTa-v3), uni- ve bi-encoder varyantları |
| Eğitim verisi | OpenBioLLM-70B ile 10k örnek few-shot etiketlenmiş → 8B modele LoRA distill → 105k pasaj etiketlenmiş → **2.3M entity mention / 640k unique entity** |
| Zero-shot | **59.77 F1** (GLiNER v2.5 large: 53.81, GLiNER v1.0: 47.77, NuNER Zero: 40.87) |
| Few-shot | 10-shot **70.39** · 20-shot **73.07** · 50-shot **76.02** F1 |
| Lisans | MIT (repo), modeller HF'de `Ihor/gliner-biomed-{small,base,large}-v1.0` (+ `-bi-` varyantları) |
| Kurulum | `pip install gliner -U` |

**Senin projen için neden özellikle uygun:**

- **Halüsinasyon yapısal olarak imkânsız.** Model metinden span seçer, metin üretmez. `extract_guided.py`'deki verbatim doğrulama filtresi ve offset grounding'e ihtiyaç kalmaz.
- **8GB VRAM'de fazlasıyla rahat.** 434M parametre → 10.142 abstract muhtemelen **dakikalar** sürer, saatler değil. İterasyon maliyetin sıfıra iner.
- **Few-shot eğrisi tam senin veri boyutuna denk geliyor.** 10→50 örnek arası 70→76 F1. Golden set v2'de 10 abstract var; doccano'dan insan-onaylı 1k geldiğinde bu, GLiNER'i fine-tune etmek için bol bol yeterli veri demek — ve o noktada 76 F1'in de üstüne çıkarsın.
- **LLM'den farklı hata profili.** LLM'in ölçülmüş iki zayıflığı (dedup davranışı: aynı cümlede canonical'ı döndürünce varyantı atlaması; word-order tersine çevirme) generative decoding'den kaynaklanıyor. Encoder'da bu mekanizma yok — her aday span bağımsız skorlanır. Bu, `booster.py`'ın deterministik olarak yakaladığı şeyleri **öğrenilmiş** biçimde yakalayabilir.
- Ekosistem devam ediyor: `GLiNER-Relex` (ortak NER + relation extraction) — senin "bigger picture" hedefinde (pathway↔disease ilişkisi) doğrudan ilgili.

**Uyarı:** Bu 59.77 F1 rakamı 8 biyomedikal dataset (hastalık/ilaç/gen) ortalaması; metabolik pathway'ler bu dataset'lerde ana kategori değil. **Kendi golden set'inde ölçmen şart.** Ama test maliyeti bir öğleden sonra.

### 3.2 Yeni nesil genel modeller — qwen2.5 eskidi

Temmuz 2026 itibarıyla manzara:

| Model | Toplam / Aktif | q4 VRAM | 8GB'a sığar mı | Not |
|---|---|---|---|---|
| **Qwen3.5-9B** (Mar 2026) | 9B dense | ~6.6 GB | ✅ | 8GB kartlar için varsayılan öneri; GPQA Diamond'da gpt-oss-120b'yi geçiyor (81.7 vs 71.5) |
| **Gemma 4 E4B** (Nis 2026) | 4.5B eff. | ~4 GB | ✅ | Apache 2.0, 256K context |
| **Gemma 4 12B** | 12B dense | ~8 GB | ⚠️ sınırda | Apache 2.0, multimodal |
| **gpt-oss-20b** | 20B / 3.6B akt. | ~12 GB (MXFP4) | ❌ (RAM ile ✅) | MoE — CPU offload dostu |
| **Gemma 4 26B-MoE** | 26B / 3.8B akt. | ~15 GB | ❌ (RAM ile ✅) | Apache 2.0 |
| **Qwen3.5-35B-A3B** | 35B / 3B akt. | ~20–32 GB | ❌ (RAM ile ✅) | RTX 3090'da 111 tok/s |
| **Qwen3.5/3.6-27B dense** | 27B | ~16–18 GB | ❌ | 24GB GPU gerekir |

**Hemen yapılabilecek en ucuz hamle:** `ollama pull qwen3.5:9b` → mevcut `eval_llm_guided.py` ile ölç. Sıfır maliyet, 30 dakika. `qwen2.5:14b`'den daha küçük olmasına rağmen daha güçlü olması yüksek ihtimal, üstelik **2.4 s/abstract'tan daha da hızlı** koşar.

**Reasoning modu uyarısı:** Qwen3+ ailesinde thinking modu var. Senin task'ın deterministik span extraction — thinking'i kapat (`/no_think` veya `enable_thinking=false`), yoksa hem yavaşlar hem JSON çıktısı bozulabilir.

### 3.3 NuExtract — text-to-JSON için özel eğitilmiş

Görevin tam olarak "metinden yapılandırılmış JSON çıkar" olduğu için doğrudan ilgili:

- `NuExtract-2.0-8B`: 0-shot extraction benchmark'ında **GPT-4.1'i +9 F1**, o3'ü +3 F1 geçiyor
- `NuExtract-tiny` (0.5B) GPT-3.5'i geçiyor; `NuExtract-large` (7B) GPT-4o seviyesinde — 100× küçük olmasına rağmen
- **NuExtract 3** (2026): 4B unified VLM, Apache 2.0

**Ancak:** NuExtract ağırlıklı olarak *doküman* extraction'ı (fatura, form, rapor) için eğitilmiş, biyomedikal serbest metin span'ı için değil. Orta öncelik — GLiNER'den sonra dene.

### 3.4 Ensemble — literatürün önerdiği asıl kazanç

*A Herd of Language Models Makes a Better Zero-shot Annotator for Clinical NER* (ACL Findings 2026): genel-amaçlı + medikal-adapte + NER-uzmanı modellerin anotasyonlarını birleştirmek, vanilla zero-shot baseline'a göre **ortalama F1'de +%8.6** kazandırıyor — üstelik anotasyon maliyetini *düşürerek*. Yöntem (MARY) basit majority voting değil: azınlıkta kalan entity'lerden, bağlamı çoğunluk-entity'lerinin bağlamına benzeyenleri seçici olarak dahil ediyor.

**Senin için doğrudan uygulanabilir**, çünkü mimarin zaten çok-kaynaklı: LLM + booster + provenance alanları (`source`, `match_type`). Üçüncü bir kaynak olarak GLiNER-BioMed eklemek bu şemaya doğal oturur. Ve doccano review modelin zaten "kabul/red/düzelt" — yani precision'ı insan koruyor, sen recall'ı maksimize etmelisin. Ensemble tam olarak bunu yapar.

**Bu, raporun en somut mimari önerisi:** tek bir "daha iyi model" aramayı bırak, **hata profilleri farklı 2-3 kaynağı birleştir** ve kararı doccano'daki insana bırak.

---

## 4. Donanım senaryoları

### Senaryo 0 — Mevcut (baz çizgi)
RTX 4060 8GB / 15GB RAM. Tavan: **~14B dense q4**. 10k abstract ≈ **6.8 saat** (pilot'un 2.4 s/abstract'ı üzerinden). Maliyet: $0.

### Senaryo 1 — RAM 64GB'a çıkar ⭐ **EN İYİ ROI**

| | |
|---|---|
| Maliyet | **~$130** (Crucial 2×32GB DDR5-5600 SO-DIMM kit) |
| Uygulanabilirlik | Lenovo LOQ 15APH8 (82XT) **2× SO-DIMM slot**, kullanıcı tarafından yükseltilebilir |
| Açtığı kapı | gpt-oss-20b, Gemma-4-26B-MoE, Qwen3.5-35B-A3B — **CPU offload ile** |
| Mekanizma | llama.cpp `--n-cpu-moe`: expert katmanlarını RAM'e taşı, attention'ı GPU'da tut. MoE'lerde token başına sadece ~3B aktif parametre → CPU'da bile katlanılabilir hız |
| Tahmini hız | ~10–20 s/abstract (dense 35B'de dakikalar sürerdi). 10k abstract ≈ **30–55 saat** |
| Senin durumunda | "Süre önemli değil, uzun bekleyebilirim" dediğin için **bu senaryo tam sana göre** |

15GB → 64GB, $2000'lık bir GPU'nun açtığı kapıların büyük kısmını $130'a açıyor. **Donanım tarafında yapılacak tek şey buysa, bu olmalı.**

### Senaryo 2 — Cloud GPU kirala (donanım almadan büyük model test et)

| Sağlayıcı / GPU | Fiyat | 10k abstract maliyeti |
|---|---|---|
| RunPod Community RTX 4090 24GB | **$0.34/saat** | ~$2–4 |
| RunPod Community A100 40GB | $1.39/saat | ~$6–10 |
| Vast.ai RTX 4090 (spot) | ~$0.14/saat | ~$1–2 |

**Bu senaryonun asıl değeri satın alma kararını riske atmadan test etmek.** MedGemma-27B, Qwen3.5-27B, Qwen3.6-27B gibi modelleri golden set'te ölçmek için birkaç saatlik kiralama yeter — **$1'dan az**. Eğer 27B sınıfı ölçülebilir bir fark yaratmıyorsa (7b→14b'de yaratmadığı gibi), GPU satın alma sorusu kendiliğinden kapanır.

**Yapılacak sıralama net: önce kirala, ölç, sonra karar ver.**

### Senaryo 3 — Masaüstü GPU satın al

| GPU | VRAM | Fiyat (MSRP) | Kazanç |
|---|---|---|---|
| Kullanılmış RTX 3090 | 24 GB | ~$700–900 | 27B q4 tam VRAM'de; en iyi $/GB |
| RTX 4090 | 24 GB | ~$1.599 | 27–32B dense rahat |
| RTX 5090 | 32 GB | ~$1.999 | 70B q4; bellek bant genişliği 1.792 GB/s (4090: 1.008) → 4090'a göre %40–80 hızlı |

**Ama:** laptop'un masaüstü GPU alamaz. Bu, ayrı bir masaüstü sistemi (+ anakart/PSU/kasa) demek → gerçek maliyet $1.000–2.500.

**Bu senaryoya karşı argüman güçlü:** projendeki ölçülmüş darboğaz VRAM değil. `span:variation` 4/6, 7B'de de 14B'de de aynı. Daha büyük VRAM daha büyük model demek, ama daha büyük model bu metriği düzeltmiyor — bu, elinde zaten ölçülmüş bir veri. GPU almadan önce Senaryo 2 ile 27B'nin gerçekten fark yarattığını *kanıtla*.

### Senaryo 4 — Frontier API (§5)

### Karşılaştırma tablosu

| Senaryo | Ön maliyet | 10k run maliyeti | 10k run süresi | Erişilen model tavanı |
|---|---|---|---|---|
| 0 — Mevcut | $0 | $0 | ~7 saat | 14B dense |
| **1 — +64GB RAM** ⭐ | **~$130** | $0 | ~30–55 saat | **35B MoE / 26B MoE** |
| 2 — Cloud spot | $0 | ~$2–8 | ~3–11 saat | 70B'ye kadar |
| 3 — Masaüstü 5090 | ~$2.500 | $0 | ~4 saat | 70B q4 |
| **4 — API** ⭐ | $0 | **~$3–15** | ~2–4 saat | **Frontier** |

---

## 5. Frontier API — en çok göz ardı edilen seçenek

**Gizlilik engeli yok:** veri public PubMed abstract'ı. Lokal çalıştırma kısıtı bu projede teknik bir zorunluluk değil, sadece bir alışkanlık.

**Hesap** (10.142 abstract × ~430 token metin + ~350 token prompt şablonu ≈ **7.9M input**, ~0.5M output):

| Model | Fiyat (in/out per 1M) | Tahmini toplam |
|---|---|---|
| Gemini 3.1 Flash-Lite | $0.25 / $1.50 | **~$3** |
| Claude Haiku 4.5 | $1 / $5 | **~$10** |
| Gemini 3.5 Flash | $1.50 / $9 | **~$16** |

> ⚠️ Bu fiyatlar web kaynaklı (Haziran–Temmuz 2026 taramaları). Faturalamadan önce sağlayıcının resmî fiyat sayfasından doğrula.

**Neden ciddiye alınmalı:** 10 abstract'lık golden set'te bir frontier modeli test etmek **birkaç sent**. Eğer `span:variation` recall'ını 4/6'dan 6/6'ya çıkarıyorsa, tüm korpusu $3–10'a etiketlemek — 55 saatlik lokal run'a ve $2.000'lık GPU'ya karşı — tartışmasız kazanan.

**Karşı argümanlar (gerçek ve dikkate alınmalı):**
- **Tez/yayın tekrarlanabilirliği:** API modelleri sessizce güncellenir; `temperature=0, seed=42` lokal determinizmini alamazsın. → Azaltma: model versiyonunu pinle, tüm ham yanıtları cache'le (zaten `data/raw/llm_cache_silver/` altyapın var).
- **Metodolojik tutarlılık:** proje "local LLM hybrid approach" olarak konumlanmış; anlatıyı değiştirir.
- **Lisans/kullanım koşulları:** üretilen silver label'lar training data olacak — sağlayıcının çıktı kullanım şartlarını kontrol et.

**Uzlaşma önerisi:** frontier API'yi **öğretmen** olarak kullan, üretim etiketleyicisi olarak değil. Bir alt küme (~500 abstract) frontier ile etiketle → bunu GLiNER-BioMed'i fine-tune etmek için kullan → kalan 10k'yı lokal, deterministik, tekrarlanabilir encoder ile etiketle. Bu tam olarak GLiNER-BioMed'in kendi eğitim reçetesi (70B ile 10k etiketle → küçük modele distill et → 105k etiketle) ve $5'ın altında kalır.

---

## 6. Somut aksiyon planı

Mevcut `playground/golden_set/eval_llm_guided.py` harness'ın her adayı aynı metrikle ölçebiliyor — bu raporun çıktısı "şu modeli kullan" değil, **"şu adayları mevcut harness'ında sırayla ölç"**.

### Aşama 0 — Eval set'i düzelt (§7) — **her şeyden önce**
10 abstract / 76 mention ile model kıyaslaması yapılamaz. Golden set'i 30–50 abstract'a çıkar, **veya** doccano'dan gelen insan-onaylı 1k'nın bir dilimini hold-out eval olarak ayır. Bu yapılmadan aşağıdaki tüm ölçümler gürültüden ayırt edilemez.

### Aşama 1 — Bedava kazançlar (bir gün, $0)
1. `ollama pull qwen3.5:9b` → ölç. `qwen2.5:14b` referansına karşı.
2. `ollama pull gemma4:12b` (Apache 2.0) → ölç.
3. Her ikisinde de reasoning/thinking modunu kapat.

### Aşama 2 — GLiNER-BioMed ⭐ (bir gün, $0)
```
pip install gliner -U
# Ihor/gliner-biomed-large-v1.0  ve  Ihor/gliner-biomed-bi-large-v1.0
```
- Zero-shot: label olarak `"metabolic pathway"`, `"metabolic process"` gibi doğal dil açıklamaları dene
- Golden set'te ölç; özellikle `span:variation` alt metriğine bak
- LLM span'ları ile **union** al ve ensemble recall'ını ölç (mevcut `merge()` mantığın bunu zaten yapabilir)

### Aşama 3 — Tavanı gör (yarım gün, <$1)
1. Frontier API'yi (Gemini Flash / Claude Haiku) **sadece 10 golden abstract'ta** çalıştır — birkaç sent
2. Bu, ulaşılabilir tavanı gösterir. Eğer frontier de 4/6'da takılıyorsa, sorun modelde değil **prompt/task tanımında**dır ve hiçbir donanım bunu çözmez — bu tek başına çok değerli bir bilgi.

### Aşama 4 — Büyük model testi (yarım gün, ~$1)
RunPod'da 4090 (24GB, $0.34/h) kirala → `qwen3.5:27b`, `gemma4:31b`, `medgemma:27b` golden set'te ölç. Sonuç 14b'ye yakınsa **GPU satın alma sorusu kapanır**.

### Aşama 5 — Karar
- Aşama 4'te belirgin fark **yoksa** → mevcut donanımda kal. Yatırımı ensemble'a ve eval set'e yap.
- Fark **varsa** → +64GB RAM ($130) al, MoE'leri CPU offload ile koş. Masaüstü GPU'yu sadece bu da yetmezse düşün.

---

## 7. Metodolojik uyarı — bu, model seçiminden daha önemli

`project_tracking.md`'de zaten kayıtlı: *"ollama tam deterministik değil... aynı config run'lar arasında ±1-2 mention değişiyor... 5 abstract'lık golden set bunları hakem etmek için çok küçük."*

Bu uyarı v2'de (10 abstract, 76 mention) hâlâ geçerli. Mevcut ana metrik `span:variation` **6 vakadan** ibaret — yani tek bir mention'ın kayması "%17 recall değişimi" gibi görünüyor. Bu ölçekte:

- Modeller arası %5'lik gerçek farklar görünmez
- Gürültü, gerçek iyileşme gibi okunabilir (ve tersi)
- 7b→14b kararının ("14b daha temiz") dayandığı UNLABELED 9→3 farkı da 6 mention'lık bir taban üzerinde

**Önerilen düzeltme:** doccano'dan insan-onaylı 1k geldiğinde, bunun ~%15'ini model seçimi için **hold-out eval** olarak kilitle ve training'e sokma. Bu, ~150 abstract / ~300 mention'lık gerçek bir eval set demek — model kıyaslamalarının anlam kazanacağı ilk nokta.

Bu yapılmadan bu raporda önerilen hiçbir modelin "daha iyi" olduğu **kanıtlanamaz** — sadece iddia edilebilir.

---

## 8. Nihai öneri

| Öncelik | Aksiyon | Maliyet | Gerekçe |
|---|---|---|---|
| **1** | Eval set'i 150+ abstract'a çıkar (doccano hold-out) | $0, zaman | Bunsuz hiçbir model kararı ölçülebilir değil |
| **2** | GLiNER-BioMed'i 3. anotasyon kaynağı olarak ekle | $0 | 434M, saniyeler, halüsinasyonsuz, farklı hata profili, 50-shot 76 F1 |
| **3** | `qwen2.5:14b` → `qwen3.5:9b` veya `gemma4:12b` | $0 | 2 nesil eski modeli kullanıyorsun; daha küçük *ve* daha hızlı *ve* muhtemelen daha iyi |
| **4** | Frontier API ile tavanı ölç (10 abstract) | ~$0.05 | Sorunun modelde mi prompt'ta mı olduğunu kesin söyler |
| **5** | Cloud'da 27B sınıfını ölç, sonra karar ver | ~$1 | GPU satın alma kararını kanıta bağlar |
| **6** | Gerekirse +64GB RAM | ~$130 | MoE'leri açar; $2000'lık GPU'nun kapılarının çoğunu $130'a açar |
| **7** | Masaüstü GPU | $1.000–2.500 | ❌ Şu an için önerilmiyor — ölçülmüş darboğaç VRAM değil |

**Tek cümlede:** Medikal LLM arama; qwen'i güncelle, yanına GLiNER-BioMed'i ekle, eval set'ini büyüt — ve donanım kararını 1 dolarlık bir cloud testinin sonucuna bağla.

---

## Kaynaklar

**Biyomedikal NER modelleri**
- [GLiNER-BioMed: A Suite of Efficient Models for Open Biomedical NER (arXiv 2504.00676)](https://arxiv.org/html/2504.00676v1) · [Bioinformatics yayını](https://academic.oup.com/bioinformatics/article/42/6/btag322/8690923) · [GitHub ds4dh/GLiNER-biomed](https://github.com/ds4dh/GLiNER-biomed) · [HF: Ihor/gliner-biomed-bi-large-v1.0](https://huggingface.co/Ihor/gliner-biomed-bi-large-v1.0)
- [Do LLMs Surpass Encoders for Biomedical NER? (arXiv 2504.00664)](https://arxiv.org/abs/2504.00664)
- [GLiNER: Generalist Model for NER (NAACL 2024)](https://aclanthology.org/2024.naacl-long.300.pdf)
- [A Herd of Language Models Makes a Better Zero-shot Annotator for Clinical NER (ACL Findings 2026)](https://aclanthology.org/2026.findings-acl.599/)

**Medikal LLM'ler ve sınırları**
- [MedGemma Technical Report (arXiv 2507.05201)](https://arxiv.org/html/2507.05201v4) · [MedGemma 1.5 model card](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card) · [Google Research blog](https://research.google/blog/medgemma-our-most-capable-open-models-for-health-ai-development/)
- [Diagnosing our datasets: How does my language model learn clinical information? (arXiv 2505.15024)](https://arxiv.org/pdf/2505.15024)
- [Leveraging open-source LLMs for clinical information extraction in resource-constrained settings (JAMIA Open)](https://academic.oup.com/jamiaopen/article/8/5/ooaf109/8270821)
- [Benchmarking LLM-based Information Extraction Tools for Medical Documents (medRxiv 2026)](https://www.medrxiv.org/content/10.64898/2026.01.19.26344287v1.full)
- [aaditya/Llama3-OpenBioLLM-8B](https://huggingface.co/aaditya/Llama3-OpenBioLLM-8B) · [Healthcare LLM Landscape 2026](https://nirmitee.io/blog/healthcare-llm-landscape-2026-medgemma-meditron-clinical-model-guide/)

**Genel modeller ve lokal çalıştırma**
- [Qwen 3.5 Locally — 27B vs 35B-A3B vs 122B](https://insiderllm.com/guides/qwen35-local-guide-which-model-fits-your-gpu/) · [Qwen 3.5 + 3.6 + 3.7 Max guide](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
- [Gemma 4 Guide: E2B, E4B, 26B MoE & 31B Open Weights (2026)](https://codersera.com/blog/gemma-4-complete-guide-2026/)
- [Best LLM Models for 8GB VRAM in 2026](https://quantized.fyi/models/best-llm-models-for-8gb-vram-in-2026-tested-ranked/) · [Best Ollama Models (July 2026)](https://benchlm.ai/best/ollama-models)
- [llama.cpp: performant local MoE CPU inference with GPU acceleration](https://huggingface.co/blog/Doctor-Shotgun/llamacpp-moe-offload-guide) · [guide: running gpt-oss with llama.cpp](https://github.com/ggml-org/llama.cpp/discussions/15396)
- [numind/NuExtract-2.0-8B](https://huggingface.co/numind/NuExtract-2.0-8B) · [NuExtract Platform](https://numind.ai/blog/nuextract-platform-the-new-information-extraction)

**Donanım ve maliyet**
- [RTX 5090 vs RTX 4090 for AI: 60-80% Faster, 32GB vs 24GB (2026)](https://localaimaster.com/blog/rtx-5090-vs-4090-ai-benchmark) · [Best GPU for Local LLMs 2026](https://www.quantizelab.dev/articles/best-gpu-for-local-llms-2026-guide)
- [Runpod GPU Cloud Pricing](https://www.runpod.io/pricing) · [Vast.ai GPU Pricing](https://vast.ai/pricing)
- [Lenovo LOQ 15APH8 (82XT) ürün sayfası](https://www.lenovo.com/us/en/p/laptops/loq-laptops/lenovo-loq-15aph8/82xt001tus) · [Crucial 64GB DDR5-5600 SO-DIMM kit](https://www.crucial.com/memory/ddr5/ct2k32g56c46s5) · [Tom's Hardware fiyat notu](https://www.tomshardware.com/pc-components/ddr5/you-can-snag-this-64gb-crucial-ddr5-5600-so-dimm-kit-for-just-usd130-at-amazon)
- [Gemini API Pricing (July 2026)](https://benchlm.ai/google/api-pricing) · [Gemini 3.5 Flash vs Claude Haiku 4.5 pricing](https://evolink.ai/blog/gemini-3-5-flash-vs-claude-haiku-4-5)
