#!/usr/bin/env python3
"""
JOB_BOT test paketi — bağımsız (pytest gerekmez, özel profile gerekmez).
Çalıştır:  python test_jobbot.py
Kendi geçici test profilini (profiles/_test.yaml) kurar, scraper'ları mock'lar.
"""
import base64
import sys, tempfile, os, shutil
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

PASS = 0; FAIL = 0; FAILS = []
def check(name, cond):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {name}")
    else: FAIL += 1; FAILS.append(name); print(f"  ❌ {name}")

from models import Job
import filter_engine as FE
import db as DB
import profiles as P
import cover_letter as CL
import notifier as NT
import scanner as SC
import apply_lite as AL

TEST_KEY = "tester"
_TMP = {"dir": None, "old": None, "auth_env": {}}


def fake_config() -> dict:
    cfg = SC.load_config()
    cfg["telegram"] = {"bot_token": "tok", "chat_id": "chat"}
    return cfg


FIXTURE_YAML = """\
key: "tester"
order: 99
name: "Test Kullanıcı"
title: "QA Test Mühendisi"
email: "test@example.com"
location: "İzmir"
preferred_locations: ["İzmir", "Manisa"]
work_modes: ["yerinde", "hibrit", "uzaktan"]
summary: "Test profili."
skill_weight: 2
skills:
  - "qa"
  - "test mühendisi"
  - "selenium"
search:
  hours_old: 168
  results_wanted: 10
  jobspy_queries:
    - { term: "Test Mühendisi", sites: ["indeed"], location: "Izmir, Turkey", country_indeed: "Turkey" }
  kariyer_queries:
    - "yazılım test uzmanı"
exclude_keywords:
  - "satış temsilcisi"
"""

def setup_fixture():
    _TMP["dir"] = Path(tempfile.mkdtemp(prefix="jobbot_test_"))
    (_TMP["dir"] / "tester.yaml").write_text(FIXTURE_YAML, encoding="utf-8")
    _TMP["old"] = P.PROFILES_DIR
    P.PROFILES_DIR = _TMP["dir"]   # gerçek profiles/ yerine geçici klasör
    _TMP["auth_env"] = {k: os.environ.get(k) for k in ("DASHBOARD_USERNAME", "DASHBOARD_PASSWORD")}
    os.environ["DASHBOARD_PASSWORD"] = ""

def teardown_fixture():
    if _TMP["old"] is not None:
        P.PROFILES_DIR = _TMP["old"]
    if _TMP["dir"]:
        shutil.rmtree(_TMP["dir"], ignore_errors=True)
    for k, v in (_TMP["auth_env"] or {}).items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_filter_engine():
    print("\n[filter_engine]")
    check("tr_norm İ->i", FE.tr_norm("İdari İŞLER")=="idari işler")
    check("tr_norm dotless ı", FE.tr_norm("YAZILIM")=="yazilim")
    j = Job("QA Test Mühendisi","X","İzmir, Türkiye","u","indeed",description="selenium uzaktan")
    check("score_job topluyor (>0)", FE.score_job(j, {"qa":3,"selenium":2,"izmir":2})>0)
    check("score_job remote bonus", FE.score_job(Job("t","c","Uzaktan","u","s"), {})>=1.0)
    check("İ-başlık eşleşmesi", FE.score_job(Job("İdari İşler Uzmanı","c","l","u","s"), {"idari işler":2})>=2)
    check("relevance konum saymaz", FE.relevance_score(Job("Garson","c","İzmir","u","s"), {"qa":3,"izmir":2})==0)
    check("relevance rol sayar", FE.relevance_score(Job("QA Uzmanı","c","l","u","s"), {"qa":3})==3)
    check("should_exclude", FE.should_exclude(Job("Satış Temsilcisi","c","l","u","s"), ["satış temsilcisi"]))
    check("location izmir TUT", FE.location_allowed("İzmir, Türkiye", ["İzmir","Manisa"], False))
    check("location manisa TUT", FE.location_allowed("Manisa", ["İzmir","Manisa"], False))
    check("location Indeed T35 İzmir TUT", FE.location_allowed("Alsancak, T35, TR", ["İzmir","Manisa"], False))
    check("location jenerik TUT", FE.location_allowed("Türkiye", ["İzmir","Manisa"], False))
    check("location boş TUT", FE.location_allowed("", ["İzmir","Manisa"], False))
    check("location remote TUT", FE.location_allowed("İstanbul", ["İzmir","Manisa"], True))
    check("location İstanbul yerinde AT", not FE.location_allowed("İstanbul", ["İzmir","Manisa"], False))
    check("location Ankara yerinde AT", not FE.location_allowed("Ankara, Türkiye", ["İzmir","Manisa"], False))
    check("location İçel yerinde AT", not FE.location_allowed("Gülnar, İçel, Türkiye", ["İzmir","Manisa"], False))
    check("location İzmir izin yoksa AT", not FE.location_allowed("İzmir, Türkiye", ["Ankara"], False))
    check("location Eskişehir izin yoksa AT", not FE.location_allowed("Eskişehir", ["Ankara"], False))
    check("is_remote_job uzaktan", FE.is_remote_job(Job("t","c","Uzaktan / Remote","u","s")))
    check("is_remote_job yerinde False", not FE.is_remote_job(Job("t","c","İzmir","u","s")))
    check("work_mode_allowed uzaktan", FE.work_mode_allowed(Job("QA","c","Uzaktan","u","s", is_remote=True), ["uzaktan"]))
    check("work_mode_allowed yerinde eler", not FE.work_mode_allowed(Job("QA","c","İzmir","u","s"), ["uzaktan"]))
    closed = Job(
        "QA Test Mühendisi",
        "Acme",
        "İzmir",
        "u",
        "linkedin",
        description="No longer accepting applications. Selenium deneyimi aranıyor.",
    )
    check("kapalı başvuru uyarısı yakalanır", FE.has_inactive_application_warning(closed))
    active = Job(
        "QA Test Mühendisi",
        "Acme",
        "İzmir",
        "u2",
        "indeed",
        description="Başvuru için Selenium deneyimi aranıyor.",
    )
    check("aktif başvuru yanlış elenmez", not FE.has_inactive_application_warning(active))


def test_db():
    print("\n[db]")
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    check("upsert yeni True", DB.upsert_job(Job("QA Test","A","İzmir","https://x/1","indeed",score=8,is_remote=True), "a") is True)
    check("upsert tekrar False (dedup)", DB.upsert_job(Job("QA Test","A","İzmir","https://x/1","indeed",score=9), "a") is False)
    DB.upsert_job(Job("İdari","B","Manisa","https://x/2","kariyer.net",score=5), "b")
    check("profil ayrımı a=1", len(DB.get_jobs(profile="a"))==1)
    check("profil ayrımı b=1", len(DB.get_jobs(profile="b"))==1)
    check("get_jobs all=2", len(DB.get_jobs(profile="all"))==2)
    check("min_score filtresi", len(DB.get_jobs(profile="a", min_score=9))==1)
    check("remote_only filtresi", len(DB.get_jobs(profile="a", remote_only=True))==1)
    check("kaynak filtresi", len(DB.get_jobs(profile="b", source="kariyer.net"))==1)
    check("arama filtresi", len(DB.get_jobs(profile="a", search="qa"))==1)
    h = DB.get_jobs(profile="a")[0]["url_hash"]
    DB.update_status(h, "saved", "a")
    check("update_status", DB.get_jobs(profile="a", status="saved")[0]["url_hash"]==h)
    tracked = DB.update_tracker(h, "a", status="interview", follow_up_at="2026-07-08", note="İK görüşmesi bekleniyor")
    check("update_tracker durum", tracked["status"]=="interview")
    check("update_tracker takip tarihi", tracked["follow_up_at"]=="2026-07-08")
    check("update_tracker not", tracked["tracker_note"]=="İK görüşmesi bekleniyor")
    st = DB.get_stats("a")
    check("get_stats total", st["total"]==1)
    check("get_stats interview", st["interview"]==1 and st["by_status"]["interview"]==1)
    DB.set_source_health("kariyer.net", "blocked", "403")
    health = {x["source"]: x for x in DB.get_source_health()}
    check("source health varsayilan jobspy", health["jobspy"]["status"]=="unknown")
    check("source health blocked", health["kariyer.net"]["status"]=="blocked")
    check("source health mesaj", health["kariyer.net"]["message"]=="403")
    with DB.get_conn() as conn:
        conn.execute(
            "UPDATE source_health SET checked_at = '2026-01-01 10:00:00' WHERE source = 'kariyer.net'"
        )
    DB.set_source_health("kariyer.net", "blocked", "skip", touch=False)
    health = {x["source"]: x for x in DB.get_source_health()}
    check("source health touch false zamani korur", health["kariyer.net"]["checked_at"]=="2026-01-01 10:00:00")
    un = DB.get_unnotified(3.0, "b")
    check("get_unnotified döner Job", len(un)==1 and hasattr(un[0],"title"))
    DB.mark_notified([DB.get_jobs(profile="b")[0]["url_hash"]], "b")
    check("mark_notified sonrası 0", len(DB.get_unnotified(3.0,"b"))==0)
    DB.delete_job(h, "a")
    check("delete_job", len(DB.get_jobs(profile="a"))==0)
    os.unlink(p)


def test_db_general_filters():
    print("\n[db genel filtreler]")
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    DB.upsert_job(Job("QA Test","A","İzmir","https://f/1","indeed",score=8,is_remote=True), "a")
    DB.upsert_job(Job("İdari İşler","B","İstanbul Hibrit","https://f/2","kariyer.net",score=6,is_remote=False), "a")
    DB.upsert_job(Job("Satın Alma","C","Ankara","https://f/3","google",score=5,is_remote=False), "a")
    try:
        check("şehir filtresi İzmir", len(DB.get_jobs(profile="a", city="İzmir"))==1)
        check("şehir filtresi İstanbul", len(DB.get_jobs(profile="a", city="İstanbul"))==1)
        check("çalışma şekli remote", len(DB.get_jobs(profile="a", work_mode="remote"))==1)
        check("çalışma şekli hibrit", len(DB.get_jobs(profile="a", work_mode="hybrid"))==1)
        check("çalışma şekli yerinde", len(DB.get_jobs(profile="a", work_mode="onsite"))==1)
        check("tarih filtresi", len(DB.get_jobs(profile="a", days=7))==3)
    finally:
        os.unlink(p)


def test_profiles():
    print("\n[profiles]")
    ps = P.list_profiles()
    check("en az 1 profil", len(ps)>=1)
    check("test profili yüklendi", any(x["key"]==TEST_KEY for x in ps))
    t = P.get_profile(TEST_KEY)
    check("get_profile çalışıyor", t and t["key"]==TEST_KEY)
    check("search.jobspy_queries var", len(t["search"]["jobspy_queries"])>0)
    w = P.profile_scoring(t)
    check("profile_scoring boş değil", len(w)>0)
    check("ağırlık float", isinstance(list(w.values())[0], float))
    check("example.yaml mevcut", (Path(__file__).parent/"profiles"/"example.yaml").exists())


def test_dashboard_ui_contract():
    print("\n[dashboard ui]")
    html = (Path(__file__).parent / "web" / "static" / "index.html").read_text(encoding="utf-8")
    check("aktif filtre özeti var", 'id="filterSummary"' in html)
    check("odak aksiyon satırı var", 'id="focusbar"' in html and "function renderFocusbar()" in html)
    check("arama temizleme düğmesi var", 'id="clearSearchBtn"' in html)
    check("sekme sayaçları var", 'id="tab-all-count"' in html and 'id="tab-new-count"' in html)
    check("filtreleri temizleme fonksiyonu var", "function clearFilters()" in html)
    check("filtre özeti render fonksiyonu var", "function renderFilterSummary()" in html)
    check("durum geri alma fonksiyonu var", "function undoStatus()" in html)
    check("kaynak sagligi UI var", "function loadSourceHealth()" in html and "/api/source-health" in html)
    check("kaynak sagligi uyarisi var", 'id="sourceHealthNote"' in html and "function renderSourceHealthNote()" in html)
    check("auto apply lite UI var", 'id="autoApplyPanel"' in html and "function loadApplyQueue()" in html)
    check("başvuru planı UI var", 'id="appPlan"' in html and "function renderApplyPlan(" in html)
    check("kapalı başvuru gizleme bilgisi var", "CLOSED_HIDDEN_COUNT" in html and "kapalı başvuru gizlendi" in html)
    check("takipçi UI var", 'id="trackerStatus"' in html and 'id="trackerFollowUp"' in html and 'id="trackerNote"' in html)
    check("takipçi kaydetme fonksiyonu var", "function saveTracker(" in html and "/tracker" in html)
    check("takipçi export var", "/api/tracker/export" in html and "CSV" in html)
    check("takipçi durum sekmeleri var", 'data-status="screening"' in html and 'data-status="interview"' in html and 'data-status="offer"' in html and 'data-status="rejected"' in html)
    check("siyah terminal tema var", 'id:"black"' in html and 'data-theme="black"' in html and "#c6f035" in html and "#4fe0c5" in html)


def test_cover_letter():
    print("\n[cover_letter]")
    prof = P.get_profile(TEST_KEY) or {}
    job = {"title":"QA Test Mühendisi","company":"Acme","url":"https://x/1","location":"İzmir","score":8,"is_remote":True,"url_hash":"abc"}
    a = CL.generate_application(job, prof)
    check("cover_letter string", isinstance(a["cover_letter"], str) and len(a["cover_letter"])>50)
    check("şirket adı geçiyor", "Acme" in a["cover_letter"])
    check("answers>=3", len(a["answers"])>=3)
    check("highlights var", len(a["highlights"])>0)
    check("url korunuyor", a["url"]=="https://x/1")


def test_apply_lite():
    print("\n[apply lite]")
    prof = P.get_profile(TEST_KEY) or {}
    policy = AL.apply_policy({"auto_apply": {"min_score": 7, "daily_limit": 2}}, prof)
    email_job = {
        "title": "QA Test Mühendisi",
        "company": "Acme",
        "location": "İzmir",
        "url": "https://acme.test/jobs/1",
        "source": "company",
        "description": "Başvuru için cv@acme.test adresine CV gönderin.",
        "score": 8,
        "status": "new",
    }
    app = CL.generate_application(email_job, prof)
    plan = AL.build_apply_plan(email_job, prof, policy, app)
    check("email yakalandı", plan["email"] == "cv@acme.test")
    check("email plan hazır", plan["ready"] is True and plan["method"] == "email")
    check("mailto üretildi", plan["mailto_url"].startswith("mailto:cv%40acme.test"))

    blocked_job = dict(email_job, source="linkedin", description="", score=8)
    blocked = AL.build_apply_plan(blocked_job, prof, policy, app)
    check("platform otomasyonu kapalı", blocked["method"] == "blocked_platform" and not blocked["ready"])

    low_job = dict(email_job, score=3)
    low = AL.build_apply_plan(low_job, prof, policy, app)
    check("düşük skor aday değil", low["candidate"] is False)


def test_notifier():
    print("\n[notifier]")
    sent = []
    orig = NT.send_message
    NT.send_message = lambda t,c,text:(sent.append(text), True)[1]
    NT.notify_summary("tok","chat",[{"name":"A","raw":10,"new":3,"notified":2},{"name":"B","raw":5,"new":1,"notified":1}])
    check("summary gönderildi", len(sent)==1 and "Tarama Raporu" in sent[0])
    check("summary toplam doğru", "Toplam yeni" in sent[0])
    sent.clear()
    NT.notify_jobs("tok","chat",[Job("QA","A","İzmir","u","indeed",score=8)], label="A")
    check("notify_jobs >=3 mesaj", len(sent)>=3)
    check("notify_jobs label", any("A" in m for m in sent))
    sent.clear()
    fit_job = Job(
        "QA Test Mühendisi",
        "Acme",
        "Uzaktan",
        "u2",
        "indeed",
        description="Aranan Nitelikler: Selenium deneyimi. Python bilgisi. İyi iletişim.",
        score=8,
        is_remote=True,
    )
    fit_job.match_terms = ["qa", "selenium"]
    fit_job.match_score = 5
    NT.notify_jobs("tok","chat",[fit_job], label="A")
    body = "\n".join(sent)
    check("notify_jobs uygunluk nedeni", "Özellikle uygun" in body and "selenium" in body)
    check("notify_jobs beklenti özeti", "Beklentiler" in body and "Selenium deneyimi" in body)
    NT.send_message = orig
    check("boş token False", NT.send_message("", "c", "x") is False)
    check("placeholder token False", NT.send_message("${TELEGRAM_BOT_TOKEN}", "c", "x") is False)


def test_scanner_pipeline():
    print("\n[scanner pipeline (mock scraper)]")
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    fake = [
        Job("QA Test Mühendisi","Acme","İzmir, Türkiye","u1","indeed",description="selenium"),     # TUT
        Job("Test Mühendisi","Beta","İstanbul","u2","indeed",description=""),                        # AT (İstanbul yerinde)
        Job("Yazılım Test Uzmanı","Gamma","Uzaktan","u3","kariyer.net",description="uzaktan"),       # TUT (remote, arama terimi)
        Job("QA Test Mühendisi","ClosedCo","İzmir","u_closed","linkedin",description="No longer accepting applications. selenium"),  # AT (başvuru kapalı)
        Job("Garson","Cafe","İzmir","u4","indeed",description=""),                                    # AT (rol uygun değil)
    ]
    o = (SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary)
    sent = []
    notified_jobs = []
    SC.scrape_jobspy = lambda *a, **k: fake
    SC.scrape_kariyer = lambda *a, **k: []
    SC.scrape_rss_feeds = lambda *a, **k: []
    def fake_notify(bt, ci, jobs, label=""):
        notified_jobs.extend(jobs)
        sent.append(("jobs",label,len(jobs)))
    SC.notify_jobs = fake_notify
    SC.notify_summary = lambda bt,ci,res: sent.append(("summary",res))
    try:
        SC.run_scan(cfg=fake_config(), profile_key=TEST_KEY)
        titles = [r["title"] for r in DB.get_jobs(profile=TEST_KEY)]
        check("İzmir QA tutuldu", "QA Test Mühendisi" in titles)
        check("İstanbul yerinde elendi", "Test Mühendisi" not in titles)
        check("uzaktan tutuldu", "Yazılım Test Uzmanı" in titles)
        check("başvuru kapalı ilan elendi", "ClosedCo" not in [r["company"] for r in DB.get_jobs(profile=TEST_KEY)])
        check("alakasız (Garson) elendi", "Garson" not in titles)
        check("bildirim uygunluk terimleri taşıyor", any("selenium" in (j.match_terms or []) for j in notified_jobs))
        check("özet rapor gönderildi", any(s[0]=="summary" for s in sent))
    finally:
        SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary = o
        os.unlink(p)


def test_scanner_without_telegram_keeps_unnotified():
    print("\n[scanner telegram opsiyonel]")
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    fake = [
        Job("QA Test Mühendisi","Acme","İzmir, Türkiye","u_no_tg","indeed",description="selenium"),
    ]
    o = (SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary)
    sent = []
    SC.scrape_jobspy = lambda *a, **k: fake
    SC.scrape_kariyer = lambda *a, **k: []
    SC.scrape_rss_feeds = lambda *a, **k: []
    SC.notify_jobs = lambda *a, **k: sent.append("jobs")
    SC.notify_summary = lambda *a, **k: sent.append("summary")
    cfg = SC.load_config()
    cfg["telegram"] = {"bot_token": "", "chat_id": ""}
    try:
        result = SC.run_scan(cfg=cfg, profile_key=TEST_KEY)
        check("telegram yokken notify çağrılmadı", sent == [])
        check("telegram yokken bildirim sayısı 0", result.get("notified") == 0)
        check("telegram yokken bildirim beklemede kaldı", len(DB.get_unnotified(3.0, TEST_KEY)) == 1)
    finally:
        SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary = o
        os.unlink(p)


def test_scanner_store_score_threshold():
    print("\n[scanner min_score_to_store]")
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    fake = [
        Job("QA","Low","Türkiye","u_low_store","indeed",description="qa"),
        Job("QA Test Mühendisi","High","Uzaktan","u_high_store","indeed",description="selenium uzaktan"),
    ]
    o = (SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary)
    SC.scrape_jobspy = lambda *a, **k: fake
    SC.scrape_kariyer = lambda *a, **k: []
    SC.scrape_rss_feeds = lambda *a, **k: []
    SC.notify_jobs = lambda *a, **k: None
    SC.notify_summary = lambda *a, **k: None
    cfg = fake_config()
    cfg["schedule"]["min_score_to_store"] = 5
    try:
        SC.run_scan(cfg=cfg, profile_key=TEST_KEY)
        titles = [r["title"] for r in DB.get_jobs(profile=TEST_KEY, min_score=0)]
        check("düşük saklama skoru elendi", "QA" not in titles)
        check("yüksek skor saklandı", "QA Test Mühendisi" in titles)
    finally:
        SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary = o
        os.unlink(p)


def test_scanner_work_modes():
    print("\n[scanner work_modes]")
    key = "remoteonly"
    fx = P.PROFILES_DIR / f"{key}.yaml"
    fx.write_text(
        'key: "remoteonly"\norder: 97\nname: "Remote Only"\ntitle: "QA"\n'
        'preferred_locations: ["İzmir"]\nwork_modes: ["uzaktan"]\nskill_weight: 2\n'
        'skills: ["qa"]\nsearch:\n  jobspy_queries:\n'
        '    - { term: "QA", sites: ["indeed"], location: "Turkey", country_indeed: "Turkey" }\n',
        encoding="utf-8",
    )
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    fake = [
        Job("QA Engineer","RemoteCo","Uzaktan","u_remote_mode","indeed",description="qa remote"),
        Job("QA Engineer","OfficeCo","İzmir","u_office_mode","indeed",description="qa"),
    ]
    o = (SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary)
    SC.scrape_jobspy = lambda *a, **k: fake
    SC.scrape_kariyer = lambda *a, **k: []
    SC.scrape_rss_feeds = lambda *a, **k: []
    SC.notify_jobs = lambda *a, **k: None
    SC.notify_summary = lambda *a, **k: None
    cfg = fake_config()
    cfg["schedule"]["min_score_to_store"] = 0
    try:
        SC.run_scan(cfg=cfg, profile_key=key)
        companies = [r["company"] for r in DB.get_jobs(profile=key, min_score=0)]
        check("uzaktan ilan tutuldu", "RemoteCo" in companies)
        check("yerinde ilan work_modes ile elendi", "OfficeCo" not in companies)
    finally:
        SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary = o
        os.unlink(p)
        try: fx.unlink()
        except OSError: pass


def test_scanner_kariyer_block_cooldown():
    print("\n[scanner kariyer block cooldown]")
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    DB.set_source_health("kariyer.net", "blocked", "403")
    calls = {"kariyer": 0}
    o = (SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary)
    SC.scrape_jobspy = lambda *a, **k: []
    def blocked_kariyer(*a, **k):
        calls["kariyer"] += 1
        return []
    SC.scrape_kariyer = blocked_kariyer
    SC.scrape_rss_feeds = lambda *a, **k: []
    SC.notify_jobs = lambda *a, **k: None
    SC.notify_summary = lambda *a, **k: None
    cfg = fake_config()
    cfg["sources"] = {"kariyer_block_cooldown_hours": 6}
    try:
        SC.run_scan(cfg=cfg, profile_key=TEST_KEY)
        health = {x["source"]: x for x in DB.get_source_health()}
        check("cooldown kariyer scraper cagrilmadi", calls["kariyer"] == 0)
        check("cooldown blocked kaldi", health["kariyer.net"]["status"] == "blocked")
        check("cooldown mesaji yazildi", "yeniden denenmeyecek" in health["kariyer.net"]["message"])
    finally:
        SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary = o
        os.unlink(p)


def test_location_priority():
    print("\n[konum önceliği — ilk şehir üstte]")
    key = "manisatest"
    fx = P.PROFILES_DIR / f"{key}.yaml"
    fx.write_text(
        'key: "manisatest"\norder: 98\nname: "Manisa Test"\ntitle: "İdari İşler Uzmanı"\n'
        'preferred_locations: ["Manisa", "İzmir"]\nskill_weight: 2\n'
        'skills: ["idari işler", "satın alma"]\nsearch:\n  jobspy_queries:\n'
        '    - { term: "İdari İşler Uzmanı", sites: ["indeed"], location: "Manisa, Turkey", country_indeed: "Turkey" }\n'
        '  kariyer_queries: ["idari işler uzmanı"]\n', encoding="utf-8")
    p = tempfile.mktemp(suffix=".db"); DB.configure(p)
    fake = [
        Job("İdari İşler Uzmanı","A","İzmir, Türkiye","u1","indeed",description="satın alma"),
        Job("İdari İşler Uzmanı","B","Manisa, Türkiye","u2","indeed",description="satın alma"),
    ]
    o = (SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary)
    SC.scrape_jobspy = lambda *a, **k: fake
    SC.scrape_kariyer = lambda *a, **k: []
    SC.scrape_rss_feeds = lambda *a, **k: []
    SC.notify_jobs = lambda *a, **k: None
    SC.notify_summary = lambda *a, **k: None
    try:
        SC.run_scan(cfg=fake_config(), profile_key=key)
        rows = DB.get_jobs(profile=key, sort="score")
        check("iki ilan da kabul", len(rows) == 2)
        check("Manisa ilk sırada", bool(rows) and "Manisa" in (rows[0]["location"] or ""))
        check("Manisa skoru > İzmir", rows[0]["score"] > rows[-1]["score"])
    finally:
        SC.scrape_jobspy, SC.scrape_kariyer, SC.scrape_rss_feeds, SC.notify_jobs, SC.notify_summary = o
        os.unlink(p)
        try: fx.unlink()
        except OSError: pass


def test_web_api():
    print("\n[web api (gerçek HTTP)]")
    import threading, time, json, urllib.request, uvicorn
    p = tempfile.mktemp(suffix=".db")
    DB.configure(p)
    DB.upsert_job(Job("QA Test","A","İzmir","https://x/1","indeed",score=8,is_remote=True), TEST_KEY)
    DB.upsert_job(Job(
        "QA Closed",
        "ClosedCo",
        "İzmir",
        "https://x/closed",
        "company",
        description="No longer accepting applications. qa selenium cv@closed.test",
        score=9,
        is_remote=True,
    ), TEST_KEY)
    DB.set_source_health("kariyer.net", "blocked", "403")
    from web.app import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=8809, log_level="error")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start(); time.sleep(2.0)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def g(path): return json.load(op.open("http://127.0.0.1:8809"+path, timeout=6))
    def post(path):
        return json.load(op.open(urllib.request.Request("http://127.0.0.1:8809"+path, method="POST"), timeout=6))
    def patch(path, payload):
        req = urllib.request.Request(
            "http://127.0.0.1:8809"+path,
            data=json.dumps(payload).encode("utf-8"),
            method="PATCH",
            headers={"Content-Type": "application/json"},
        )
        return json.load(op.open(req, timeout=6))
    try:
        check("/ 200", op.open("http://127.0.0.1:8809/", timeout=6).status==200)
        check("/api/profiles", len(g("/api/profiles")["profiles"])>=1)
        check("/api/stats total", g("/api/stats?profile="+TEST_KEY)["total"]==2)
        jb = g("/api/jobs?profile="+TEST_KEY)
        check("/api/jobs count", jb["count"]==1)
        check("/api/jobs hidden_count", jb.get("hidden_count")==1)
        check("/api/jobs kapalı ilan göstermez", all(j["company"]!="ClosedCo" for j in jb["jobs"]))
        check("/api/jobs remote", g("/api/jobs?profile="+TEST_KEY+"&remote_only=true")["count"]==1)
        check("/api/jobs arama", g("/api/jobs?profile="+TEST_KEY+"&search=qa")["count"]==1)
        h = jb["jobs"][0]["url_hash"]
        check("/api/application", "cover_letter" in g(f"/api/jobs/{h}/application?profile="+TEST_KEY))
        check("/api/status ok", post(f"/api/jobs/{h}/status?status=saved&profile="+TEST_KEY).get("ok") is True)
        tr = patch(f"/api/jobs/{h}/tracker?profile="+TEST_KEY, {"status":"interview","follow_up_at":"2026-07-08","note":"İK görüşmesi"})
        check("/api/tracker patch", tr.get("ok") is True and tr["job"]["status"]=="interview" and tr["job"]["tracker_note"]=="İK görüşmesi")
        check("/api/tracker export json", g("/api/tracker/export?profile="+TEST_KEY+"&format=json")["count"]==2)
        check("/api/scan/status", "running" in g("/api/scan/status"))
        sh = g("/api/source-health")["sources"]
        check("/api/source-health", any(x["source"]=="kariyer.net" and x["status"]=="blocked" for x in sh))
        aq = g("/api/apply/queue?profile="+TEST_KEY)
        check("/api/apply/queue", "items" in aq and "ready_count" in aq)
        check("/api/apply/queue hidden_count", aq.get("hidden_count")==1)
        check("/api/apply/queue kapalı ilan göstermez", all((x.get("job") or {}).get("company")!="ClosedCo" for x in aq["items"]))
    finally:
        srv.should_exit = True; os.unlink(p)


def test_dashboard_auth():
    print("\n[dashboard auth]")
    import threading, time, urllib.error, urllib.request, uvicorn

    old_user = os.environ.get("DASHBOARD_USERNAME")
    old_pass = os.environ.get("DASHBOARD_PASSWORD")
    os.environ["DASHBOARD_USERNAME"] = "tester"
    os.environ["DASHBOARD_PASSWORD"] = "secret"
    from web.app import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=8811, log_level="error")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start(); time.sleep(2.0)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        status = None
        try:
            op.open("http://127.0.0.1:8811/", timeout=6)
        except urllib.error.HTTPError as e:
            status = e.code
        check("şifresiz 401", status == 401)

        token = base64.b64encode(b"tester:secret").decode("ascii")
        req = urllib.request.Request("http://127.0.0.1:8811/")
        req.add_header("Authorization", "Basic " + token)
        check("şifreli 200", op.open(req, timeout=6).status == 200)
    finally:
        srv.should_exit = True
        if old_user is None:
            os.environ.pop("DASHBOARD_USERNAME", None)
        else:
            os.environ["DASHBOARD_USERNAME"] = old_user
        if old_pass is None:
            os.environ.pop("DASHBOARD_PASSWORD", None)
        else:
            os.environ["DASHBOARD_PASSWORD"] = old_pass


def test_resume_analyzer():
    print("\n[resume analyzer]")
    from resume_analyzer import suggest_profile_from_text

    text = """
    QA Test Mühendisi olarak Selenium, Postman, SQL ve API test deneyimim var.
    İzmir ve Manisa lokasyonlarında hibrit veya uzaktan çalışmaya uygunum.
    """
    result = suggest_profile_from_text(text)
    suggestions = result["suggestions"]
    check("beceriler çıkarıldı", "Selenium" in suggestions["skills"] and "SQL" in suggestions["skills"])
    check("şehirler çıkarıldı", "İzmir" in suggestions["locations"] and "Manisa" in suggestions["locations"])
    check("pozisyon önerisi çıkarıldı", any("Test" in title for title in suggestions["titles"]))
    check("arama terimi önerisi çıkarıldı", any("QA" in term or "Test" in term for term in suggestions["search_terms"]))


def test_upload_api():
    print("\n[upload api]")
    import threading, time, json, urllib.request, uvicorn
    import web.app as WA
    old_root = WA.UPLOAD_ROOT
    old_analyze = WA.analyze_resume_pdf
    tmp_root = Path(tempfile.mkdtemp(prefix="jobbot_uploads_"))
    WA.UPLOAD_ROOT = tmp_root
    WA.analyze_resume_pdf = lambda path: {
        "status": "ok",
        "text_chars": 64,
        "preview": "QA Test Mühendisi Selenium SQL İzmir",
        "suggestions": {
            "skills": ["Selenium", "SQL"],
            "titles": ["QA Test Mühendisi"],
            "locations": ["İzmir"],
            "search_terms": ["QA Test Mühendisi", "Yazılım Test Uzmanı"],
        },
    }
    from web.app import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=8810, log_level="error")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start(); time.sleep(2.0)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path):
        return json.load(op.open("http://127.0.0.1:8810"+path, timeout=6))

    def delete(path):
        req = urllib.request.Request("http://127.0.0.1:8810"+path, method="DELETE")
        return json.load(op.open(req, timeout=6))

    def post_pdf(path, filename, payload):
        boundary = "----jobbot-test-boundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8810"+path,
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        return json.load(op.open(req, timeout=6))

    try:
        up = post_pdf("/api/uploads?profile="+TEST_KEY, "cv-test.pdf", b"%PDF-1.4\n%test\n")
        check("pdf upload ok", up.get("ok") is True and up.get("files"))
        files = get("/api/uploads?profile="+TEST_KEY)["files"]
        check("pdf listelendi", len(files)==1 and files[0]["original_name"]=="cv-test.pdf")
        stored = files[0]["stored_name"]
        analysis = get("/api/uploads/"+stored+"/analysis?profile="+TEST_KEY)
        check("pdf analiz endpoint ok", analysis.get("status")=="ok" and analysis.get("text_chars")==64)
        check("pdf analiz beceri döndü", "Selenium" in analysis["suggestions"]["skills"])
        check("pdf analiz dosya bilgisi döndü", analysis["file"]["stored_name"]==stored)
        check("pdf silindi", delete("/api/uploads/"+stored+"?profile="+TEST_KEY).get("ok") is True)
        check("silme sonrası liste boş", get("/api/uploads?profile="+TEST_KEY)["files"]==[])
    finally:
        srv.should_exit = True
        WA.UPLOAD_ROOT = old_root
        WA.analyze_resume_pdf = old_analyze
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    print("="*60); print("  JOB_BOT TEST PAKETİ"); print("="*60)
    setup_fixture()
    try:
        for t in [test_filter_engine, test_db, test_db_general_filters, test_profiles, test_dashboard_ui_contract, test_cover_letter,
                  test_apply_lite,
                  test_notifier, test_scanner_pipeline, test_scanner_without_telegram_keeps_unnotified,
                  test_scanner_store_score_threshold, test_scanner_work_modes,
                  test_scanner_kariyer_block_cooldown, test_location_priority,
                  test_web_api, test_dashboard_auth, test_resume_analyzer, test_upload_api]:
            try: t()
            except Exception as e:
                FAIL += 1; FAILS.append(t.__name__+" (exception)")
                import traceback; print(f"  ❌ {t.__name__} EXCEPTION: {e}"); traceback.print_exc()
    finally:
        teardown_fixture()
    print("\n"+"="*60)
    print(f"  SONUÇ: {PASS} geçti, {FAIL} başarısız")
    if FAILS: print("  Başarısızlar:", ", ".join(FAILS))
    print("="*60)
    sys.exit(1 if FAIL else 0)
