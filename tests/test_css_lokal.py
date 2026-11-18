"""
Deploy (Sprint 3 point 7): Tailwind CSS is served from app/static/css/tailwind.css,
built with `npm run build:css`, instead of the Tailwind Play CDN script.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "views" / "templates"
CSS = ROOT / "app" / "static" / "css" / "tailwind.css"


def _halaman_penuh():
    """Templates that are full HTML pages (not partials/macros)."""
    return [p for p in sorted(TEMPLATES.glob("*.html")) if "<html" in p.read_text(encoding="utf-8")
            or p.name == "_layout.html"]


def test_tidak_ada_template_yang_memuat_tailwind_dari_cdn():
    pelanggar = [p.name for p in TEMPLATES.glob("*.html") if "cdn.tailwindcss.com" in p.read_text(encoding="utf-8")]
    assert pelanggar == []


@pytest.mark.parametrize("halaman", _halaman_penuh(), ids=lambda p: p.name)
def test_setiap_halaman_penuh_memuat_css_lokal(halaman):
    html = halaman.read_text(encoding="utf-8")
    if "{% extends" in html:
        pytest.skip("mewarisi _layout.html")
    assert 'href="/static/css/tailwind.css"' in html


def test_css_hasil_build_tersedia_dan_disajikan():
    assert CSS.exists() and CSS.stat().st_size > 10_000
    r = TestClient(app).get("/static/css/tailwind.css")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")


@pytest.mark.parametrize("kelas", ["bg-[#0B5ED7]", "bg-[#0F2942]", "bg-[#F8FAFC]", "lg:grid-cols-2", "sm:w-96", "min-w-[18px]"])
def test_kelas_dari_template_ada_di_css(kelas):
    """Spot check that the committed CSS was built from the current templates (run `npm run build:css`)."""
    escaped = re.sub(r"([\[\]#:/.])", r"\\\1", kelas)
    assert "." + escaped in CSS.read_text(encoding="utf-8"), f"{kelas} tidak ada; jalankan `npm run build:css`"


def test_preflight_tailwind_ikut_dibangun():
    css = CSS.read_text(encoding="utf-8")
    assert "box-sizing:border-box" in css.replace(" ", "")
