"""
Veritabanı katmanı — çok-profilli (her CV/kişi ayrı etiketli) iş kaydı saklama,
durum takibi, tarama geçmişi.
Thread-safe: her işlem için yeni bağlantı açar (scheduler + web aynı anda kullanır).
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from models import Job

_DB_PATH: Path | None = None


def configure(db_path: str) -> None:
    global _DB_PATH
    _DB_PATH = Path(db_path).expanduser()
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db()


@contextmanager
def get_conn():
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        # Eski şema (profile sütunu yok) -> yeniden kur. İlan verisi az olduğundan güvenli.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        if cols and "profile" not in cols:
            conn.execute("DROP TABLE IF EXISTS jobs")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                url_hash    TEXT,
                profile     TEXT DEFAULT '',
                title       TEXT,
                company     TEXT,
                location    TEXT,
                url         TEXT,
                source      TEXT,
                description TEXT,
                job_type    TEXT,
                salary_min  REAL,
                salary_max  REAL,
                currency    TEXT,
                is_remote   INTEGER DEFAULT 0,
                score       REAL DEFAULT 0,
                status      TEXT DEFAULT 'new',
                notified    INTEGER DEFAULT 0,
                found_at    TEXT DEFAULT (datetime('now','localtime')),
                posted_at   TEXT,
                PRIMARY KEY (url_hash, profile)
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                profile       TEXT DEFAULT '',
                started_at    TEXT DEFAULT (datetime('now','localtime')),
                finished_at   TEXT,
                raw_count     INTEGER DEFAULT 0,
                new_count     INTEGER DEFAULT 0,
                matched_count INTEGER DEFAULT 0,
                status        TEXT DEFAULT 'running'
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_score   ON jobs(score);
            CREATE INDEX IF NOT EXISTS idx_jobs_found   ON jobs(found_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_profile ON jobs(profile);
        """)

        # scan_log eski ise profile sütunu ekle
        sl = [r["name"] for r in conn.execute("PRAGMA table_info(scan_log)").fetchall()]
        if sl and "profile" not in sl:
            conn.execute("ALTER TABLE scan_log ADD COLUMN profile TEXT DEFAULT ''")


# -- İş kaydı işlemleri ---------------------------------------------------------

def upsert_job(job: Job, profile: str = "") -> bool:
    """İlanı ekle. Yeniyse True, varsa False. Var olanın score'u güncellenir.
    Dedup (url_hash, profile) bazlı — aynı ilan iki kişide ayrı tutulabilir."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM jobs WHERE url_hash = ? AND profile = ?",
            (job.url_hash, profile),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE jobs SET score = ? WHERE url_hash = ? AND profile = ?",
                (job.score, job.url_hash, profile),
            )
            return False

        conn.execute("""
            INSERT INTO jobs
                (url_hash, profile, title, company, location, url, source, description,
                 job_type, salary_min, salary_max, currency, is_remote, score,
                 posted_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            job.url_hash, profile, job.title, job.company, job.location, job.url,
            job.source, job.description, job.job_type, job.salary_min,
            job.salary_max, job.currency, int(job.is_remote), job.score,
            job.posted_at.isoformat() if job.posted_at else None,
        ))
        return True


def get_jobs(profile=None, status=None, source=None, min_score=0.0,
             remote_only=False, search=None, sort="score", limit=200) -> list[dict]:
    query = "SELECT * FROM jobs WHERE score >= ?"
    params: list = [min_score]

    if profile and profile != "all":
        query += " AND profile = ?"
        params.append(profile)
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    if source and source != "all":
        query += " AND source = ?"
        params.append(source)
    if remote_only:
        query += (" AND (is_remote = 1 OR LOWER(location) LIKE '%uzaktan%'"
                  " OR LOWER(location) LIKE '%remote%')")
    if search:
        query += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        like = f"%{search.lower()}%"
        params.extend([like, like])

    order = {
        "score": "score DESC, found_at DESC",
        "date": "found_at DESC",
        "company": "company ASC",
    }.get(sort, "score DESC")
    query += f" ORDER BY {order} LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_job(url_hash: str, profile: str = "") -> dict | None:
    """Tek bir ilanı (url_hash, profile) ile döndür."""
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM jobs WHERE url_hash = ? AND profile = ?",
            (url_hash, profile),
        ).fetchone()
        if not r:  # profile verilmediyse hash ile dene
            r = conn.execute(
                "SELECT * FROM jobs WHERE url_hash = ? LIMIT 1", (url_hash,)
            ).fetchone()
        return dict(r) if r else None


def delete_job(url_hash: str, profile: str = "") -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM jobs WHERE url_hash = ? AND profile = ?",
                     (url_hash, profile))


def update_status(url_hash: str, status: str, profile: str = "") -> None:
    with get_conn() as conn:
        if profile:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE url_hash = ? AND profile = ?",
                (status, url_hash, profile),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE url_hash = ?", (status, url_hash)
            )


def get_stats(profile=None) -> dict:
    where = ""
    p: list = []
    if profile and profile != "all":
        where = " WHERE profile = ?"
        p = [profile]
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT status, COUNT(*) AS c FROM jobs{where} GROUP BY status", p
        ).fetchall()
        by_status = {r["status"]: r["c"] for r in rows}

        total = conn.execute(f"SELECT COUNT(*) FROM jobs{where}", p).fetchone()[0]
        sources = conn.execute(
            f"SELECT source, COUNT(*) AS c FROM jobs{where} GROUP BY source ORDER BY c DESC", p
        ).fetchall()

        if profile and profile != "all":
            last_scan = conn.execute(
                "SELECT * FROM scan_log WHERE profile = ? ORDER BY id DESC LIMIT 1", p
            ).fetchone()
        else:
            last_scan = conn.execute(
                "SELECT * FROM scan_log ORDER BY id DESC LIMIT 1"
            ).fetchone()

        return {
            "total": total,
            "new": by_status.get("new", 0),
            "saved": by_status.get("saved", 0),
            "applied": by_status.get("applied", 0),
            "dismissed": by_status.get("dismissed", 0),
            "by_source": {r["source"]: r["c"] for r in sources},
            "last_scan": dict(last_scan) if last_scan else None,
        }


# -- Telegram bildirim takibi --------------------------------------------------

def get_unnotified(min_score: float, profile: str = "") -> list[Job]:
    with get_conn() as conn:
        if profile:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE notified = 0 AND score >= ? AND profile = ? "
                "AND status != 'dismissed' ORDER BY score DESC",
                (min_score, profile),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE notified = 0 AND score >= ? "
                "AND status != 'dismissed' ORDER BY score DESC",
                (min_score,),
            ).fetchall()

    jobs = []
    for r in rows:
        jobs.append(Job(
            title=r["title"], company=r["company"], location=r["location"],
            url=r["url"], source=r["source"], description=r["description"] or "",
            job_type=r["job_type"], salary_min=r["salary_min"],
            salary_max=r["salary_max"], currency=r["currency"] or "USD",
            is_remote=bool(r["is_remote"]), score=r["score"],
        ))
    return jobs


def mark_notified(url_hashes: list[str], profile: str = "") -> None:
    if not url_hashes:
        return
    with get_conn() as conn:
        if profile:
            conn.executemany(
                "UPDATE jobs SET notified = 1 WHERE url_hash = ? AND profile = ?",
                [(h, profile) for h in url_hashes],
            )
        else:
            conn.executemany(
                "UPDATE jobs SET notified = 1 WHERE url_hash = ?",
                [(h,) for h in url_hashes],
            )


# -- Tarama geçmişi ------------------------------------------------------------

def start_scan(profile: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scan_log (status, profile) VALUES ('running', ?)", (profile,)
        )
        return cur.lastrowid


def finish_scan(scan_id, raw, new, matched, status="done") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE scan_log SET finished_at = datetime('now','localtime'), "
            "raw_count = ?, new_count = ?, matched_count = ?, status = ? "
            "WHERE id = ?",
            (raw, new, matched, status, scan_id),
        )


def is_scan_running() -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM scan_log WHERE status = 'running' "
            "AND started_at > datetime('now','localtime','-30 minutes') LIMIT 1"
        ).fetchone()
        return row is not None
