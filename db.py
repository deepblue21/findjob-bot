"""
Veritabanı katmanı — çok-profilli (her CV/kişi ayrı etiketli) iş kaydı saklama,
durum takibi, tarama geçmişi.
Thread-safe: her işlem için yeni bağlantı açar (scheduler + web aynı anda kullanır).
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from cities import city_variants
from models import Job

_DB_PATH: Path | None = None
_SOURCE_HEALTH_DEFAULTS = {
    "jobspy": "JobSpy",
    "kariyer.net": "Kariyer.net",
}
TRACKER_STATUSES = (
    "new", "saved", "applied", "screening", "interview",
    "offer", "rejected", "dismissed",
)


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
                tracker_note TEXT DEFAULT '',
                follow_up_at TEXT,
                last_action_at TEXT,
                status_changed_at TEXT DEFAULT (datetime('now','localtime')),
                applied_at  TEXT,
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

            CREATE TABLE IF NOT EXISTS source_health (
                source      TEXT PRIMARY KEY,
                status      TEXT DEFAULT 'unknown',
                message     TEXT DEFAULT '',
                checked_at  TEXT DEFAULT (datetime('now','localtime'))
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

        # Akıllı Takipçi alanları: mevcut kullanıcı verisini silmeden şemayı büyüt.
        job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        tracker_columns = {
            "tracker_note": "TEXT DEFAULT ''",
            "follow_up_at": "TEXT",
            "last_action_at": "TEXT",
            "status_changed_at": "TEXT",
            "applied_at": "TEXT",
        }
        for name, column_type in tracker_columns.items():
            if name not in job_cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {column_type}")


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
             remote_only=False, search=None, sort="score", limit=200,
             city=None, work_mode=None, days=None, offset=0) -> list[dict]:
    query = "SELECT * FROM jobs WHERE score >= ?"
    params: list = [min_score]
    remote_sql = ("(is_remote = 1 OR LOWER(COALESCE(location,'')) LIKE '%uzaktan%' "
                  "OR LOWER(COALESCE(location,'')) LIKE '%remote%' "
                  "OR LOWER(COALESCE(job_type,'')) LIKE '%remote%')")
    hybrid_sql = ("(LOWER(COALESCE(location,'')) LIKE '%hibrit%' "
                  "OR LOWER(COALESCE(location,'')) LIKE '%hybrid%' "
                  "OR LOWER(COALESCE(job_type,'')) LIKE '%hybrid%')")

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
        query += f" AND {remote_sql}"
    if city and city != "all":
        variants = city_variants(str(city))
        if variants:
            query += " AND (" + " OR ".join("location LIKE ?" for _ in variants) + ")"
            params.extend([f"%{v}%" for v in variants])
    if work_mode and work_mode != "all":
        if work_mode == "remote":
            query += f" AND {remote_sql}"
        elif work_mode == "hybrid":
            query += f" AND {hybrid_sql}"
        elif work_mode == "onsite":
            query += f" AND NOT {remote_sql} AND NOT {hybrid_sql}"
    if days and str(days) != "all":
        try:
            n_days = int(days)
        except (TypeError, ValueError):
            n_days = 0
        if n_days > 0:
            query += " AND found_at >= datetime('now','localtime', ?)"
            params.append(f"-{n_days} days")
    if search:
        query += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        like = f"%{search.lower()}%"
        params.extend([like, like])

    order = {
        "score": "score DESC, found_at DESC",
        "date": "found_at DESC",
        "company": "company ASC",
    }.get(sort, "score DESC")
    query += f" ORDER BY {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset or 0])

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
    applied_sql = ", applied_at = COALESCE(applied_at, datetime('now','localtime'))" if status == "applied" else ""
    with get_conn() as conn:
        if profile:
            conn.execute(
                "UPDATE jobs SET status = ?, "
                "status_changed_at = datetime('now','localtime'), "
                "last_action_at = datetime('now','localtime')"
                f"{applied_sql} WHERE url_hash = ? AND profile = ?",
                (status, url_hash, profile),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = ?, "
                "status_changed_at = datetime('now','localtime'), "
                "last_action_at = datetime('now','localtime')"
                f"{applied_sql} WHERE url_hash = ?", (status, url_hash)
            )


def update_tracker(url_hash: str, profile: str = "", *, status: str | None = None,
                   follow_up_at: str | None = None, note: str | None = None) -> dict | None:
    """Başvuru aşaması, takip tarihi ve kullanıcı notunu tek işlemde güncelle."""
    fields: list[str] = []
    params: list = []
    if status is not None:
        fields.extend([
            "status = ?",
            "status_changed_at = datetime('now','localtime')",
        ])
        params.append(status)
        if status == "applied":
            fields.append("applied_at = COALESCE(applied_at, datetime('now','localtime'))")
    if follow_up_at is not None:
        fields.append("follow_up_at = ?")
        params.append(follow_up_at.strip() or None)
    if note is not None:
        fields.append("tracker_note = ?")
        params.append(note.strip()[:2000])
    if not fields:
        return get_job(url_hash, profile=profile)

    fields.append("last_action_at = datetime('now','localtime')")
    where = "url_hash = ?"
    params.append(url_hash)
    if profile:
        where += " AND profile = ?"
        params.append(profile)
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE {where}", params)
    return get_job(url_hash, profile=profile)


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
            "screening": by_status.get("screening", 0),
            "interview": by_status.get("interview", 0),
            "offer": by_status.get("offer", 0),
            "rejected": by_status.get("rejected", 0),
            "dismissed": by_status.get("dismissed", 0),
            "by_status": by_status,
            "by_source": {r["source"]: r["c"] for r in sources},
            "last_scan": dict(last_scan) if last_scan else None,
        }


# -- Kaynak sagligi ------------------------------------------------------------

def set_source_health(source: str, status: str, message: str = "", touch: bool = True) -> None:
    source = (source or "").strip().lower()
    if not source:
        return
    if status not in {"ok", "blocked", "error", "unknown"}:
        status = "unknown"
    message = (message or "").strip()[:260]
    sql = """
        INSERT INTO source_health (source, status, message, checked_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(source) DO UPDATE SET
            status = excluded.status,
            message = excluded.message,
            checked_at = excluded.checked_at
    """
    if not touch:
        sql = """
            INSERT INTO source_health (source, status, message, checked_at)
            VALUES (?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(source) DO UPDATE SET
                status = excluded.status,
                message = excluded.message
        """
    with get_conn() as conn:
        conn.execute(sql, (source[:80], status, message))


def get_source_health() -> list[dict]:
    with get_conn() as conn:
        rows = {
            r["source"]: dict(r)
            for r in conn.execute(
                "SELECT source, status, message, checked_at FROM source_health"
            ).fetchall()
        }

    out = []
    for source, label in _SOURCE_HEALTH_DEFAULTS.items():
        item = rows.pop(source, None) or {
            "source": source,
            "status": "unknown",
            "message": "Henuz taranmadi",
            "checked_at": None,
        }
        item["label"] = label
        out.append(item)

    for source in sorted(rows):
        item = rows[source]
        item["label"] = source
        out.append(item)
    return out


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
