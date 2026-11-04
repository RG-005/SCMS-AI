"""
Fast tests (no browser) for UC-L Laporan Kinerja Infrastruktur:
access per role, SLA calculation, period/region filters, CSV export and CSV formula injection.
"""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.controllers.kontrol_laporan_kinerja import (
    MELEWATI_SLA, PESAN_KOSONG, PESAN_RENTANG_TERBALIK, PESAN_TANGGAL_TIDAK_VALID, TEPAT_WAKTU, TERLAMBAT,
    DALAM_SLA, KontrolLaporanKinerja, aman_untuk_spreadsheet, jam_sla,
)
from app.database import SessionLocal
from app.main import app
from app.models.entities import Rating, WorkOrder
from database.seed import seed_data

WARGA = "0812xxxxxxx"
ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"


def wib(hari, jam, menit=0):
    """A WIB (UTC+7) wall-clock time in October 2026, as an aware UTC datetime."""
    return datetime(2026, 10, hari, jam, menit, tzinfo=timezone(timedelta(hours=7))).astimezone(timezone.utc)


@pytest.fixture
def db_bersih():
    seed_data(verbose=False)


def klien(identifier=None, password="password123") -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


def rekap(**kwargs):
    db = SessionLocal()
    try:
        return KontrolLaporanKinerja(db).rekap(**kwargs)
    finally:
        db.close()


def ubah_wo(id_wo, **kolom):
    db = SessionLocal()
    try:
        wo = db.get(WorkOrder, id_wo)
        for k, v in kolom.items():
            setattr(wo, k, v)
        db.commit()
    finally:
        db.close()


def tiket(data, id_wo):
    return next(b for b in data["tiket"] if b["id_work_order"] == id_wo)


def baca_csv(teks):
    assert teks.startswith("﻿"), "CSV needs a BOM so Excel reads UTF-8"
    return list(csv.reader(io.StringIO(teks.lstrip("﻿"))))


# ------------------------------------------------------------------ access
@pytest.mark.parametrize("akun, kode", [
    (KABID, 200), (ADMIN, 200), (WARGA, 403), (PENILIK, 403),
])
def test_hak_akses_halaman_dan_unduhan(db_bersih, akun, kode):
    c = klien(akun)
    assert c.get("/laporan-kinerja").status_code == kode
    assert c.get("/laporan-kinerja/unduh?jenis=wilayah").status_code == kode


def test_tanpa_login_diarahkan_ke_login(db_bersih):
    r = klien().get("/laporan-kinerja", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/Login")


def test_menu_laporan_kinerja_hanya_untuk_admin_dan_kabid(db_bersih):
    for halaman in ("/Dashboard", "/verifikasi", "/work-orders", "/master-data"):
        assert 'href="/laporan-kinerja"' in klien(KABID).get(halaman).text, halaman
    for halaman in ("/Dashboard", "/work-orders", "/TugasLapangan"):
        assert 'href="/laporan-kinerja"' not in klien(PENILIK).get(halaman).text, halaman


# ---------------------------------------------------------- SLA calculation
@pytest.mark.parametrize("teks, jam", [
    ("24 jam", 24), ("48 jam", 48), ("3x24 jam", 72), ("7x24 jam", 168), ("7 x 24 Jam", 168),
    ("", None), (None, None), ("segera", None),
])
def test_jam_sla(teks, jam):
    assert jam_sla(teks) == jam


def test_tiket_selesai_melewati_sla_tercatat_terlambat(db_bersih):
    # REP-2026-00290: diterima 5 Okt 09:00 WIB, selesai 10 Okt 15:00 WIB, SLA 3x24 jam
    t = tiket(rekap(), "REP-2026-00290")
    assert t["sla"] == "3x24 jam"
    assert t["durasi_jam"] == 126.0
    assert t["status_sla"] == TERLAMBAT


def test_tiket_selesai_dalam_sla_tercatat_tepat_waktu(db_bersih):
    ubah_wo("REP-2026-00290", tanggal_selesai=wib(7, 9).replace(tzinfo=None))  # 48 jam setelah diterima
    data = rekap()
    assert tiket(data, "REP-2026-00290")["status_sla"] == TEPAT_WAKTU
    gubeng = next(r for r in data["per_wilayah"] if r["nama_wilayah"] == "Wilayah Gubeng")
    assert gubeng["kepatuhan_sla"] == 100.0
    assert gubeng["rata_durasi_jam"] == 48.0


def test_tiket_aktif_dalam_dan_melewati_sla(db_bersih):
    # REP-2026-00341: Urgent (SLA 24 jam), diterima 20 Okt 08:15 WIB
    assert tiket(rekap(sekarang=wib(20, 20)), "REP-2026-00341")["status_sla"] == DALAM_SLA
    assert tiket(rekap(sekarang=wib(22, 8)), "REP-2026-00341")["status_sla"] == MELEWATI_SLA


def test_ringkasan_total(db_bersih):
    data = rekap(sekarang=wib(31, 12))
    total = data["total"]
    assert total["total"] == 5 and total["selesai"] == 1 and total["aktif"] == 4
    assert total["tingkat_penyelesaian"] == 20.0
    assert total["terlambat"] == 1 and total["tepat_waktu"] == 0
    assert total["kepatuhan_sla"] == 0.0
    assert total["aktif_lewat_sla"] == 4
    assert total["risk_tertinggi"] == 8.4
    # sorted by risk, highest first
    assert data["tiket"][0]["id_work_order"] == "REP-2026-00341"


def test_wilayah_tanpa_tiket_tetap_tampil_dengan_nol(db_bersih):
    wonokromo = next(r for r in rekap()["per_wilayah"] if r["nama_wilayah"] == "Wonokromo")
    assert wonokromo["total"] == 0 and wonokromo["kepatuhan_sla"] is None


def test_rating_warga_masuk_rekap(db_bersih):
    db = SessionLocal()
    try:
        db.add(Rating(id_rating="RTG-UJI-1", id_laporan="LAP-2026-0003", nilai_bintang=4, komentar="rapi"))
        db.commit()
    finally:
        db.close()
    gubeng = next(r for r in rekap()["per_wilayah"] if r["nama_wilayah"] == "Wilayah Gubeng")
    assert gubeng["rata_rating"] == 4.0 and gubeng["jumlah_rating"] == 1


# ------------------------------------------------------------------ filters
def test_filter_periode_berdasarkan_tanggal_diterima_wib(db_bersih):
    data = rekap(tanggal_mulai="2026-10-19", tanggal_akhir="2026-10-20")
    assert {b["id_work_order"] for b in data["tiket"]} == {"REP-2026-00360", "REP-2026-00341"}


def test_filter_wilayah(db_bersih):
    data = rekap(wilayah="WIL-02")
    assert [b["id_work_order"] for b in data["tiket"]] == ["REP-2026-00360"]
    assert [r["nama_wilayah"] for r in data["per_wilayah"]] == ["Wilayah Benowo"]


def test_periode_tanpa_data(db_bersih):
    data = rekap(tanggal_mulai="2025-01-01", tanggal_akhir="2025-01-31")
    assert data["success"] and data["message"] == PESAN_KOSONG and data["tiket"] == []
    html = klien(KABID).get("/laporan-kinerja?tanggal_mulai=2025-01-01&tanggal_akhir=2025-01-31").text
    assert PESAN_KOSONG in html and 'id="unduhWilayah"' not in html


@pytest.mark.parametrize("mulai, akhir, pesan", [
    ("2026-10-31", "2026-10-01", PESAN_RENTANG_TERBALIK),
    ("31-10-2026", "", PESAN_TANGGAL_TIDAK_VALID),
])
def test_tanggal_tidak_valid_ditolak(db_bersih, mulai, akhir, pesan):
    assert rekap(tanggal_mulai=mulai, tanggal_akhir=akhir)["message"] == pesan
    c = klien(KABID)
    r = c.get("/laporan-kinerja", params={"tanggal_mulai": mulai, "tanggal_akhir": akhir})
    assert r.status_code == 400 and pesan in r.text
    r = c.get("/laporan-kinerja/unduh", params={"jenis": "tiket", "tanggal_mulai": mulai, "tanggal_akhir": akhir})
    assert r.status_code == 400


# ---------------------------------------------------------------------- CSV
def test_unduh_csv_rekap_wilayah(db_bersih):
    r = klien(KABID).get("/laporan-kinerja/unduh",
                         params={"jenis": "wilayah", "tanggal_mulai": "2026-10-01", "tanggal_akhir": "2026-10-31"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == \
        'attachment; filename="laporan_kinerja_wilayah_2026-10-01_sd_2026-10-31.csv"'
    baris = baca_csv(r.content.decode("utf-8"))
    assert baris[0][:2] == ["Wilayah", "Total Tiket"]
    gubeng = next(b for b in baris if b[0] == "Wilayah Gubeng")
    assert gubeng[1] == "4"
    assert baris[-1][0] == "TOTAL" and baris[-1][1] == "5"


def test_unduh_csv_detail_tiket(db_bersih):
    r = klien(ADMIN).get("/laporan-kinerja/unduh?jenis=tiket")
    baris = baca_csv(r.content.decode("utf-8"))
    kolom = baris[0]
    assert kolom[0] == "ID Tiket" and "Status SLA" in kolom
    rep290 = next(b for b in baris if b[0] == "REP-2026-00290")
    assert rep290[kolom.index("Status SLA")] == TERLAMBAT
    assert rep290[kolom.index("Selesai (WIB)")] == "10-10-2026 15:00"


def test_jenis_unduhan_tidak_dikenal_ditolak(db_bersih):
    assert klien(KABID).get("/laporan-kinerja/unduh?jenis=semua").status_code == 400


def test_csv_tidak_bisa_menjalankan_formula_dari_input_warga(db_bersih):
    ubah_wo("REP-2026-00341", lokasi_jalan='=HYPERLINK("http://evil.example","klik")')
    baris = baca_csv(klien(KABID).get("/laporan-kinerja/unduh?jenis=tiket").content.decode("utf-8"))
    kolom = baris[0]
    lokasi = next(b for b in baris if b[0] == "REP-2026-00341")[kolom.index("Lokasi")]
    assert lokasi.startswith("'=")


@pytest.mark.parametrize("nilai, hasil", [
    ("=1+1", "'=1+1"), ("+62", "'+62"), ("-5", "'-5"), ("@SUM(A1)", "'@SUM(A1)"),
    ("Jl. Raya", "Jl. Raya"), (8.4, 8.4), (-1.5, -1.5),
])
def test_aman_untuk_spreadsheet(nilai, hasil):
    assert aman_untuk_spreadsheet(nilai) == hasil
