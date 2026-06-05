"""
Kariyer.net scraper — YAPIYA BAGIMSIZ.
Yaklasim:
  1. __NEXT_DATA__ JSON'unu ozyinelemeli tara, is-ilani benzeri TUM listeleri bul
     (yol bilmeye gerek yok; pageProps.jobList.items / searchResult.jobs / ne olursa)
  2. HTML fallback: /is-ilani/ desenli linkleri topla (canli dogrulanmis URL deseni)
URL yapisi: liste -> /is-ilanlari/android+developer  |  ilan -> /is-ilani/...-{id}
"""
import json
import re
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from cities import TURKISH_CITIES, tr_low
from models import Job
from scrapers.http_util import make_session, get_with_retry, polite_delay

logger = logging.getLogger(__name__)

BASE = "https://www.kariyer.net/is-ilanlari"

# Is-ilani benzeri dict tespiti icin alan adlari
TITLE_KEYS = {"name", "title", "positionname", "jobtitle", "displayname",
              "position", "ilanbasligi", "advtitle"}
URL_KEYS   = {"url", "joburl", "link", "slug", "detailurl", "adverturl"}
ID_KEYS    = {"id", "jobid", "advid", "advertid", "ilanid", "advertno"}
COMPANY_KEYS = {"companyname", "company", "firmaadi", "corpname", "companytitle"}
CITY_KEYS  = {"cityname", "city", "sehir", "location", "il"}
WORK_KEYS  = {"worktypetext", "worktype", "calismasekli", "workingtype"}


def _build_url(query: str) -> str:
    slug = query.strip().lower().replace(" ", "+")
    return f"{BASE}/{slug}"


def _norm(d: dict) -> dict:
    """Dict anahtarlarini kucuk harfe indirgeyerek arama kolaylastir."""
    return {str(k).lower(): v for k, v in d.items()}


def _looks_like_job(d: dict) -> bool:
    """Bir dict is ilani gibi mi? title-benzeri + (url|id) sart."""
    if not isinstance(d, dict):
        return False
    low = _norm(d)
    has_title = any(k in low and isinstance(low[k], str) and low[k].strip()
                    for k in TITLE_KEYS)
    has_locator = any(k in low and low[k] not in (None, "", 0) for k in (URL_KEYS | ID_KEYS))
    return has_title and has_locator


def _walk_for_jobs(node, found: list, depth: int = 0):
    """JSON agacini ozyinelemeli tara, is-ilani listelerini topla."""
    if depth > 12:
        return
    if isinstance(node, list):
        # Bu liste cogunlukla is-ilani dict'lerinden mi olusuyor?
        job_items = [x for x in node if _looks_like_job(x)]
        if job_items and len(job_items) >= max(2, len(node) // 2):
            found.append(job_items)
        # yine de icine in (ic ice listeler olabilir)
        for x in node:
            _walk_for_jobs(x, found, depth + 1)
    elif isinstance(node, dict):
        for v in node.values():
            _walk_for_jobs(v, found, depth + 1)


def _extract_next_data(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except (json.JSONDecodeError, TypeError):
        return []

    found: list[list] = []
    _walk_for_jobs(data, found)
    if not found:
        return []
    # En buyuk liste muhtemelen ana arama sonucudur
    best = max(found, key=len)
    logger.debug(f"[Kariyer] __NEXT_DATA__ icinde {len(best)} is-benzeri obje bulundu.")
    return best


def _tr_low(s: str) -> str:
    """Türkçe-güvenli küçük harf (İ/I/ı -> i)."""
    return tr_low(s)


def _clean_kariyer_title(text: str) -> str:
    """Kariyer anchor metnini temizle: 'Sponsorlu İlan' on ekini ve sehir/calisma-sekli/
    tarih kuyrugunu at, makul bir baslik birak."""
    t = re.sub(r"^\s*Sponsorlu İlan\s*", "", text, flags=re.IGNORECASE)
    # calisma sekli / tip / tarih isaretlerinden once kes
    t = re.split(r"\s+(?:İş Yerinde|Uzaktan|Hibrit|Remote|Tam zamanlı|Yarı zamanlı|"
                 r"Dönemsel|Serbest|Ort\.|update|\d+\s*gün)\b", t, maxsplit=1)[0]
    return t.strip(" -|·")


def _loc_from_text(text: str) -> tuple[str, str]:
    """İlan metninden şehir + çalışma şekli çıkar."""
    t = _tr_low(text)
    work = ""
    if "uzaktan" in t or "remote" in t:
        work = "Uzaktan / Remote"
    elif "hibrit" in t:
        work = "Hibrit"
    elif "is yerinde" in t or "iş yerinde" in t:
        work = "İş Yerinde"
    city = ""
    for disp in TURKISH_CITIES:
        if _tr_low(disp) in t:
            city = disp
            break
    return city, work


def _fallback_html(html: str) -> list[dict]:
    """/is-ilani/ desenli linkleri dogrudan HTML'den topla (sehir + calisma sekli ile)."""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/is-ilani/" not in href:
            continue
        if not href.startswith("http"):
            href = "https://www.kariyer.net" + href
        href = href.split("?")[0]
        if href in seen:
            continue
        seen.add(href)
        raw = a.get_text(" ", strip=True)
        if "sponsorlu" in _tr_low(raw):
            continue  # Sponsorlu İlan reklamlarini atla (alakasiz, her sayfada cikar)
        city, work = _loc_from_text(raw)
        text = _clean_kariyer_title(raw)
        if not text or len(text) < 3:
            m = re.search(r"/is-ilani/(.+)-\d+$", href)
            text = m.group(1).replace("-", " ").title() if m else "İlan"
        item = {"name": text, "url": href}
        if city:
            item["cityname"] = city
        if work:
            item["worktypetext"] = work
        results.append(item)
    return results


def _to_job(item: dict) -> Job | None:
    if not isinstance(item, dict):
        return None
    low = _norm(item)

    def first(keys):
        for k in keys:
            v = low.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, (int, float)) and v:
                return str(v)
            if isinstance(v, dict):  # location: {cityName: ...}
                inner = _norm(v)
                for ik in CITY_KEYS:
                    if isinstance(inner.get(ik), str) and inner[ik].strip():
                        return inner[ik].strip()
        return None

    title = first(TITLE_KEYS) or ""
    if not title:
        return None

    # URL cozumle
    url = first(URL_KEYS)
    if url and not url.startswith("http"):
        url = "https://www.kariyer.net" + (url if url.startswith("/") else "/" + url)
    if not url:
        jid = first(ID_KEYS)
        if jid:
            url = f"https://www.kariyer.net/is-ilani/{jid}"
    if not url:
        return None

    company = first(COMPANY_KEYS) or ""
    city = first(CITY_KEYS) or ""
    work = (first(WORK_KEYS) or "").lower()
    is_remote = "uzaktan" in work or "remote" in work
    job_type = "remote" if is_remote else ("hybrid" if "hibrit" in work else None)

    return Job(
        title=title, company=company,
        location=city or ("Uzaktan" if is_remote else "Türkiye"),
        url=url.split("?")[0], source="kariyer.net",
        description="", job_type=job_type, currency="TRY",
        is_remote=is_remote, posted_at=datetime.now(),
    )


def scrape_kariyer(queries: list[str]) -> list[Job]:
    session = make_session()
    all_jobs: list[Job] = []
    seen: set[str] = set()

    for query in queries:
        url = _build_url(query)
        logger.info(f"[Kariyer] '{query}' -> {url}")
        resp = get_with_retry(session, url, max_retries=3, base_delay=3.0)
        if not resp:
            logger.warning(f"[Kariyer] '{query}' alinamadi.")
            polite_delay(5, 9)
            continue

        nd_items = _extract_next_data(resp.text)
        if nd_items:
            items, method = nd_items, "__NEXT_DATA__"
        else:
            items, method = _fallback_html(resp.text), "HTML-fallback"

        found = 0
        for it in items:
            job = _to_job(it)
            if job and job.url not in seen:
                seen.add(job.url); all_jobs.append(job); found += 1
        logger.info(f"[Kariyer] '{query}': {found} ilan ({method}).")
        polite_delay(5, 10)

    return all_jobs
