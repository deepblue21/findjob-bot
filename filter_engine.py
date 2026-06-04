from models import Job


def tr_norm(s: str) -> str:
    """Türkçe-güvenli normalize: İ/I/ı -> i, sonra lower().
    Böylece 'İdari İşler' başlığı 'idari işler' keyword'üyle eşleşir."""
    s = s or ""
    s = s.replace("İ", "i").replace("I", "i").replace("ı", "i")
    return s.lower()


def score_job(job: Job, scoring_weights: dict) -> float:
    """İlan başlığı + açıklaması + konumuna göre puan (Türkçe-güvenli)."""
    text = tr_norm(" ".join([job.title or "", job.description or "", job.location or ""]))
    total = 0.0
    # uzun keyword'ler önce (greedy)
    for keyword, weight in sorted(scoring_weights.items(), key=lambda x: -len(str(x[0]))):
        if tr_norm(str(keyword)) in text:
            total += weight
    # remote bonus
    if job.is_remote or "uzaktan" in text or "remote" in text:
        total += 1.0
    return round(total, 1)


def should_exclude(job: Job, exclude_keywords: list) -> bool:
    text = tr_norm(" ".join([job.title or "", job.description or ""]))
    return any(tr_norm(str(kw)) in text for kw in exclude_keywords)


def is_remote_job(job) -> bool:
    """Türkçe-güvenli: uzaktan/remote geçiyorsa True (hibrit hariç)."""
    t = tr_norm(" ".join([job.title or "", job.description or "", job.location or ""]))
    return bool(job.is_remote) or "uzaktan" in t or "remote" in t


def relevance_score(job, role_weights: dict) -> float:
    """Sadece ROL/beceri kelimelerine göre uygunluk (konum ve remote SAYILMAZ).
    Böylece sadece doğru şehirde olması bir işi 'uygun' yapmaz."""
    text = tr_norm(" ".join([job.title or "", job.description or ""]))
    total = 0.0
    for kw, w in (role_weights or {}).items():
        if tr_norm(str(kw)) in text:
            total += w
    return round(total, 1)


def location_allowed(location: str, cities: list, is_remote: bool = False) -> bool:
    """Kabul kuralı (yasak-liste mantığı):
      - Tamamen uzaktan/remote                       -> TUT
      - İzin verilen şehir (İzmir/Manisa) konumda    -> TUT
      - Açıkça BAŞKA bir büyük şehir (yerinde)        -> AT
      - Konum bilinmiyor/jenerik ("Türkiye", boş)     -> TUT (kaybetme;
        çünkü JobSpy sorgusu zaten şehir-kapsamlı)
    """
    t = tr_norm(location)
    if is_remote or "uzaktan" in t or "remote" in t:
        return True
    for c in cities or []:
        if tr_norm(c) in t:
            return True
    # İzin verilenler dışındaki belirgin şehirler -> yerinde ise ele
    OTHER_CITIES = [
        "istanbul", "ankara", "bursa", "antalya", "kocaeli", "konya", "adana",
        "gaziantep", "kayseri", "mersin", "eskisehir", "samsun", "denizli",
        "sakarya", "tekirdag", "balikesir", "trabzon", "malatya", "kahramanmaras",
        "van", "diyarbakir", "sanliurfa", "aydin", "mugla", "hatay", "ordu",
        "afyon", "isparta", "elazig", "tokat", "sivas", "corum", "yozgat",
        "zonguldak", "edirne", "canakkale", "kibris", "yurt disi",
    ]
    for o in OTHER_CITIES:
        if o in t:
            return False
    # Bilinmeyen / jenerik konum -> tut
    return True


def filter_and_score(jobs, scoring_weights, exclude_keywords, min_score=2.0):
    results = []
    for job in jobs:
        if should_exclude(job, exclude_keywords):
            continue
        job.score = score_job(job, scoring_weights)
        if job.score >= min_score:
            results.append(job)
    results.sort(key=lambda j: j.score, reverse=True)
    return results
