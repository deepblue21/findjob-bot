"""
İlana özel başvuru materyali üretici (şablon tabanlı, çevrimdışı çalışır).
ToS güvenli: hiçbir yere otomatik GÖNDERİM yapmaz; sadece taslak üretir.
Kullanıcı dashboard'da kopyalayıp KENDİSİ başvurur.

İstersen ileride bir LLM API anahtarı ekleyerek daha kişisel metinler de üretebiliriz.
"""
from __future__ import annotations


def _clean(s) -> str:
    return (str(s).strip() if s else "").replace("\n", " ").strip()


def _top_skills(profile: dict, n: int = 6) -> list[str]:
    out = []
    for item in profile.get("skills", []) or []:
        if isinstance(item, dict):
            out.extend(str(k) for k in item.keys())
        elif item:
            out.append(str(item))
    # tekilleştir, sırayı koru
    seen, uniq = set(), []
    for s in out:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq[:n]


def _location_line(job: dict, profile: dict) -> str:
    loc = (job.get("location") or "").lower()
    remote = bool(job.get("is_remote")) or "remote" in loc or "uzaktan" in loc
    prefs = [str(p).lower() for p in (profile.get("preferred_locations") or [])]
    for p in prefs:
        if p and p in loc:
            return (f"İlanın {job.get('location')} konumu yaşadığım/çalışmak istediğim "
                    f"bölgeyle örtüşüyor; bu da benim için önemli bir avantaj.")
    if remote:
        return ("Pozisyonun uzaktan/hibrit çalışmaya uygun olması, verimli ve "
                "sonuç odaklı çalışma şeklimle birebir örtüşüyor.")
    return ""


def generate_application(job: dict, profile: dict) -> dict:
    """job (DB dict) + profile (profile.yaml) -> başvuru materyali dict."""
    name = _clean(profile.get("name")) or "Aday"
    my_title = _clean(profile.get("title")) or "Test Mühendisi"
    summary = _clean(profile.get("summary"))
    years = profile.get("years_experience")
    email = _clean(profile.get("email"))
    phone = _clean(profile.get("phone"))
    linkedin = _clean(profile.get("linkedin"))

    company = _clean(job.get("company")) or "ilgili firma"
    role = _clean(job.get("title")) or "açık pozisyon"
    skills = _top_skills(profile, 6)
    skills_str = ", ".join(skills) if skills else "yazılım test süreçleri"

    exp_line = ""
    if years:
        exp_line = f"{years} yıllık deneyimimle " if int(years) else ""

    loc_line = _location_line(job, profile)

    # ── Ön yazı ──
    paragraphs = [
        f"Sayın {company} İnsan Kaynakları Ekibi,",
        (f"{role} ilanınızı büyük ilgiyle inceledim ve pozisyonun gereksinimlerinin "
         f"profilimle güçlü şekilde örtüştüğünü gördüm. " + (summary or "")),
        (f"{exp_line}özellikle {skills_str} konularında kendimi geliştirdim. "
         f"Test senaryolarının hazırlanması, hata tespiti ve raporlanması ile "
         f"ürün kalitesinin artırılmasına katkı sağlamayı hedefliyorum."),
    ]
    if loc_line:
        paragraphs.append(loc_line)
    paragraphs.append(
        f"{company} bünyesinde bilgi ve enerjimi katma fırsatını çok değerli buluyorum. "
        f"Detayları bir görüşmede paylaşmaktan memnuniyet duyarım. İlginiz için teşekkür ederim."
    )
    sign = name
    contact_bits = " · ".join([b for b in [email, phone, linkedin] if b])
    if contact_bits:
        sign += f"\n{contact_bits}"
    paragraphs.append(f"Saygılarımla,\n{sign}")

    cover_letter = "\n\n".join(p for p in paragraphs if p)

    # ── Ekran sorusu cevap taslakları ──
    answers = [
        {
            "q": "Neden bu pozisyona başvuruyorsunuz?",
            "a": (f"{role} pozisyonu, {skills_str} alanlarındaki ilgimi ve hedefimi "
                  f"birebir karşılıyor. {company}'de kaliteye katkı sağlayarak "
                  f"kariyerimi ileri taşımak istiyorum."),
        },
        {
            "q": "Sizi neden tercih etmeliyiz / güçlü yönleriniz?",
            "a": (f"Detaycı, öğrenmeye açık ve takım uyumu yüksek bir adayım. "
                  f"{skills_str} konularında pratik yapıyorum ve test süreçlerini "
                  f"sahiplenerek sonuç üretirim."),
        },
        {
            "q": "Maaş beklentiniz nedir?",
            "a": _clean(profile.get("salary_expectation"))
                 or "Pozisyona ve sorumluluklara göre görüşmeye açığım.",
        },
        {
            "q": "Ne zaman başlayabilirsiniz?",
            "a": _clean(profile.get("availability")) or "En kısa sürede başlayabilirim.",
        },
    ]

    highlights = [
        f"Hedef unvan: {my_title}",
        f"Öne çıkan beceriler: {skills_str}",
    ]
    if job.get("location"):
        highlights.append(f"İlan konumu: {job.get('location')}")
    if job.get("score"):
        highlights.append(f"Uyum skoru: {job.get('score')}")

    return {
        "url_hash": job.get("url_hash"),
        "title": role,
        "company": company,
        "url": job.get("url"),
        "cover_letter": cover_letter,
        "answers": answers,
        "highlights": highlights,
        "note": ("Bu bir TASLAKTIR — gözden geçirip kendi cümlelerinle düzenle. "
                 "Başvuruyu ilan sayfasında kendin gönder."),
    }
