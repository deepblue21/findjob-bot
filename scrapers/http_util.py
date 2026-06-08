"""
Ortak HTTP yardımcısı — retry, exponential backoff, rotating User-Agent.
Tüm scraper'lar bunu kullanır.
"""
import requests
import time
import random
import logging

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
]


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def get_with_retry(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    max_retries: int = 3,
    base_delay: float = 2.0,
    timeout: int = 20,
    return_status: bool = False,
) -> requests.Response | None | tuple[requests.Response | None, int | None]:
    """
    GET isteği at, 429/5xx durumunda exponential backoff ile tekrar dene.
    Başarısızsa None döner.
    """
    for attempt in range(max_retries):
        try:
            # Her denemede UA döndür
            session.headers["User-Agent"] = random.choice(USER_AGENTS)
            resp = session.get(url, params=params, timeout=timeout)

            if resp.status_code == 200:
                return (resp, resp.status_code) if return_status else resp

            if resp.status_code == 429:
                wait = base_delay * (2 ** attempt) + random.uniform(1, 4)
                logger.warning(f"429 rate limit — {wait:.1f}sn bekleniyor (deneme {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                logger.warning(f"403 erişim engeli: {url}")
                return (None, resp.status_code) if return_status else None

            if 500 <= resp.status_code < 600:
                wait = base_delay * (2 ** attempt)
                logger.warning(f"Sunucu hatası {resp.status_code} — {wait:.1f}sn bekleniyor")
                time.sleep(wait)
                continue

            logger.warning(f"Beklenmeyen durum {resp.status_code}: {url}")
            return (None, resp.status_code) if return_status else None

        except requests.exceptions.Timeout:
            wait = base_delay * (2 ** attempt)
            logger.warning(f"Timeout — {wait:.1f}sn bekleniyor (deneme {attempt+1})")
            time.sleep(wait)
        except requests.exceptions.RequestException as e:
            logger.warning(f"İstek hatası: {e}")
            time.sleep(base_delay * (2 ** attempt))

    logger.error(f"{max_retries} deneme başarısız: {url}")
    return (None, None) if return_status else None


def polite_delay(min_s: float = 3.0, max_s: float = 7.0) -> None:
    """İstekler arası nazik bekleme."""
    time.sleep(random.uniform(min_s, max_s))
