"""CV PDF metninden is arama onerileri uretir."""
from __future__ import annotations

import re
from pathlib import Path

from cities import TURKISH_CITIES, city_variants, tr_low


MAX_PREVIEW_CHARS = 1200

SKILL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Selenium", ("selenium",)),
    ("Postman", ("postman",)),
    ("SQL", ("sql", "t-sql", "pl/sql")),
    ("Python", ("python",)),
    ("FastAPI", ("fastapi",)),
    ("Django", ("django",)),
    ("Flask", ("flask",)),
    ("JavaScript", ("javascript", "js")),
    ("TypeScript", ("typescript", "ts")),
    ("React", ("react", "react.js", "reactjs")),
    ("Node.js", ("node.js", "nodejs", "node ")),
    ("HTML", ("html",)),
    ("CSS", ("css",)),
    ("API Test", ("api test", "rest api", "soap", "api testing")),
    ("Jira", ("jira",)),
    ("Git", ("git", "github", "gitlab")),
    ("Docker", ("docker",)),
    ("Linux", ("linux",)),
    ("AWS", ("aws", "amazon web services")),
    ("Azure", ("azure",)),
    ("C#", ("c#", "csharp")),
    (".NET", (".net", "asp.net")),
    ("Java", ("java",)),
    ("Excel", ("excel", "ileri excel")),
    ("Power BI", ("power bi", "powerbi")),
    ("Tableau", ("tableau",)),
    ("SAP", ("sap",)),
    ("ERP", ("erp",)),
    ("Logo", ("logo", "logo tiger")),
    ("Mikro", ("mikro",)),
    ("Muhasebe", ("muhasebe", "accounting")),
    ("Satın Alma", ("satın alma", "satinalma", "purchasing", "procurement")),
    ("İdari İşler", ("idari işler", "idari isler", "administrative")),
)

TITLE_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "QA Test Mühendisi",
        ("qa", "test mühendisi", "test muhendisi", "software tester", "selenium", "postman"),
        ("QA Test Mühendisi", "Yazılım Test Uzmanı", "Software Test Engineer"),
    ),
    (
        "Yazılım Test Uzmanı",
        ("yazılım test", "yazilim test", "test uzmanı", "test uzmani", "api test"),
        ("Yazılım Test Uzmanı", "Manuel Test Uzmanı", "Test Analyst"),
    ),
    (
        "Python Developer",
        ("python", "django", "flask", "fastapi"),
        ("Python Developer", "Backend Developer", "Python Yazılım Geliştirici"),
    ),
    (
        "Frontend Developer",
        ("frontend", "front-end", "react", "javascript", "typescript", "html", "css"),
        ("Frontend Developer", "React Developer", "Web Arayüz Geliştirici"),
    ),
    (
        "Backend Developer",
        ("backend", "back-end", "node.js", "nodejs", ".net", "spring boot", "java developer"),
        ("Backend Developer", "API Developer", "Yazılım Geliştirici"),
    ),
    (
        "Veri Analisti",
        ("veri analisti", "data analyst", "power bi", "tableau", "raporlama", "business intelligence"),
        ("Veri Analisti", "Business Intelligence Analyst", "Raporlama Uzmanı"),
    ),
    (
        "Satın Alma Uzmanı",
        ("satın alma", "satinalma", "procurement", "purchasing", "tedarik"),
        ("Satın Alma Uzmanı", "Procurement Specialist", "Tedarik Uzmanı"),
    ),
    (
        "İdari İşler Uzmanı",
        ("idari işler", "idari isler", "ofis yönetimi", "office management"),
        ("İdari İşler Uzmanı", "Ofis Yöneticisi", "Administrative Specialist"),
    ),
    (
        "Muhasebe Uzmanı",
        ("muhasebe", "accounting", "fatura", "beyanname", "tek düzen"),
        ("Muhasebe Uzmanı", "Finans Uzmanı", "Accounting Specialist"),
    ),
)

WORK_MODE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("uzaktan", ("uzaktan", "remote", "home office")),
    ("hibrit", ("hibrit", "hybrid")),
    ("yerinde", ("yerinde", "ofisten", "onsite", "on-site")),
)


def _unique(values: list[str], limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = tr_low(value).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(value)
        if len(out) >= limit:
            break
    return out


def _contains(text_norm: str, needles: tuple[str, ...]) -> bool:
    return any(tr_low(needle) in text_norm for needle in needles if needle)


def _clean_preview(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:MAX_PREVIEW_CHARS]


def extract_pdf_text(path: Path, max_pages: int = 8) -> str:
    """PDF text extraction is best-effort; scanned PDFs can still be empty."""
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(str(path))
        pages = list(reader.pages[:max_pages])
        return "\n".join((page.extract_text() or "") for page in pages).strip()
    except Exception:
        return ""


def suggest_profile_from_text(text: str) -> dict:
    text = text or ""
    norm = tr_low(text)

    skills = [
        label
        for label, needles in SKILL_KEYWORDS
        if _contains(norm, needles)
    ]
    locations = [
        city
        for city in TURKISH_CITIES
        if any(tr_low(variant) in norm for variant in city_variants(city))
    ]
    work_modes = [
        label
        for label, needles in WORK_MODE_KEYWORDS
        if _contains(norm, needles)
    ]

    titles: list[str] = []
    search_terms: list[str] = []
    for title, triggers, terms in TITLE_RULES:
        if _contains(norm, triggers):
            titles.append(title)
            search_terms.extend(terms)

    if not search_terms and skills:
        search_terms.extend(skills[:4])

    return {
        "text_chars": len(text),
        "suggestions": {
            "skills": _unique(skills, limit=14),
            "titles": _unique(titles, limit=8),
            "locations": _unique(locations, limit=8),
            "work_modes": _unique(work_modes, limit=4),
            "search_terms": _unique(search_terms, limit=10),
        },
    }


def analyze_resume_pdf(path: Path) -> dict:
    text = extract_pdf_text(path)
    result = suggest_profile_from_text(text)
    result.update(
        {
            "status": "ok" if text else "needs_text",
            "preview": _clean_preview(text),
        }
    )
    return result
