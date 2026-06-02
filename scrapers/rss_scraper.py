"""RSS/JSON feed scraper — RemoteOK, WeWorkRemotely, Jobicy vb."""
import feedparser
import logging
import time
from datetime import datetime
from models import Job
from scrapers.http_util import make_session, get_with_retry

logger = logging.getLogger(__name__)


def _parse_remoteok(url: str, keywords: list[str]) -> list[Job]:
    jobs = []
    session = make_session()
    resp = get_with_retry(session, url, timeout=15)
    if not resp:
        return jobs
    try:
        data = resp.json()
        listings = [i for i in data if isinstance(i, dict) and i.get("slug")]
        for item in listings:
            tags = [t.lower() for t in item.get("tags", [])]
            title = (item.get("position") or "").lower()
            text = title + " " + " ".join(tags)
            if keywords and not any(k.lower() in text for k in keywords):
                continue
            jobs.append(Job(
                title=item.get("position", ""),
                company=item.get("company", ""),
                location="Remote",
                url=item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('slug','')}",
                source="RemoteOK",
                description=(item.get("description") or "")[:400],
                job_type="remote", is_remote=True,
                salary_min=_num(item.get("salary_min")),
                salary_max=_num(item.get("salary_max")),
                posted_at=_epoch(item.get("date")),
            ))
    except Exception as e:
        logger.warning(f"[RSS] RemoteOK hata: {e}")
    logger.info(f"[RSS] RemoteOK: {len(jobs)} ilan.")
    return jobs


def _parse_rss(name: str, url: str, keywords: list[str]) -> list[Job]:
    jobs = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = (entry.get("title") or "").lower()
            summary = (entry.get("summary") or entry.get("description") or "").lower()
            text = title + " " + summary
            if keywords and not any(k.lower() in text for k in keywords):
                continue
            link = entry.get("link") or entry.get("id") or ""
            if not link:
                continue
            published = None
            if getattr(entry, "published_parsed", None):
                try:
                    published = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                except Exception:
                    pass
            jobs.append(Job(
                title=entry.get("title", "").strip(),
                company=_company(entry),
                location="Remote",
                url=link, source=name,
                description=summary[:400],
                job_type="remote", is_remote=True,
                posted_at=published,
            ))
    except Exception as e:
        logger.warning(f"[RSS] {name} hata: {e}")
    logger.info(f"[RSS] {name}: {len(jobs)} ilan.")
    return jobs


def scrape_rss_feeds(feeds: list[dict]) -> list[Job]:
    out = []
    for f in feeds:
        if f.get("type") == "json" and "remoteok" in f["url"]:
            out.extend(_parse_remoteok(f["url"], f.get("keywords", [])))
        else:
            out.extend(_parse_rss(f["name"], f["url"], f.get("keywords", [])))
    return out


def _company(entry):
    val = entry.get("author")
    if isinstance(val, str) and val:
        return val
    d = entry.get("author_detail")
    if isinstance(d, dict):
        return d.get("name", "")
    return ""


def _num(v):
    try:
        return float(v) if v else None
    except (ValueError, TypeError):
        return None


def _epoch(v):
    try:
        from datetime import timezone
        return datetime.fromtimestamp(int(v), tz=timezone.utc).replace(tzinfo=None) if v else None
    except Exception:
        return None
