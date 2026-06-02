"""JobSpy adaptoru — LinkedIn / Indeed / Google paralel tarama."""
import logging
import time
import random
from datetime import datetime
from models import Job

logger = logging.getLogger(__name__)


def _to_job(row: dict) -> Job | None:
    url = str(row.get("job_url") or row.get("job_url_direct") or "")
    if not url or url == "nan":
        return None

    salary_min = salary_max = None
    currency = str(row.get("currency") or "USD")
    if currency == "nan":
        currency = "USD"
    try:
        mn = row.get("min_amount"); mx = row.get("max_amount")
        salary_min = float(mn) if mn and str(mn) != "nan" else None
        salary_max = float(mx) if mx and str(mx) != "nan" else None
        interval = str(row.get("interval", "")).lower()
        # JobSpy enforce_annual_salary=True kullaniyoruz, yine de guvenlik icin:
        if interval == "hourly" and salary_min:
            salary_min *= 2080; salary_max = salary_max * 2080 if salary_max else None
        elif interval == "monthly" and salary_min:
            salary_min *= 12; salary_max = salary_max * 12 if salary_max else None
    except Exception:
        pass

    location = str(row.get("location") or "")
    if location == "nan":
        location = ""

    # JobSpy'nin native is_remote alanini kullan
    native_remote = row.get("is_remote")
    is_remote = bool(native_remote) if native_remote not in (None, "nan") else \
        ("remote" in location.lower())

    job_type_raw = str(row.get("job_type") or "").lower()
    job_type = None
    if "remote" in job_type_raw:
        job_type = "remote"; is_remote = True
    elif "hybrid" in job_type_raw:
        job_type = "hybrid"
    elif "fulltime" in job_type_raw or "full-time" in job_type_raw:
        job_type = "onsite" if not is_remote else "remote"

    posted_at = None
    dv = row.get("date_posted")
    if dv and str(dv) not in ("nan", "NaT"):
        try:
            posted_at = dv.to_pydatetime() if hasattr(dv, "to_pydatetime") \
                else datetime.fromisoformat(str(dv))
        except Exception:
            pass

    return Job(
        title=str(row.get("title") or ""),
        company=str(row.get("company") or ""),
        location=location,
        url=url,
        source=str(row.get("site") or "jobspy"),
        description=str(row.get("description") or "")[:500],
        job_type=job_type,
        salary_min=salary_min, salary_max=salary_max, currency=currency,
        posted_at=posted_at, is_remote=is_remote,
    )


def scrape_jobspy(queries: list[dict], hours_old: int, results_wanted: int) -> list[Job]:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("python-jobspy kurulu degil: pip install python-jobspy")
        return []

    all_jobs: list[Job] = []
    seen: set[str] = set()

    for q in queries:
        term = q["term"]
        sites = q.get("sites", ["indeed", "google"])
        location = q.get("location", "Turkey")
        country = q.get("country_indeed", "Turkey")   # FIX: Indeed/Glassdoor icin sart

        # FIX: Google Jobs ozel syntax ister
        google_term = q.get("google_search_term") or \
            f"{term} jobs near {location}".strip()

        logger.info(f"[JobSpy] '{term}' @ {location} (indeed={country}) -> {sites}")
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=term,
                google_search_term=google_term,
                location=location,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=country,
                enforce_annual_salary=True,
                linkedin_fetch_description=False,
                verbose=0,
            )
            if df is None or df.empty:
                logger.info(f"[JobSpy] '{term}': sonuc yok.")
            else:
                cnt = 0
                for _, row in df.iterrows():
                    job = _to_job(row.to_dict())
                    if job and job.url not in seen:
                        seen.add(job.url); all_jobs.append(job); cnt += 1
                logger.info(f"[JobSpy] '{term}': {cnt} ilan.")
        except Exception as e:
            logger.warning(f"[JobSpy] '{term}' hata: {e}")

        time.sleep(random.uniform(4, 9))  # LinkedIn rate limit korumasi

    return all_jobs
