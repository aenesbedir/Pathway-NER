# Doccano — Başlangıç Adımları (Annotator)

Bu kısa kılavuz, doccano'yu **kurduktan sonra** kendi veri dilimini (batch) içeri
alıp işaretlemeye başlaman içindir. Kurulum bu kılavuzun kapsamı dışında — doccano
zaten kurulu ve çalışıyor varsayılıyor.

Sana iki dosya iletilecek:
1. **Batch dosyan** — ör. `pilot_1k_doccano_batch_01_5.jsonl` (200 makale abstract'ı,
   makine tarafından önceden işaretlenmiş `PATHWAY` span'leriyle).
2. **`ANNOTATION_GUIDE.md`** — hangi span'i kabul/ret/düzelteceğini anlatan kurallar.

---

## 1. Doccano'yu başlat ve giriş yap

Doccano server'ını başlat, tarayıcıdan aç: **http://localhost:8000**
Kurulumda oluşturduğun kullanıcı adı/şifre ile giriş yap.

## 2. Yeni proje oluştur

**Projects → Create Project**
- **Project type:** `Sequence Labeling` (mutlaka bu tip)
- **Name:** istediğin bir ad, ör. `pathway-batch-01`
- Diğer seçenekleri varsayılan bırak, oluştur.

> Elinde başka bir doccano projesi varsa ona **dokunma** — bu iş için mutlaka yeni,
> boş bir proje aç.

## 3. Etiketi tanımla

Proje içinde **Labels → Create Label** (veya "Add"):
- **Label name:** tam olarak `PATHWAY` (büyük harf, tek etiket).
- Renk seç, kaydet.

> Bu ad **birebir** `PATHWAY` olmalı. Batch dosyasındaki span'ler bu etikete bağlı;
> ad tutmazsa içe aktarma hata verir.

## 4. Batch dosyanı içeri al

**Dataset → Actions → Import Dataset**
- **File format:** `JSONL`
- **File:** sana verilen `..._batch_XX_5.jsonl` dosyası
- Kolon ayarlarını **varsayılan** bırak (`text` / `label`).
- İçe aktar.

Bittiğinde **200 doküman** görmelisin, çoğu üzerinde önceden işaretlenmiş span'lerle.
200'den farklı bir sayı görürsen veya hata alırsan **dur ve haber ver** — devam etme.

## 5. İşaretlemeye başla

Artık `ANNOTATION_GUIDE.md`'deki kurallara göre çalış. Her doküman için özetle:

- **Kabul et:** doğru olan span'lere dokunma.
- **Sil:** yanlış span'i kaldır (metabolit/enzim adı, hastalık adı, pathway olmayan şey).
- **Sınırı düzelt:** span eksik/fazla karakter kapsıyorsa kenarını düzelt.
- **Ekle:** makinenin **kaçırdığı** bir pathway adını metinde seçip `PATHWAY` ile etiketle.

Kararın tek ölçütü şu soru: **"bu ifade bir metabolik süreci adlandırıyor mu?"**
Ayrıntılı örnekler ve sınır durumları `ANNOTATION_GUIDE.md`'de.

> Bazı dokümanlarda hiç span olmayabilir — bu normal. Yine de oku; makine bir mention
> kaçırmışsa ekle.

Bir dokümanı bitirince doccano'daki **"Complete"** (tamamlandı) işaretini koy; böylece
nerede kaldığını takip edebilir, sonra kaldığın yerden devam edebilirsin.

## 6. Bitince dışa aktar

Batch'teki tüm dokümanları bitirdiğinde:

**Dataset → Actions → Export Dataset**
- **File format:** `JSONL`
- İnen dosyayı, hangi batch olduğu belli olacak şekilde adlandırıp geri ilet
  (ör. `batch_01_5_export.jsonl`).

Bu kadar. Sorularını `ANNOTATION_GUIDE.md`'yi kontrol ederek çöz; orada da yoksa sor.
