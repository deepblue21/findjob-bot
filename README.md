# 🤖 JOB_BOT — Çok Profilli İş Arama Botu + Dashboard

Birden fazla kişi/profil için **Türkiye bazlı** iş ilanlarını otomatik tarayan, becerilere göre
puanlayan, isteğe bağlı olarak **Telegram'a bildiren** ve terminal temalı bir **web dashboard**'da yöneten açık kaynak araç.

Kaynaklar: **Kariyer.net · Indeed · Google Jobs · LinkedIn** (uluslararası remote feed'ler opsiyonel/kapalı).

> Bot otomatik **başvuru yapmaz** — yalnızca ilan bulur, puanlar,
> bildirir ve sana özel ön yazı/başvuru taslağı hazırlar. Son "gönder" adımını sen yaparsın.

---

## ✨ Özellikler

- **Çok profilli:** her kişi için ayrı `profiles/*.yaml` — kendi arama terimleri, becerileri, konumları. Dashboard'dan **isimle seçim**.
- **Profile göre puanlama:** profildeki beceriler puanlamaya otomatik eklenir; ilanlar gerçek uyuma göre sıralanır.
- **Konum filtresi:** profilinde izin verdiğin şehirler (ör. İstanbul/Ankara, yerinde+hibrit) **veya** tamamen uzaktan; diğer şehirlerin yerinde ilanları elenir.
- **Türkçe-güvenli eşleştirme:** "İdari İşler" gibi başlıklar büyük İ harfine takılmadan doğru puanlanır.
- **Başvuru kuyruğu + ön yazı taslağı:** her ilana özel ön yazı, ekran sorusu cevapları ve öne çıkan beceriler; kopyala → kendin başvur.
- **Telegram:** ayarlanırsa eşleşen ilanları kişi adıyla bildirir; ayarlanmazsa dashboard çalışmaya devam eder.
- **Dedup:** aynı ilan iki kez bildirilmez. **Otomatik tarama:** her N saatte tüm profiller.
- **Dashboard:** skor rozetleri, çalışma şekli (uzaktan/hibrit/yerinde) rozetleri, kaynak/skor/remote filtreleri, durum sekmeleri, anlık SCAN NOW.
- **Kaynak sağlığı:** JobSpy / Kariyer.net durumunu gösterir; erişim engeli varsa tarama devam eder ve kaynak daha seyrek yeniden denenir.

---

## 🏗️ Mimari

```
run.py                  → tek process: FastAPI web + APScheduler zamanlayıcı
├── scanner.py          → çekirdek tarama (profil başına); .env + config yükler
├── profiles.py         → profiles/*.yaml yükleyici + beceri→puan
├── filter_engine.py    → Türkçe-güvenli puanlama, konum & remote filtresi, exclude
├── cover_letter.py     → ilana özel ön yazı / başvuru cevabı taslağı (şablon, çevrimdışı)
├── notifier.py         → Telegram (ilan bildirimi + özet rapor)
├── db.py               → SQLite (profil etiketli ilan kaydı, durum, tarama geçmişi)
├── scrapers/
│   ├── jobspy_scraper.py   → Indeed / Google / LinkedIn (JobSpy)
│   ├── kariyer_scraper.py  → Kariyer.net (__NEXT_DATA__ JSON + HTML fallback)
│   └── rss_scraper.py      → RemoteOK / WWR / Jobicy (opsiyonel)
├── web/
│   ├── app.py              → JSON API uçları
│   └── static/index.html   → dashboard
├── config.yaml         → ortak ayarlar (secret İÇERMEZ — ${ENV} kullanır)
├── .env                → secret'lar (git'e GİRMEZ)
└── profiles/*.yaml     → kişisel profiller (git'e GİRMEZ)
```

---

## 🚀 Kurulum

> Windows'ta **WSL2 (Ubuntu)** önerilir. Python 3.10-3.12 gerekir.

```bash
# 1) Repoyu klonla
git clone -b codex/public-share https://github.com/deepblue21/findjob-bot.git
cd findjob-bot

# 2) Sanal ortam + bağımlılıklar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) Secret'ları ayarla (Telegram bildirimi istiyorsan doldur)
cp .env.example .env
nano .env            # boş kalırsa dashboard çalışır, Telegram bildirimi atlanır

# 4) En az bir profil oluştur
cp profiles/example.yaml profiles/ben.yaml
nano profiles/ben.yaml   # ad, beceriler, arama terimleri, konumlar

# 5) (Önerilen) doğrula
python selftest.py

# 6) Başlat
python run.py
```

Tarayıcıda: **http://localhost:8765**

### Profil ve CV/PDF nasıl verilir?

Projeyi kullanan herkes kendi kişisel bilgisini repoya koymadan iki yerde tanımlar:

1. **Profil dosyası:** `profiles/example.yaml` dosyasını kopyalayıp kendi dosyasını oluşturur.

   ```bash
   cp profiles/example.yaml profiles/ben.yaml
   nano profiles/ben.yaml
   ```

   Bu dosyada özellikle şunlar doldurulur:
   - `key`, `name`, `title`, `email`, `location`
   - `preferred_locations` ve `work_modes`
   - `skills`
   - `search.jobspy_queries` ve gerekiyorsa `kariyer_queries`
   - `exclude_keywords`

   `profiles/*.yaml` kişisel veri sayılır ve `.gitignore` kapsamındadır; GitHub'a gönderilmez.

2. **CV/PDF dosyası:** Uygulama çalıştıktan sonra dashboard'da sağ üstten kendi profilini seçer,
   **Profil PDF kaynakları** bölümünde **PDF yükle** düğmesiyle CV veya portföy PDF'ini yükler.
   Ardından **Önerileri çıkar** düğmesi beceri, pozisyon, şehir ve arama terimi önerileri üretir.

   Yüklenen PDF'ler yerelde `uploads/resumes/<profil-key>/` altında tutulur ve repoya girmez.
   PDF başına sınır 10 MB'dir. Taranmış/görüntü tabanlı PDF'lerde metin okunamayabilir; en iyi sonuç
   seçilebilir metin içeren CV PDF'iyle alınır.

CV analizi profili otomatik değiştirmez; çıkan önerileri kontrol edip uygun olanları
`profiles/ben.yaml` içine eklemek gerekir. Değişiklikten sonra dashboard'daki **SCAN NOW**
düğmesiyle yeni filtrelerle tarama başlatılabilir.

### Telegram bilgileri
- `@BotFather` → `/newbot` → **TELEGRAM_BOT_TOKEN**
- `@userinfobot` → **TELEGRAM_CHAT_ID**
- Botun sana yazabilmesi için önce bota **/start** gönder.
- Telegram bilgileri yoksa uygulama kapanmaz; sadece bildirim göndermez.

### Dashboard şifresi (önerilir)

Tailscale kullansan bile dashboard kişisel profil ve başvuru verisi içerdiği için basit şifre
koruması açman önerilir. `.env` içine şunları ekle:

```env
DASHBOARD_USERNAME=jobbot
DASHBOARD_PASSWORD=guclu-bir-sifre-yaz
```

`DASHBOARD_PASSWORD` boşsa şifre koruması kapalı kalır. Şifreyi repoya commit etme.

### Kişisel Dosya Güvenliği
- Kişisel `.env`, `profiles/*.yaml`, PDF/CV dosyaları, veritabanları ve yüklemeler gitignore kapsamındadır.
- CV/PDF dosyalarını repoya commit etme. Profili `profiles/ben.yaml` içinde YAML olarak özetle.
- Paylaşılan tek profil dosyası `profiles/example.yaml` şablonudur.

---

## 🎛️ Kullanım

- Sağ üstten **kişi (isim)** seç → o profilin ilanları/istatistikleri gelir.
- **SCAN NOW** → seçili kişiyi anında tarar (config her taramada yeniden okunur, restart gerekmez).
- **PDF yükle** → seçili profile CV/portföy PDF'i bağlar; **Önerileri çıkar** ile beceri ve arama terimi önerilerini gösterir.
- İlan kartında: **📝** ön yazı taslağı · **★** kuyruğa ekle · **✓** başvurdum · **✕** ele · **↗** ilana git.
- **📝** modalında: ön yazıyı düzenle/kopyala, ekran sorusu cevapları, **İlana git** ile başvur, **Başvurdum** ile işaretle.
- Filtreler: durum sekmeleri (TÜMÜ / YENİ / ★ KUYRUK / BAŞVURULDU / ELENEN), kaynak, min skor, **sadece remote**, sıralama, arama.

---

## 🌐 Uzaktan Erişim (Tailscale)

Evde değilken dashboard'a telefonundan veya başka bir cihazından güvenli şekilde erişmek için
Tailscale kullanabilirsin. Bu yöntem modem port yönlendirmesi gerektirmez ve **Tailscale Funnel**
açılmadığı sürece dashboard'u herkese açık internete yayınlamaz; yalnızca aynı Tailscale hesabına
bağlı cihazlar erişebilir.

### 1) Tailscale'i kur

- Evde dashboard'u çalıştıran bilgisayara Tailscale kur ve giriş yap.
- Telefona veya dışarıdan bağlanacağın cihaza Tailscale kur.
- Tüm cihazlarda aynı Tailscale hesabıyla oturum aç.
- Telefonda Tailscale uygulamasında bilgisayarı görüyorsan bağlantı hazırdır.

### 2) Dashboard'u bilgisayarda çalıştır

```bash
python run.py
```

Bilgisayarda yerel kontrol:

```text
http://localhost:8765
```

### 3) Dashboard'u Tailscale içinde yayınla

Windows'ta PowerShell'i gerekirse yönetici olarak açıp çalıştır:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" serve --yes --bg --tcp=8765 127.0.0.1:8765
```

Tailscale IP adresini görmek için:

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" ip -4
```

### 4) Telefondan aç

Telefonda Tailscale **Connected** durumundayken tarayıcının adres çubuğuna şunu yaz:

```text
http://<TAILSCALE_IP>:8765
```

Örnek biçim: `http://100.x.y.z:8765`

> Not: Tarayıcı otomatik olarak `https://` yaparsa çalışmayabilir. Adresi özellikle `http://`
> ile yaz. Google arama kutusuna değil, tarayıcı adres çubuğuna gir.

### Yayını kapatma

```powershell
& "C:\Program Files\Tailscale\tailscale.exe" serve --tcp=8765 off
```

### Windows'ta otomatik başlatma

PC açıldığında Job Bot ve Tailscale Serve otomatik başlasın istiyorsan PowerShell'i yönetici
olarak açıp repo kökünde çalıştır:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_startup.ps1
```

Hemen denemek için:

```powershell
Start-ScheduledTask -TaskName "JobBot Dashboard"
```

Kaldırmak için:

```powershell
Unregister-ScheduledTask -TaskName "JobBot Dashboard" -Confirm:$false
```

### Güvenlik notları

- README'ye kendi Tailscale IP'ni, cihaz adını, tailnet alan adını veya kişisel profil bilgilerini yazma.
- `tailscale funnel` kullanma; Funnel dashboard'u internete açık hale getirir.
- Bilgisayar kapalıysa, Job Bot çalışmıyorsa veya telefonda Tailscale bağlı değilse uzaktan erişim çalışmaz.
- Dashboard'u başkalarıyla paylaşacaksan önce uygulamaya basit kullanıcı adı/şifre koruması eklemek iyi olur.

---

## ⚙️ Yapılandırma

**`config.yaml`** (ortak, secret içermez):
- `schedule.interval_hours` — otomatik tarama aralığı
- `schedule.min_score_to_notify` — Telegram eşiği
- `schedule.min_score_to_store` — bu skorun altı hiç kaydedilmez
- `scoring` — ortak puanlama (çalışma şekli/seviye); konum önceliği profilden gelir
- `sources.kariyer_block_cooldown_hours` — Kariyer.net 403 verirse tekrar denemeden önce beklenecek süre
- `filters.exclude_keywords` — tüm profillerde ortak eleme
- `database.path` — SQLite yolu
- `.env` içindeki `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` — opsiyonel dashboard şifresi

**`profiles/<kişi>.yaml`** (kişiye özel): kimlik, `skills`, `preferred_locations`,
`work_modes`, `search.jobspy_queries` / `kariyer_queries`, `exclude_keywords`.
Beceriler puanlamaya otomatik eklenir.

---

## 🔒 Güvenlik

- Secret'lar **`.env`** içinde; `.gitignore` ile repoya **girmez**. `config.yaml` yalnızca `${TELEGRAM_BOT_TOKEN}` gibi placeholder tutar.
- **Kişisel profiller** (`profiles/*.yaml`, PII içerir) repoya girmez — yalnızca `profiles/example.yaml` paylaşılır.
- Veritabanı (`*.db`), sanal ortam (`.venv/`) ve loglar gitignore'da.
- **Token'ın bir yerde sızdıysa** mutlaka `@BotFather` → `/revoke` ile yenile.

---

## 🧠 Filtreleme Nasıl Çalışır

Bir ilan ancak şu üç şartı geçerse kaydedilir:
1. **Eleme kelimesi** içermiyorsa (`exclude_keywords`).
2. **Rol uygunluğu** ≥ `min_relevance` — başlık/açıklama, kişinin becerilerinden **veya aradığı pozisyon terimlerinden** en az birini içermeli. (Yalnızca doğru şehirde olması yetmez.)
3. **Konum uygun** — Profilde izin verilen şehirlerden biri **veya** tamamen uzaktan; konumu bilinmeyen/jenerik ilanlar tutulur, sadece başka şehirdeki **yerinde** ilanlar elenir.

Telegram ayarlıysa yalnızca skoru `min_score_to_notify` üstü ilanlar gönderilir; dashboard tümünü gösterir.

## 🌗 Tema & Arayüz

Sağ üstteki tema menüsünde açık, koyu, siyah terminal ve renkli temalar bulunur; seçim tarayıcıda saklanır. Arayüz kart tabanlı düzen, çalışma-şekli rozetleri (uzaktan/hibrit/yerinde), skor renkleri, aktif filtre özeti ve ön yazı modalı içerir.

## Kaynak Sağlığı ve Kariyer.net 403

Kariyer.net daha önce çalışırken sonradan `403 erişim engeli` döndürmeye başlayabilir. Bu genelde botun kodunun bozulmasından değil, Kariyer.net tarafındaki koruma katmanının düz HTTP isteklerini geçici veya kalıcı olarak reddetmesinden kaynaklanır.

Bot bu durumda:
- Kariyer.net için kalan sorguları o taramada atlar.
- Aynı taramadaki diğer profillerde Kariyer.net'i yeniden zorlamaz.
- Dashboard'da Kariyer.net'i `blocked`, JobSpy'ı `ok` gibi gösterir.
- `sources.kariyer_block_cooldown_hours` süresi dolana kadar Kariyer.net'i tekrar denemez; süre dolunca yeniden dener.

Yapılabilir güvenli seçenekler:
- JobSpy kaynaklarını (Indeed / Google / LinkedIn) ana kaynak olarak kullanmak.
- Kariyer engeli geçiciyse cooldown sonrası yeniden denemek.
- Kariyer tarafı sürekli 403 veriyorsa `kariyer_queries` listesini boşaltıp o kaynağı pratikte kapatmak.
- Site girişini, captcha'yı veya koruma katmanını otomatik aşmaya çalışmamak; bu kırılgan ve kullanım şartları açısından riskli bir yoldur.

## 🧪 Testler

```bash
python test_dashboard_static.py  # dashboard sözleşmesi ve inline JS sözdizimi
python test_jobbot.py            # filtre, db, scanner, API, Telegram mock testleri — ağ gerektirmez
python diag.py                   # scraper'ları CANLI dener, kaç ilan bulundu/elendi raporu
```
Testler GitHub Actions ile push ve pull request'lerde otomatik koşar (`.github/workflows/tests.yml`).

## 🛡️ Bot Engeli Stratejisi

429/5xx'te exponential backoff + retry, her istekte rotating User-Agent, sorgular arası random delay, URL-hash bazlı dedup. Kariyer.net scraper'ı yapıdan bağımsızdır (`__NEXT_DATA__` JSON, bulamazsa HTML fallback). Kariyer.net `403` döndürürse kaynak `blocked` işaretlenir ve `sources.kariyer_block_cooldown_hours` kadar beklenir.

---

## ⚠️ Sorumluluk Reddi

Bu araç kişisel veya ekip içi kullanım içindir. LinkedIn/Kariyer.net gibi sitelerin kullanım şartlarına
saygı gösterin; bot **otomatik başvuru/giriş yapmaz**. Hesap güvenliği ve başvuru kararları
kullanıcının sorumluluğundadır.

## 📄 Lisans

MIT (bkz. `LICENSE`).
