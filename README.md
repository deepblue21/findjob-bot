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

### Telegram bilgileri
- `@BotFather` → `/newbot` → **TELEGRAM_BOT_TOKEN**
- `@userinfobot` → **TELEGRAM_CHAT_ID**
- Botun sana yazabilmesi için önce bota **/start** gönder.
- Telegram bilgileri yoksa uygulama kapanmaz; sadece bildirim göndermez.

### Kişisel Dosya Güvenliği
- Kişisel `.env`, `profiles/*.yaml`, PDF/CV dosyaları, veritabanları ve yüklemeler gitignore kapsamındadır.
- CV/PDF dosyalarını repoya commit etme. Profili `profiles/ben.yaml` içinde YAML olarak özetle.
- Paylaşılan tek profil dosyası `profiles/example.yaml` şablonudur.

---

## 🎛️ Kullanım

- Sağ üstten **kişi (isim)** seç → o profilin ilanları/istatistikleri gelir.
- **SCAN NOW** → seçili kişiyi anında tarar (config her taramada yeniden okunur, restart gerekmez).
- İlan kartında: **📝** ön yazı taslağı · **★** kuyruğa ekle · **✓** başvurdum · **✕** ele · **↗** ilana git.
- **📝** modalında: ön yazıyı düzenle/kopyala, ekran sorusu cevapları, **İlana git** ile başvur, **Başvurdum** ile işaretle.
- Filtreler: durum sekmeleri (TÜMÜ / YENİ / ★ KUYRUK / BAŞVURULDU / ELENEN), kaynak, min skor, **sadece remote**, sıralama, arama.

---

## ⚙️ Yapılandırma

**`config.yaml`** (ortak, secret içermez):
- `schedule.interval_hours` — otomatik tarama aralığı
- `schedule.min_score_to_notify` — Telegram eşiği
- `schedule.min_score_to_store` — bu skorun altı hiç kaydedilmez
- `scoring` — ortak puanlama (çalışma şekli/seviye); konum önceliği profilden gelir
- `filters.exclude_keywords` — tüm profillerde ortak eleme
- `database.path` — SQLite yolu

**`profiles/<kişi>.yaml`** (kişiye özel): kimlik, `skills`, `preferred_locations`,
`search.jobspy_queries` / `kariyer_queries`, `exclude_keywords`.
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

## 🧪 Testler

```bash
python test_dashboard_static.py  # dashboard sözleşmesi ve inline JS sözdizimi
python test_jobbot.py            # filtre, db, scanner, API, Telegram mock testleri — ağ gerektirmez
python diag.py                   # scraper'ları CANLI dener, kaç ilan bulundu/elendi raporu
```
Testler GitHub Actions ile push ve pull request'lerde otomatik koşar (`.github/workflows/tests.yml`).

## 🛡️ Bot Engeli Stratejisi

429/5xx'te exponential backoff + retry, her istekte rotating User-Agent, sorgular arası random delay, URL-hash bazlı dedup. Kariyer.net scraper'ı yapıdan bağımsızdır (`__NEXT_DATA__` JSON, bulamazsa HTML fallback).

---

## ⚠️ Sorumluluk Reddi

Bu araç kişisel veya ekip içi kullanım içindir. LinkedIn/Kariyer.net gibi sitelerin kullanım şartlarına
saygı gösterin; bot **otomatik başvuru/giriş yapmaz**. Hesap güvenliği ve başvuru kararları
kullanıcının sorumluluğundadır.

## 📄 Lisans

MIT (bkz. `LICENSE`).
