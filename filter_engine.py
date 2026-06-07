from cities import TURKISH_CITIES
from models import Job

_TR_ASCII = str.maketrans({
    "ç": "c", "ğ": "g", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "Ö": "o", "Ş": "s", "Ü": "u",
    "â": "a", "î": "i", "û": "u", "Â": "a", "Î": "i", "Û": "u",
})


def tr_norm(s: str) -> str:
    """Türkçe-güvenli normalize: İ/I/ı -> i, sonra lower().
    Böylece 'İdari İşler' başlığı 'idari işler' keyword'üyle eşleşir."""
    s = s or ""
    s = s.replace("İ", "i").replace("I", "i").replace("ı", "i")
    return s.lower()


def city_norm(s: str) -> str:
    """Şehir karşılaştırmaları için aksanları da kaldıran normalize."""
    return tr_norm(s).translate(_TR_ASCII)


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


def work_mode(job) -> str:
    """İlanı uzaktan/hibrit/yerinde olarak sınıflandır."""
    t = tr_norm(" ".join([job.title or "", job.description or "", job.location or "", job.job_type or ""]))
    if bool(getattr(job, "is_remote", False)) or "uzaktan" in t or "remote" in t:
        return "uzaktan"
    if "hibrit" in t or "hybrid" in t:
        return "hibrit"
    return "yerinde"


def _norm_work_mode(value: str) -> str:
    t = tr_norm(value)
    if "remote" in t or "uzaktan" in t:
        return "uzaktan"
    if "hybrid" in t or "hibrit" in t:
        return "hibrit"
    if "onsite" in t or "on-site" in t or "yerinde" in t or "is yerinde" in t or "iş yerinde" in t:
        return "yerinde"
    return t.strip()


def work_mode_allowed(job, allowed_modes: list | None) -> bool:
    modes = {_norm_work_mode(str(m)) for m in (allowed_modes or []) if str(m).strip()}
    modes.discard("")
    if not modes:
        return True
    return work_mode(job) in modes


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
      - Profilde izin verilen şehir konumda          -> TUT
      - Açıkça BAŞKA bir büyük şehir (yerinde)        -> AT
      - Konum bilinmiyor/jenerik ("Türkiye", boş)     -> TUT (kaybetme;
        çünkü JobSpy sorgusu zaten şehir-kapsamlı)
    """
    t = city_norm(location)
    if is_remote or "uzaktan" in t or "remote" in t:
        return True
    for c in cities or []:
        if city_norm(c) in t:
            return True
    # İzin verilenler dışındaki belirgin şehirler -> yerinde ise ele.
    known_cities = {city_norm(c) for c in TURKISH_CITIES}
    known_cities.update({"kibris", "yurt disi", "yurtdisi"})
    for city in known_cities:
        if city and city in t:
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
