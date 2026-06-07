#!/usr/bin/env python3
"""Dashboard static contract tests.

Runs without project dependencies so UI regressions can be checked from Windows
or WSL even when scraper/API packages are not installed in the active Python.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent
HTML_PATH = ROOT / "web" / "static" / "index.html"

PASS = 0
FAIL = 0
FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK {name}")
    else:
        FAIL += 1
        FAILS.append(name)
        print(f"  FAIL {name}")


def html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def test_theme_contract(src: str) -> None:
    print("\n[theme contract]")
    themes_match = re.search(r"const THEMES=\[(.*?)\];", src, re.S)
    check("THEMES dizisi var", themes_match is not None)
    if not themes_match:
        return

    ids = re.findall(r'id:"([^"]+)"', themes_match.group(1))
    check("tema id'leri tekil", len(ids) == len(set(ids)))
    check("siyah tema menüde", "black" in ids)
    check("siyah tema eski terminal yeşilini kullanıyor", "#c6f035" in src)
    check("siyah tema eski camgöbeği vurgusunu kullanıyor", "#4fe0c5" in src)
    for theme_id in ids:
        check(f"{theme_id} renk noktası var", f"d-{theme_id}" in src)
    for theme_id in [i for i in ids if i not in ("light", "ocean", "emerald")]:
        check(f"{theme_id} data-theme kuralı var", f'data-theme="{theme_id}"' in src)


def test_filter_and_status_contract(src: str) -> None:
    print("\n[filter/status contract]")
    required = [
        ('id="filterSummary"', "aktif filtre özeti"),
        ('id="clearSearchBtn"', "arama temizleme düğmesi"),
        ('id="citySel"', "şehir filtresi"),
        ('id="workModeSel"', "çalışma şekli filtresi"),
        ('id="daysSel"', "tarih filtresi"),
        ('id="focusbar"', "odak aksiyon satırı"),
        ('id="tab-all-count"', "tümü sekme sayacı"),
        ('id="tab-new-count"', "yeni sekme sayacı"),
        ("function renderFocusbar()", "odak satırı render fonksiyonu"),
        ("function applyFocus(", "odak filtresi fonksiyonu"),
        ("function renderFilterSummary()", "filtre özeti fonksiyonu"),
        ("function clearFilters()", "filtre temizleme fonksiyonu"),
        ("function undoStatus()", "durum geri alma fonksiyonu"),
        ('label:"Geri al"', "toast geri alma aksiyonu"),
    ]
    for needle, label in required:
        check(label, needle in src)


def test_upload_contract(src: str) -> None:
    print("\n[pdf upload contract]")
    required = [
        ('id="resumePanel"', "PDF paneli"),
        ('id="resumeInput"', "PDF dosya alanı"),
        ('id="uploadList"', "yüklenen PDF listesi"),
        ('accept=".pdf,application/pdf"', "yalnızca PDF kabulü"),
        ("function loadUploads()", "yüklenenleri listeleme fonksiyonu"),
        ("function uploadResumes()", "PDF yükleme fonksiyonu"),
        ("/api/uploads", "upload API bağlantısı"),
    ]
    for needle, label in required:
        check(label, needle in src)


def test_resume_analysis_contract(src: str) -> None:
    print("\n[pdf analysis contract]")
    required = [
        ('id="resumeAnalysis"', "PDF analiz paneli"),
        ("function analyzeUpload(", "PDF analiz fonksiyonu"),
        ("function renderResumeAnalysis(", "PDF analiz render fonksiyonu"),
        ("/analysis", "analiz API bağlantısı"),
        ("Önerileri çıkar", "PDF öneri aksiyonu"),
    ]
    for needle, label in required:
        check(label, needle in src)


def test_inline_scripts_compile(src: str) -> None:
    print("\n[js syntax]")
    scripts = re.findall(r"<script>([\s\S]*?)</script>", src)
    check("inline script bulundu", bool(scripts))
    node = shutil.which("node")
    if not node:
        print("  SKIP Node yok; JS syntax kontrolü atlandı")
        return

    js = "\n".join(f"new Function({script!r});" for script in scripts)
    result = subprocess.run([node, "-e", js], cwd=ROOT, text=True, capture_output=True)
    check("inline JS derleniyor", result.returncode == 0)
    if result.returncode != 0:
        print(result.stderr.strip())


def main() -> int:
    print("=" * 60)
    print("  DASHBOARD STATIC TESTLER")
    print("=" * 60)
    src = html()
    test_theme_contract(src)
    test_filter_and_status_contract(src)
    test_upload_contract(src)
    test_resume_analysis_contract(src)
    test_inline_scripts_compile(src)
    print("\n" + "=" * 60)
    print(f"  SONUÇ: {PASS} geçti, {FAIL} başarısız")
    if FAILS:
        print("  Başarısızlar:", ", ".join(FAILS))
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
