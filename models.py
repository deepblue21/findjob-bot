from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib
import html
import re


_EXPECTATION_HEADINGS = (
    "aranan nitelikler",
    "genel nitelikler",
    "beklentiler",
    "aranan özellikler",
    "requirements",
    "qualifications",
    "required skills",
    "must have",
)

_EXPECTATION_TERMS = (
    "deneyim",
    "tecrübe",
    "bilgi",
    "hakim",
    "mezun",
    "tercihen",
    "gerek",
    "aran",
    "beklen",
    "required",
    "requirement",
    "experience",
    "knowledge",
    "familiar",
    "degree",
    "must",
)


def _tr_norm(text: str) -> str:
    text = text or ""
    return text.replace("İ", "i").replace("I", "i").replace("ı", "i").lower()


def _plain_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\r\n\t]+", ". ", text)
    text = re.sub(r"[•●▪◦]", ". ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: max(0, limit - 1)].rsplit(" ", 1)[0].strip()
    return (cut or text[: limit - 1]).rstrip(".,;:") + "…"


def _sentence_parts(text: str) -> list[str]:
    raw_parts = re.split(r"(?<=[.!?])\s+|;\s+|\s+-\s+", text)
    parts = []
    for part in raw_parts:
        clean = part.strip(" -•●▪◦.,;")
        if len(clean) >= 3:
            parts.append(clean)
    return parts


def _strip_expectation_heading(text: str) -> str:
    return re.sub(
        r"^(?:aranan|genel)\s+nitelikler\s*:?\s*|^beklentiler\s*:?\s*|"
        r"^requirements\s*:?\s*|^qualifications\s*:?\s*|^must\s+have\s*:?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" -:;")


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    job_type: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: str = "USD"
    posted_at: Optional[datetime] = None
    score: float = 0.0
    is_remote: bool = False
    match_terms: Optional[list[str]] = None
    match_score: Optional[float] = None

    @property
    def url_hash(self) -> str:
        clean = self.url.strip().lower().split("?")[0]
        return hashlib.sha256(clean.encode()).hexdigest()[:16]

    def expectations_summary(self, max_items: int = 3, max_chars: int = 360) -> str:
        """Açıklamadan kısa, kaynakta geçen beklenti/aranan nitelik özeti çıkar."""
        text = _plain_text(self.description)
        if not text:
            return ""

        parts = _sentence_parts(text)
        if not parts:
            return _trim(text, max_chars)

        chosen: list[str] = []
        heading_idx = next(
            (
                i for i, part in enumerate(parts)
                if any(h in _tr_norm(part) for h in _EXPECTATION_HEADINGS)
            ),
            None,
        )
        if heading_idx is not None:
            chosen.extend(parts[heading_idx: heading_idx + max_items])

        if not chosen:
            chosen.extend(
                part for part in parts
                if any(term in _tr_norm(part) for term in _EXPECTATION_TERMS)
            )

        if not chosen:
            chosen = parts[:max_items]

        items: list[str] = []
        seen: set[str] = set()
        for item in chosen:
            item = _strip_expectation_heading(item)
            if not item:
                continue
            key = _tr_norm(item)
            if key in seen:
                continue
            seen.add(key)
            items.append(_trim(item, 120))
            if len(items) >= max_items:
                break

        return _trim("; ".join(items), max_chars)

    def to_telegram_message(self) -> str:
        """HTML parse_mode — Markdown'dan cok daha saglam, URL'lerde kirilmaz."""
        e = html.escape  # <, >, & kacis

        salary = ""
        if self.salary_min and self.salary_max:
            salary = f"\n💰 {self.salary_min:,.0f}–{self.salary_max:,.0f} {e(self.currency)}/yıl"
        elif self.salary_min:
            salary = f"\n💰 {self.salary_min:,.0f}+ {e(self.currency)}/yıl"

        remote = " 🌍" if self.is_remote else ""
        score = f" ⭐{self.score:.1f}" if self.score > 0 else ""
        jtype = f" [{e(self.job_type.upper())}]" if self.job_type else ""
        posted = f"\n🗓️ Yayın: {self.posted_at.strftime('%d.%m.%Y')}" if self.posted_at else ""

        match_terms = [
            str(t).strip() for t in (self.match_terms or [])
            if str(t).strip()
        ][:6]
        fit = ""
        if match_terms:
            fit_label = "Özellikle uygun" if (self.match_score or self.score) >= 5 else "Uygunluk"
            fit = f"\n🎯 {fit_label}: {e(', '.join(match_terms))}"

        expectations = self.expectations_summary()
        expectation_line = f"\n🧩 Beklentiler: {e(expectations)}" if expectations else ""

        return (
            f"<b>{e(self.title)}</b>{score}{jtype}\n"
            f"🏢 {e(self.company)}\n"
            f"📍 {e(self.location)}{remote}"
            f"{salary}\n"
            f"{posted}"
            f"{fit}"
            f"{expectation_line}\n"
            f"📂 {e(self.source)}\n"
            f'🔗 <a href="{e(self.url)}">İlana git</a>'
        )
