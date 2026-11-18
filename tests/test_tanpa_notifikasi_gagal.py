"""The "Notifikasi Gagal" / "Kirim Ulang" feature (old Sprint 3 BR-8) was removed by the team.

These tests keep it removed: no route, no staff menu, no simulated delivery channel, and the
deprecated `notifikasi` columns are neither written nor read by the application. The in-app
notification (UC-I) itself is unchanged.
"""
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.entities import Laporan, Notifikasi
from app.services.alur_status import kirim_notifikasi
from database.seed import seed_data

ROOT = Path(__file__).resolve().parent.parent
KOLOM_USANG = ("status_kirim", "jumlah_percobaan", "waktu_percobaan_terakhir")
ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
WARGA = "0812xxxxxxx"


@pytest.fixture
def db_bersih():
    seed_data(verbose=False)


def klien(identifier=None, password="password123") -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


@pytest.mark.parametrize("akun", [ADMIN, KABID])
def test_rute_notifikasi_gagal_tidak_ada(db_bersih, akun):
    c = klien(akun)
    assert c.get("/notifikasi-gagal").status_code == 404
    assert c.post("/notifikasi-gagal/NTF-SEED-0003/kirim-ulang").status_code == 404


@pytest.mark.parametrize("akun,url", [
    (ADMIN, "/Dashboard"), (ADMIN, "/verifikasi"), (ADMIN, "/work-orders"), (ADMIN, "/master-data"),
    (KABID, "/laporan-kinerja"),
])
def test_menu_notifikasi_gagal_tidak_tampil(db_bersih, akun, url):
    halaman = klien(akun).get(url)
    assert halaman.status_code == 200
    for teks in ("menuNotifikasiGagal", "badgeNotifGagal", "/notifikasi-gagal", "Notifikasi Gagal", "Kirim Ulang"):
        assert teks not in halaman.text, (url, teks)


def test_layanan_kanal_tersimulasi_sudah_dihapus():
    assert importlib.util.find_spec("app.services.pengiriman_notifikasi") is None
    assert not (ROOT / "app/views/templates/notifikasi_gagal.html").exists()


def test_kode_aplikasi_tidak_memakai_kolom_usang():
    """Only the column definitions (entities.py) and the old-database fix-up (database.py) remain."""
    pemakai = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "app").rglob("*")
                     if p.suffix in (".py", ".html", ".js") and "__pycache__" not in p.parts
                     and any(k in p.read_text(encoding="utf-8") for k in KOLOM_USANG))
    assert pemakai == ["app/database.py", "app/models/entities.py"]


def test_variabel_lingkungan_kanal_tidak_dipakai_lagi():
    berkas = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in (".py", ".yml", ".example", ".html", ".js")
              and not ({"node_modules", ".git", "__pycache__", "tests"} & set(p.parts))]
    berkas += [ROOT / ".env.example", ROOT / ".env.docker.example"]
    pemakai = [str(p.relative_to(ROOT)) for p in berkas if p.exists()
               and "SCMS_NOTIF_TINGKAT_GAGAL" in p.read_text(encoding="utf-8", errors="ignore")]
    assert pemakai == []


def test_notifikasi_in_app_tetap_dibuat_dan_tampil(db_bersih):
    db = SessionLocal()
    try:
        laporan = db.get(Laporan, "LAP-2026-0001")
        notif = kirim_notifikasi(db, laporan, "Uji", "Pesan uji")
        db.commit()
        id_notif = notif.id_notifikasi
    finally:
        db.close()
    assert f'id="notif-{id_notif}"' in klien(WARGA).get("/notifikasi").text


def test_seed_tidak_lagi_membuat_notifikasi_gagal(db_bersih):
    db = SessionLocal()
    try:
        assert db.query(Notifikasi).filter_by(status_kirim="Gagal").count() == 0
    finally:
        db.close()
