"""
Fast tests (no browser) for Sprint 3 backlog 2: live notification badge and toast (UC-I).
GET /api/notifikasi/belum-dibaca, its access rules, the polling settings on citizen pages
and the polling interval setting. The browser behaviour itself is in uc_i_push_notifikasi.feature.
"""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.controllers.kontrol_notifikasi import KontrolNotifikasi
from app.controllers.kontrol_penugasan import KontrolPenugasan
from app.database import SessionLocal
from app.main import POLL_NOTIF_BAWAAN, app, interval_poll_notif
from app.models.entities import Notifikasi, Warga
from database.seed import seed_data

WARGA = "0812xxxxxxx"        # USR-01: 1 unread (NTF-SEED-0001), 1 read
WARGA_LAIN = "0813xxxxxxx"   # USR-03
ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"
URL = "/api/notifikasi/belum-dibaca"


@pytest.fixture
def db_bersih():
    seed_data(verbose=False)


def klien(identifier=None) -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": "password123"}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


def tugaskan_341():
    db = SessionLocal()
    try:
        assert KontrolPenugasan(db).tugaskan_penilik("REP-2026-00341", "Budi Santoso").status_work_order == "Ditugaskan"
    finally:
        db.close()


def konfig(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="konfigNotifLangsung">(.*?)</script>', html, re.S)
    assert m, "konfigurasi polling tidak ada di halaman"
    return json.loads(m.group(1))


# ------------------------------------------------------------- endpoint access
def test_tanpa_login_401_tanpa_data(db_bersih):
    r = klien().get(URL, follow_redirects=False)
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/json")
    assert set(r.json()) == {"detail"}


@pytest.mark.parametrize("akun", [ADMIN, KABID, PENILIK])
def test_staf_403(db_bersih, akun):
    r = klien(akun).get(URL)
    assert r.status_code == 403 and set(r.json()) == {"detail"}


def test_akun_dinonaktifkan_401(db_bersih):
    c = klien(WARGA)
    db = SessionLocal()
    try:
        db.query(Warga).filter_by(no_hp=WARGA).one().is_active = False
        db.commit()
    finally:
        db.close()
    assert c.get(URL).status_code == 401


def test_polling_tidak_pernah_mengeluarkan_warga(db_bersih):
    """A poll that briefly cannot find the account (e.g. while the test database is re-seeded)
    answers 401 but does not clear the session; only a real page load ends it."""
    c = klien(WARGA)
    db = SessionLocal()
    try:
        db.query(Warga).filter_by(no_hp=WARGA).one().is_active = False
        db.commit()
        assert c.get(URL).status_code == 401
        db.query(Warga).filter_by(no_hp=WARGA).one().is_active = True
        db.commit()
    finally:
        db.close()
    assert c.get(URL).status_code == 200  # still logged in


# ------------------------------------------------------------- endpoint data
def test_warga_mendapat_jumlah_dan_notifikasi_terbaru(db_bersih):
    r = klien(WARGA).get(URL)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    data = r.json()
    assert data["jumlah"] == 1
    [n] = data["terbaru"]
    assert n["id"] == "NTF-SEED-0001" and n["id_laporan"] == "LAP-2026-0001"
    assert n["url"] == "/notifikasi/NTF-SEED-0001/buka"
    assert n["judul"] and "LAP-2026-0001" in n["pesan"] and n["waktu"].endswith("WIB")


def test_perubahan_status_langsung_terlihat(db_bersih):
    c = klien(WARGA)
    tugaskan_341()
    data = c.get(URL).json()
    assert data["jumlah"] == 2
    assert data["terbaru"][0]["id_laporan"] == "LAP-2026-0001"
    assert data["terbaru"][0]["id"] != "NTF-SEED-0001"  # newest first


def test_hanya_notifikasi_milik_sendiri(db_bersih):
    tugaskan_341()  # notifies USR-01 only
    data = klien(WARGA_LAIN).get(URL).json()
    assert data == {"jumlah": 0, "terbaru": []}


def test_terbaru_paling_banyak_lima_dan_jumlah_tetap_lengkap(db_bersih):
    db = SessionLocal()
    try:
        for i in range(7):
            db.add(Notifikasi(id_notifikasi=f"NTF-UJI-{i}", id_laporan="LAP-2026-0001", id_warga="USR-01",
                              judul="Uji", pesan=f"pesan {i}", status_baca=False))
        db.commit()
    finally:
        db.close()
    data = klien(WARGA).get(URL).json()
    assert data["jumlah"] == 8 and len(data["terbaru"]) == 5


def test_notifikasi_dibaca_tidak_ikut(db_bersih):
    c = klien(WARGA)
    c.get("/notifikasi/NTF-SEED-0001/buka")
    assert c.get(URL).json() == {"jumlah": 0, "terbaru": []}


def test_belum_dibaca_terbaru_urut_dari_yang_terbaru(db_bersih):
    tugaskan_341()
    db = SessionLocal()
    try:
        ids = [n.id_notifikasi for n in KontrolNotifikasi(db).belum_dibaca_terbaru("USR-01")]
    finally:
        db.close()
    assert len(ids) == 2 and ids[-1] == "NTF-SEED-0001"


# ------------------------------------------------------------- citizen pages
@pytest.mark.parametrize("halaman", ["/Beranda", "/lapor", "/lacak", "/notifikasi"])
def test_halaman_warga_memuat_polling_dan_toast(db_bersih, halaman):
    html = klien(WARGA).get(halaman).text
    k = konfig(html)
    assert k["url"] == URL and k["interval_detik"] >= 1
    assert k["terlihat"] == ["NTF-SEED-0001"]  # already on screen: no toast for it
    assert 'id="toastNotif"' in html and "/static/js/notifikasi_langsung.js" in html
    assert 'id="menuNotifikasi" data-kelas-badge=' in html


@pytest.mark.parametrize("akun, halaman", [(ADMIN, "/Dashboard"), (ADMIN, "/master-data"),
                                           (KABID, "/laporan-kinerja"), (PENILIK, "/TugasLapangan")])
def test_halaman_staf_tanpa_polling(db_bersih, akun, halaman):
    html = klien(akun).get(halaman).text
    assert "konfigNotifLangsung" not in html and 'id="toastNotif"' not in html


def test_halaman_login_tanpa_polling(db_bersih):
    assert "konfigNotifLangsung" not in klien().get("/Login").text


def test_tombol_izin_notifikasi_browser_di_halaman_notifikasi(db_bersih):
    assert 'id="aktifkanNotifBrowser"' in klien(WARGA).get("/notifikasi").text


def test_berkas_skrip_tersedia():
    r = TestClient(app).get("/static/js/notifikasi_langsung.js")
    assert r.status_code == 200
    assert "fetch(konfig.url" in r.text  # the URL comes from the page settings
    assert "badgeNotif" in r.text and "toastNotif" in r.text and "Notification" in r.text
    # polling must not pause in a hidden/covered window (browser notifications matter most there)
    assert "if (document.hidden) {" not in r.text


# ------------------------------------------------------------- interval setting
@pytest.mark.parametrize("nilai, hasil", [
    (None, POLL_NOTIF_BAWAAN), ("5", 5), ("1", 1), ("0", POLL_NOTIF_BAWAAN), ("-3", POLL_NOTIF_BAWAAN),
    ("abc", POLL_NOTIF_BAWAAN),
])
def test_interval_poll(monkeypatch, nilai, hasil):
    if nilai is None:
        monkeypatch.delenv("SCMS_POLL_NOTIF_DETIK", raising=False)
    else:
        monkeypatch.setenv("SCMS_POLL_NOTIF_DETIK", nilai)
    assert interval_poll_notif() == hasil


def test_bawaan_lima_belas_detik():
    assert POLL_NOTIF_BAWAAN == 15
