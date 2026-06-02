from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib
import html


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

    @property
    def url_hash(self) -> str:
        clean = self.url.strip().lower().split("?")[0]
        return hashlib.sha256(clean.encode()).hexdigest()[:16]

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

        return (
            f"<b>{e(self.title)}</b>{score}{jtype}\n"
            f"🏢 {e(self.company)}\n"
            f"📍 {e(self.location)}{remote}"
            f"{salary}\n"
            f"📂 {e(self.source)}\n"
            f'🔗 <a href="{e(self.url)}">İlana git</a>'
        )
