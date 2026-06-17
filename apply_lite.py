"""Onayli basvuru asistani.

Bu modul platformlarda botla form gondermez. Sadece uygun ilanlari basvuru
kuyruguna aday yapar, acik e-posta varsa kullanicinin onaylayacagi bir taslak
hazirlar ve riskli platform otomasyonlarini kapali tutar.
"""
from __future__ import annotations

import re
from urllib.parse import quote


DEFAULT_POLICY = {
    "enabled": True,
    "min_score": 7.0,
    "daily_limit": 3,
    "allowed_methods": ["email"],
    "require_approval": True,
    "blocked_platform_sources": ["linkedin", "indeed", "kariyer.net"],
}

_EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)


def apply_policy(config: dict | None, profile: dict | None = None) -> dict:
    """Ortak config ve profil ozel ayarlarini tek policy sozlugune indirger."""
    policy = dict(DEFAULT_POLICY)
    for source in ((config or {}).get("auto_apply"), (profile or {}).get("auto_apply")):
        if isinstance(source, dict):
            policy.update({k: v for k, v in source.items() if v is not None})

    try:
        policy["min_score"] = float(policy.get("min_score", DEFAULT_POLICY["min_score"]))
    except (TypeError, ValueError):
        policy["min_score"] = DEFAULT_POLICY["min_score"]
    try:
        policy["daily_limit"] = max(1, int(policy.get("daily_limit", DEFAULT_POLICY["daily_limit"])))
    except (TypeError, ValueError):
        policy["daily_limit"] = DEFAULT_POLICY["daily_limit"]

    policy["allowed_methods"] = [
        str(x).strip().lower()
        for x in (policy.get("allowed_methods") or [])
        if str(x).strip()
    ]
    policy["blocked_platform_sources"] = [
        str(x).strip().lower()
        for x in (policy.get("blocked_platform_sources") or [])
        if str(x).strip()
    ]
    policy["enabled"] = bool(policy.get("enabled", True))
    policy["require_approval"] = bool(policy.get("require_approval", True))
    return policy


def extract_contact_emails(text: str) -> list[str]:
    """Ilan metnindeki tekil e-posta adreslerini sirayi koruyarak dondurur."""
    seen: set[str] = set()
    emails: list[str] = []
    for match in _EMAIL_RE.findall(text or ""):
        email = match.strip().strip(".,;:()[]<>").lower()
        if email and email not in seen:
            seen.add(email)
            emails.append(email)
    return emails


def _job_text(job: dict) -> str:
    return " ".join(
        str(job.get(k) or "")
        for k in ("title", "company", "location", "description", "url")
    )


def _mailto(email: str, subject: str, body: str) -> str:
    return f"mailto:{quote(email)}?subject={quote(subject)}&body={quote(body)}"


def build_apply_plan(
    job: dict,
    profile: dict | None,
    policy: dict | None = None,
    application: dict | None = None,
) -> dict:
    """Tek ilan icin guvenli basvuru plani uretir."""
    policy = policy or dict(DEFAULT_POLICY)
    score = float(job.get("score") or 0)
    status = str(job.get("status") or "new")
    source = str(job.get("source") or "").strip().lower()
    allowed_methods = set(policy.get("allowed_methods") or [])
    blocked_sources = set(policy.get("blocked_platform_sources") or [])
    emails = extract_contact_emails(_job_text(job))
    email = emails[0] if emails else ""

    candidate = (
        bool(policy.get("enabled", True))
        and score >= float(policy.get("min_score", 7.0))
        and status not in {"applied", "dismissed"}
    )

    warnings: list[str] = []
    method = "manual"
    ready = False
    reason = "Açık e-posta veya tek adımlı direct apply kanalı bulunamadı."
    action_label = "İlana git"
    mailto_url = ""

    if email:
        method = "email"
        action_label = "E-posta taslağı"
        if "email" in allowed_methods:
            ready = candidate
            reason = (
                "İlan metninde açık e-posta bulundu; taslak hazırlanır, gönderim "
                "kullanıcı onayıyla yapılır."
            )
            warnings.append("CV eki mailto ile otomatik eklenmez; göndermeden önce CV'yi elle ekle.")
        else:
            reason = "E-posta yöntemi policy içinde kapalı."
    elif source in blocked_sources:
        method = "blocked_platform"
        reason = (
            "Bu kaynakta platform üzerinden otomatik başvuru kapalı; hesap ve kullanım "
            "şartları riski nedeniyle yalnızca manuel başvuru önerilir."
        )
        warnings.append("Botla form doldurma veya submit işlemi yapılmaz.")
    else:
        method = "direct_review"
        reason = (
            "Kaynak şirket/harici sayfa olabilir; önce kullanıcı incelemesi gerekir, "
            "otomatik submit yapılmaz."
        )

    if email and application:
        profile_name = str((profile or {}).get("name") or "").strip()
        title = str(job.get("title") or application.get("title") or "Açık Pozisyon").strip()
        subject = f"{title} Başvurusu"
        if profile_name:
            subject += f" - {profile_name}"
        body = (
            str(application.get("cover_letter") or "").strip()
            + "\n\nCV dosyam ektedir.\n"
        ).strip()
        mailto_url = _mailto(email, subject, body)

    return {
        "candidate": candidate,
        "ready": ready,
        "method": method,
        "action_label": action_label,
        "requires_approval": bool(policy.get("require_approval", True)),
        "email": email,
        "mailto_url": mailto_url,
        "reason": reason,
        "warnings": warnings,
        "min_score": float(policy.get("min_score", 7.0)),
    }
