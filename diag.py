#!/usr/bin/env python3
"""
Teşhis aracı — scraper'ları CANLI çalıştırır, her kaynağın kaç ilan getirdiğini
ve filtrenin kaçını tuttuğunu/elediğini gösterir.
Çalıştır:  python diag.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import scanner
import profiles as P
from profiles import profile_scoring
from filter_engine import score_job, should_exclude, location_allowed, is_remote_job
from scrapers.jobspy_scraper import scrape_jobspy
from scrapers.kariyer_scraper import scrape_kariyer

def main():
    cfg = scanner.load_config()
    base_scoring = cfg.get("scoring", {}) or {}
    base_exclude = (cfg.get("filters", {}) or {}).get("exclude_keywords", []) or []
    min_store = float(cfg["schedule"].get("min_score_to_store", 1.0))

    profs = P.list_profiles()
    if not profs:
        print("❌ profiles/ klasöründe profil yok!"); return

    for prof in profs:
        name = prof.get("name", prof["key"])
        search = prof.get("search", {}) or {}
        cities = prof.get("preferred_locations", []) or []
        print("\n" + "=" * 60)
        print(f"  👤 {name}  (şehirler: {cities})")
        print("=" * 60)

        raw = []
        # Kariyer (ilk 2 sorgu)
        try:
            kq = (search.get("kariyer_queries") or [])[:2]
            kj = scrape_kariyer(kq) if kq else []
            print(f"  Kariyer.net : {len(kj)} ham ilan  (sorgu: {kq})")
            raw += kj
        except Exception as e:
            print(f"  Kariyer.net : ❌ HATA -> {e}")
        # JobSpy (ilk 2 sorgu, hız için results=10)
        try:
            jq = (search.get("jobspy_queries") or [])[:2]
            jj = scrape_jobspy(jq, search.get("hours_old", 168), 10) if jq else []
            print(f"  JobSpy      : {len(jj)} ham ilan  (Indeed/Google/LinkedIn)")
            raw += jj
        except Exception as e:
            print(f"  JobSpy      : ❌ HATA -> {e}")

        # puanlama
        scoring = dict(base_scoring)
        for k, w in profile_scoring(prof).items():
            scoring[k] = max(scoring.get(k, 0), w)
        exclude = list(base_exclude) + list(prof.get("exclude_keywords", []) or [])

        kept = 0; n_exc = n_low = n_loc = 0
        print(f"\n  --- filtre (min skor: {min_store}) ---")
        for j in raw:
            if should_exclude(j, exclude):
                n_exc += 1; continue
            j.score = score_job(j, scoring)
            j.is_remote = is_remote_job(j)
            if j.score < min_store:
                n_low += 1; continue
            if not location_allowed(j.location, cities, j.is_remote):
                n_loc += 1; continue
            kept += 1
            print(f"    ✅ [{j.score:>4.1f}] {(j.title or '')[:42]:42} | {(j.location or '?')[:18]:18} | {j.source}")
        print(f"\n  SONUÇ: ham={len(raw)} | kelime_elendi={n_exc} | dusuk_skor={n_low} | yanlis_konum={n_loc} | KABUL={kept}")

    print("\nBitti. Bu çıktıyı bana gönder, neyin yanlış olduğunu birlikte görelim.")

if __name__ == "__main__":
    main()
