"""FastAPI web uygulaması — çok profilli dashboard + JSON API."""
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db
import scanner
import profiles as profiles_mod
from cover_letter import generate_application

logger = logging.getLogger(__name__)

app = FastAPI(title="Job Bot Dashboard")
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/profiles")
def api_profiles():
    """Dashboard'daki isim seçici için profilleri döndür."""
    return {
        "profiles": [
            {"key": p["key"], "name": p.get("name", p["key"]),
             "title": p.get("title", "")}
            for p in profiles_mod.list_profiles()
        ]
    }


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
    search: str = Query(""),
    sort: str = Query("score"),
    limit: int = Query(200),
):
    jobs = db.get_jobs(
        profile=profile, status=status, source=source, min_score=min_score,
        remote_only=remote_only, search=search or None,
        sort=sort, limit=limit,
    )
    return {"jobs": jobs, "count": len(jobs)}


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
