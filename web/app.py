"""FastAPI web uygulaması — çok profilli dashboard + JSON API."""
import base64
from contextlib import asynccontextmanager
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import db
import scanner
import profiles as profiles_mod
from cities import TURKISH_CITIES
from cover_letter import generate_application
from resume_analyzer import analyze_resume_pdf

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_ROOT = Path(__file__).resolve().parents[1] / "uploads" / "resumes"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
AUTH_REALM = "JobBot"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if db._DB_PATH is None:
        cfg = scanner.load_config()
        db.configure(cfg["database"]["path"])
    yield


app = FastAPI(title="Job Bot Dashboard", lifespan=lifespan)


def _dashboard_auth_config() -> tuple[str, str]:
    env = {**scanner._load_dotenv(), **os.environ}
    username = str(env.get("DASHBOARD_USERNAME", "jobbot") or "jobbot").strip()
    password = str(env.get("DASHBOARD_PASSWORD", "") or "").strip()
    if password.startswith("${"):
        password = ""
    return username or "jobbot", password


def _valid_basic_auth(header: str | None, username: str, password: str) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        raw = base64.b64decode(header.split(" ", 1)[1], validate=True).decode("utf-8")
    except Exception:
        return False
    supplied_user, sep, supplied_pass = raw.partition(":")
    if not sep:
        return False
    return secrets.compare_digest(supplied_user, username) and secrets.compare_digest(
        supplied_pass, password
    )


@app.middleware("http")
async def require_dashboard_auth(request: Request, call_next):
    username, password = _dashboard_auth_config()
    if not password:
        return await call_next(request)
    if _valid_basic_auth(request.headers.get("authorization"), username, password):
        return await call_next(request)
    return PlainTextResponse(
        "Authentication required",
        status_code=401,
        headers={"WWW-Authenticate": f'Basic realm="{AUTH_REALM}"'},
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def _profile_keywords(p: dict) -> list:
    """Bir profilin rol/konum anahtar kelimeleri (drawer'da 'neden eşleşti')."""
    kws = []
    for s in (p.get("skills") or []):
        if isinstance(s, dict):
            kws += [str(k) for k in s.keys()]
        elif s:
            kws.append(str(s))
    sc = p.get("search", {}) or {}
    for q in (sc.get("jobspy_queries") or []):
        if q.get("term"): kws.append(str(q["term"]))
    for q in (sc.get("kariyer_queries") or []):
        kws.append(str(q))
    kws += [str(c) for c in (p.get("preferred_locations") or [])]
    seen, out = set(), []
    for k in kws:
        kl = k.strip().lower()
        if kl and kl not in seen:
            seen.add(kl); out.append(k.strip())
    return out


@app.get("/api/profiles")
def api_profiles():
    """Dashboard'daki isim seçici için profilleri döndür."""
    return {
        "profiles": [
            {"key": p["key"], "name": p.get("name", p["key"]),
             "title": p.get("title", ""), "keywords": _profile_keywords(p)}
            for p in profiles_mod.list_profiles()
        ]
    }


@app.get("/api/filter-options")
def api_filter_options():
    return {"cities": TURKISH_CITIES}


@app.get("/api/stats")
def api_stats(profile: str = Query("all")):
    return db.get_stats(profile=profile)


@app.get("/api/jobs")
def api_jobs(
    profile: str = Query("all"),
    status: str = Query("all"),
    source: str = Query("all"),
    min_score: float = Query(0.0),
    remote_only: bool = Query(False),
    city: str = Query("all"),
    work_mode: str = Query("all"),
    days: str = Query("all"),
    search: str = Query(""),
    sort: str = Query("score"),
    limit: int = Query(200),
    offset: int = Query(0),
):
    jobs = db.get_jobs(
        profile=profile, status=status, source=source, min_score=min_score,
        remote_only=remote_only, city=city, work_mode=work_mode, days=days,
        search=search or None, sort=sort, limit=limit, offset=offset,
    )
    return {"jobs": jobs, "count": len(jobs)}


def _safe_segment(value: str, default: str = "general") -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", (value or "").strip()).strip(".-")
    return value[:80] or default


def _safe_filename(value: str) -> str:
    name = Path(value or "resume.pdf").name
    stem = re.sub(r"[^a-zA-Z0-9ğüşöçıİĞÜŞÖÇ_.-]+", "-", Path(name).stem).strip(".-")
    return (stem[:80] or "resume") + ".pdf"


def _profile_upload_dir(profile: str) -> Path:
    return UPLOAD_ROOT / _safe_segment(profile)


def _resolve_upload_path(profile: str, stored_name: str) -> Path:
    folder = _profile_upload_dir(profile)
    target = (folder / Path(stored_name).name).resolve()
    if folder.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail="geçersiz dosya yolu")
    return target


def _upload_info(path: Path, profile: str) -> dict:
    stat = path.stat()
    stored = path.name
    original = re.sub(r"^\d+_\d+_", "", stored)
    return {
        "profile": profile or "general",
        "stored_name": stored,
        "original_name": original,
        "size": stat.st_size,
        "uploaded_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/uploads")
def api_uploads(profile: str = Query("")):
    prof = _safe_segment(profile)
    folder = _profile_upload_dir(prof)
    if not folder.exists():
        return {"files": []}
    files = sorted(folder.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"files": [_upload_info(p, prof) for p in files]}


@app.post("/api/uploads")
async def api_upload_pdfs(profile: str = Query(""), files: list[UploadFile] = File(...)):
    prof = _safe_segment(profile)
    folder = _profile_upload_dir(prof)
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, file in enumerate(files):
        original = file.filename or "resume.pdf"
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{original} 10 MB sınırını aşıyor")
        if not original.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail=f"{original} geçerli bir PDF değil")
        stored = f"{int(time.time()*1000)}_{i}_{_safe_filename(original)}"
        target = folder / stored
        target.write_bytes(data)
        saved.append(_upload_info(target, prof))
        await file.close()
    return {"ok": True, "files": saved}


@app.get("/api/uploads/{stored_name}/analysis")
def api_upload_analysis(stored_name: str, profile: str = Query("")):
    prof = _safe_segment(profile)
    target = _resolve_upload_path(prof, stored_name)
    if not target.exists() or target.suffix.lower() != ".pdf":
        return JSONResponse({"error": "dosya bulunamadı"}, status_code=404)
    analysis = analyze_resume_pdf(target)
    return {"file": _upload_info(target, prof), **analysis}


@app.delete("/api/uploads/{stored_name}")
def api_delete_upload(stored_name: str, profile: str = Query("")):
    prof = _safe_segment(profile)
    target = _resolve_upload_path(prof, stored_name)
    if not target.exists():
        return JSONResponse({"error": "dosya bulunamadı"}, status_code=404)
    target.unlink()
    return {"ok": True}


@app.post("/api/jobs/{url_hash}/status")
def api_update_status(url_hash: str, status: str = Query(...),
                      profile: str = Query("")):
    if status not in ("new", "saved", "applied", "dismissed"):
        return JSONResponse({"error": "geçersiz durum"}, status_code=400)
    db.update_status(url_hash, status, profile=profile)
    return {"ok": True, "url_hash": url_hash, "status": status}


@app.get("/api/jobs/{url_hash}/application")
def api_application(url_hash: str, profile: str = Query("")):
    """İlana özel ön yazı + başvuru cevabı taslağı üret."""
    job = db.get_job(url_hash, profile=profile)
    if not job:
        return JSONResponse({"error": "ilan bulunamadı"}, status_code=404)
    prof = profiles_mod.get_profile(profile or job.get("profile", "")) or {}
    return generate_application(job, prof)


@app.post("/api/scan")
def api_scan(profile: str = Query("")):
    """profile verilirse o kişiyi, verilmezse tüm profilleri tarar."""
    if scanner._scan_lock.locked() or db.is_scan_running():
        return {"started": False, "reason": "Tarama zaten çalışıyor"}
    threading.Thread(
        target=scanner.run_scan,
        kwargs={"profile_key": profile or None},
        daemon=True,
    ).start()
    return {"started": True, "profile": profile or "all"}


@app.get("/api/scan/status")
def api_scan_status():
    return {"running": db.is_scan_running()}


# Statik dosyalar (gerekirse)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
