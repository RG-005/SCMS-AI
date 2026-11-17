"""
Fast tests (no browser) for UC-L Laporan Kinerja Infrastruktur:
access per role, stage durations from riwayat_status, age of active tickets,
period/region filters, CSV export and CSV formula injection.

Removed SLA tests (jam_sla, Tepat Waktu/Terlambat, Dalam/Melewati SLA, Kepatuhan SLA) were
replaced by stage-duration and ticket-age tests when the SLA concept was removed
after the teaching assistant's review.
"""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.controllers.kontrol_laporan_kinerja import (
    MASUK, PESAN_KOSONG, PESAN_RENTANG_TERBALIK, PESAN_TANGGAL_TIDAK_VALID, KontrolLaporanKinerja,
    aman_untuk_spreadsheet, durasi_tahap,
)
from app.database import SessionLocal
from app.main import app
from app.models.entities import Rating, RiwayatStatus, WorkOrder
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


def tambah_riwayat(id_wo, *entri):
    """entri: (status, aware UTC time). Stored naive UTC like the app does."""
    db = SessionLocal()
    try:
        for status, waktu in entri:
            db.add(RiwayatStatus(id_work_order=id_wo, status=status, keterangan="uji", waktu=waktu.replace(tzinfo=None)))
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


# --------------------------------------- stage durations (SLA removed)
def jam(n):
    return pytest.approx(n / 24)


def test_durasi_tahap_jalur_normal_dari_riwayat(db_bersih):
    # REP-2026-00290 (seed, WIB): diterima 5/10 09:00, Disetujui 5/10 14:00, Ditugaskan 6/10 08:00,
    # Terinspeksi 7/10 10:00, Dalam Proses 8/10 09:00, Selesai 10/10 15:00
    t = tiket(rekap(), "REP-2026-00290")
    mentah = t["_durasi_tahap_mentah"]
    assert mentah["verifikasi"] == jam(5)
    assert mentah["penugasan"] == jam(18)
    assert mentah["inspeksi"] == jam(26)
    assert mentah["spk"] == jam(23)
    assert mentah["perbaikan"] == jam(54)
    assert t["durasi_tahap"] == {"verifikasi": 0.2, "penugasan": 0.8, "inspeksi": 1.1, "spk": 1.0, "perbaikan": 2.2}
    assert t["durasi_hari"] == round(126 / 24, 1)
    assert t["tahap_saat_ini"] == "Selesai" and t["umur_hari"] is None
    assert not any("sla" in kunci for kunci in t)


def test_durasi_tahap_jalur_inspeksi_tambahan_tidak_menghitung_tahap_yang_dilewati(db_bersih):
    # REP-2026-00355 (diterima 22/10 10:00 WIB) takes the additional-inspection path:
    # Dilaporkan -> Menunggu Inspeksi -> Terinspeksi -> Dalam Proses -> Selesai (never Ditugaskan)
    tambah_riwayat("REP-2026-00355", ("Menunggu Inspeksi", wib(22, 12)), ("Terinspeksi", wib(23, 12)),
                   ("Dalam Proses", wib(24, 12)), ("Selesai", wib(26, 12)))
    ubah_wo("REP-2026-00355", status_work_order="Selesai")
    data = rekap()
    t = tiket(data, "REP-2026-00355")
    assert t["_durasi_tahap_mentah"]["verifikasi"] == jam(2)
    assert t["durasi_tahap"]["penugasan"] is None
    assert t["durasi_tahap"]["inspeksi"] is None
    assert t["durasi_tahap"]["spk"] == 1.0 and t["durasi_tahap"]["perbaikan"] == 2.0
    assert t["durasi_hari"] == round((4 * 24 + 2) / 24, 1)
    # the skipped stages are not counted for this ticket in the averages either
    borderline = next(r for r in data["per_prioritas"] if r["prioritas"] == "Borderline")
    assert borderline["jumlah_tahap"] == {"verifikasi": 1, "penugasan": 0, "inspeksi": 0, "spk": 1, "perbaikan": 1}
    assert borderline["rata_tahap"]["penugasan"] is None and borderline["rata_tahap"]["perbaikan"] == 2.0
    assert data["total"]["jumlah_tahap"]["inspeksi"] == 1  # only REP-2026-00290


def test_tiket_yang_belum_melewati_tahap_tidak_dihitung(db_bersih):
    # REP-2026-00341 is Disetujui: only "Verifikasi" is finished (20/10 08:15 -> 13:00 WIB)
    data = rekap()
    t = tiket(data, "REP-2026-00341")
    assert t["_durasi_tahap_mentah"]["verifikasi"] == jam(4.75)
    assert [t["durasi_tahap"][k] for k in ("penugasan", "inspeksi", "spk", "perbaikan")] == [None] * 4
    # REP-2026-00355 (Dilaporkan) has not finished any stage
    assert set(tiket(data, "REP-2026-00355")["durasi_tahap"].values()) == {None}
    total = data["total"]
    assert total["jumlah_tahap"] == {"verifikasi": 4, "penugasan": 2, "inspeksi": 1, "spk": 1, "perbaikan": 1}
    # average over the tickets that finished the stage: (5 + 4.75 + 3.33 + 17) h / 4 tickets
    assert total["rata_tahap"]["verifikasi"] == round((5 + 4.75 + 10 / 3 + 17) / 24 / 4, 1)
    assert total["rata_tahap"]["penugasan"] == round((18 + 21) / 24 / 2, 1)


def test_durasi_tahap_per_prioritas(db_bersih):
    per = {r["prioritas"]: r for r in rekap()["per_prioritas"]}
    # Tinggi: REP-2026-00290 (verifikasi 5 h) and REP-2026-00360 (verifikasi 17 h)
    assert per["Tinggi"]["jumlah_tahap"]["verifikasi"] == 2
    assert per["Tinggi"]["rata_tahap"]["verifikasi"] == round(22 / 24 / 2, 1)
    assert per["Tinggi"]["rata_tahap"]["perbaikan"] == round(54 / 24, 1)
    # Urgent: REP-2026-00298 reached Ditugaskan (21 h after approval), REP-2026-00341 did not
    assert per["Urgent"]["jumlah_tahap"]["penugasan"] == 1
    assert per["Urgent"]["rata_tahap"]["penugasan"] == round(21 / 24, 1)
    assert per["Rendah"]["total"] == 0 and set(per["Rendah"]["rata_tahap"].values()) == {None}


def test_durasi_tahap_fungsi_murni():
    t0 = wib(1, 8)
    # end before start (bad data) and a missing end are both left out
    hasil = durasi_tahap({MASUK: t0, "Disetujui": wib(1, 6), "Ditugaskan": wib(2, 8)})
    assert hasil["verifikasi"] is None
    assert hasil["penugasan"] == pytest.approx(26 / 24)
    assert hasil["inspeksi"] is None and hasil["perbaikan"] is None
    # Menunggu Inspeksi also ends verification; a later Ditugaskan (inspector replaced) counts as penugasan
    hasil = durasi_tahap({MASUK: t0, "Menunggu Inspeksi": wib(1, 20), "Ditugaskan": wib(2, 8)})
    assert hasil["verifikasi"] == pytest.approx(0.5) and hasil["penugasan"] == pytest.approx(0.5)


def test_selesai_tanpa_riwayat_selesai_memakai_tanggal_selesai(db_bersih):
    # old data: no "Selesai" history entry, only work_order.tanggal_selesai
    db = SessionLocal()
    try:
        db.query(RiwayatStatus).filter_by(id_work_order="REP-2026-00290", status="Selesai").delete()
        db.commit()
    finally:
        db.close()
    ubah_wo("REP-2026-00290", tanggal_selesai=wib(9, 9).replace(tzinfo=None))
    t = tiket(rekap(), "REP-2026-00290")
    assert t["_durasi_tahap_mentah"]["perbaikan"] == jam(24)
    assert t["durasi_hari"] == 4.0


def test_umur_tiket_aktif_dan_tahap_saat_ini(db_bersih):
    # REP-2026-00341: diterima 20/10 08:15 WIB, Disetujui 20/10 13:00 WIB
    data = rekap(sekarang=wib(22, 8, 15))
    t = tiket(data, "REP-2026-00341")
    assert t["umur_hari"] == 2.0
    assert t["tahap_saat_ini"] == "Menunggu Penugasan"
    assert t["lama_di_tahap_hari"] == round(43.25 / 24, 1)
    assert tiket(data, "REP-2026-00298")["tahap_saat_ini"] == "Inspeksi Lapangan"
    assert tiket(data, "REP-2026-00355")["tahap_saat_ini"] == "Menunggu Verifikasi"


def test_tiket_aktif_diurutkan_dari_yang_paling_lama(db_bersih):
    data = rekap(sekarang=wib(31, 12))
    # diterima: 00298 18/10, 00360 19/10, 00341 20/10, 00355 22/10; 00290 is Selesai
    assert [b["id_work_order"] for b in data["tiket_aktif"]] == \
        ["REP-2026-00298", "REP-2026-00360", "REP-2026-00341", "REP-2026-00355"]
    umur = [b["umur_hari"] for b in data["tiket_aktif"]]
    assert umur == sorted(umur, reverse=True)
    assert data["total"]["umur_tertua"] == umur[0]


def test_ringkasan_total(db_bersih):
    data = rekap(sekarang=wib(31, 12))
    total = data["total"]
    assert total["total"] == 5 and total["selesai"] == 1 and total["aktif"] == 4
    assert total["tingkat_penyelesaian"] == 20.0
    assert total["rata_durasi_hari"] == round(126 / 24, 1)
    assert total["risk_tertinggi"] == 8.4
    assert not any("sla" in kunci or "kepatuhan" in kunci for kunci in total)
    # sorted by risk, highest first
    assert data["tiket"][0]["id_work_order"] == "REP-2026-00341"


def test_wilayah_tanpa_tiket_tetap_tampil_dengan_nol(db_bersih):
    wonokromo = next(r for r in rekap()["per_wilayah"] if r["nama_wilayah"] == "Wonokromo")
    assert wonokromo["total"] == 0 and wonokromo["rata_durasi_hari"] is None
    assert set(wonokromo["rata_tahap"].values()) == {None}


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
    kolom = baris[0]
    assert kolom[:2] == ["Wilayah", "Total Tiket"]
    assert not any("SLA" in k for k in kolom)
    assert "Rata-rata Durasi Perbaikan (hari)" in kolom and "Rata-rata Umur Tiket Aktif (hari)" in kolom
    gubeng = next(b for b in baris if b[0] == "Wilayah Gubeng")
    assert gubeng[1] == "4"
    assert gubeng[kolom.index("Rata-rata Durasi Inspeksi Lapangan (hari)")] == "1.1"
    assert baris[-1][0] == "TOTAL" and baris[-1][1] == "5"


def test_unduh_csv_detail_tiket(db_bersih):
    r = klien(ADMIN).get("/laporan-kinerja/unduh?jenis=tiket")
    baris = baca_csv(r.content.decode("utf-8"))
    kolom = baris[0]
    assert kolom[0] == "ID Tiket"
    assert not any("SLA" in k for k in kolom)
    rep290 = next(b for b in baris if b[0] == "REP-2026-00290")
    assert rep290[kolom.index("Durasi Perbaikan (hari)")] == "2.2"
    assert rep290[kolom.index("Durasi Verifikasi (hari)")] == "0.2"
    assert rep290[kolom.index("Tahap Saat Ini")] == "Selesai"
    assert rep290[kolom.index("Umur Tiket Aktif (hari)")] == ""
    assert rep290[kolom.index("Selesai (WIB)")] == "10-10-2026 15:00"
    rep341 = next(b for b in baris if b[0] == "REP-2026-00341")
    assert rep341[kolom.index("Tahap Saat Ini")] == "Menunggu Penugasan"
    assert float(rep341[kolom.index("Umur Tiket Aktif (hari)")]) > 0
    assert rep341[kolom.index("Durasi Penugasan (hari)")] == ""


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


# ------------------------------------------------- Sprint 3 backlog 3: grafik
def test_data_grafik_sama_dengan_tabel(db_bersih):
    data = rekap(tanggal_mulai="2026-10-01", tanggal_akhir="2026-10-31")
    g = data["grafik"]
    assert g["prioritas"]["label"] == ["Urgent", "Tinggi", "Borderline", "Rendah"]
    assert g["prioritas"]["jumlah"] == [r["total"] for r in data["per_prioritas"]] == [2, 2, 1, 0]
    assert g["prioritas"]["warna"][0] == "#DC2626"
    assert g["wilayah"]["label"] == [r["nama_wilayah"] for r in data["per_wilayah"]]
    assert g["wilayah"]["total"] == [r["total"] for r in data["per_wilayah"]]
    assert [s + a for s, a in zip(g["wilayah"]["selesai"], g["wilayah"]["aktif"])] == g["wilayah"]["total"]
    assert g["tahap"]["hari"] == [data["total"]["rata_tahap"][kode] for kode, _ in data["tahap"]]
    assert sum(g["tren"]["masuk"]) == data["total"]["total"] == 5
    assert sum(g["tren"]["selesai"]) == data["total"]["selesai"] == 1


def test_tren_mingguan_per_minggu_senin_wib_tanpa_celah(db_bersih):
    tren = rekap(tanggal_mulai="2026-10-01", tanggal_akhir="2026-10-31")["grafik"]["tren"]
    # Seed (WIB): received 5 Oct, 18 Oct (a Sunday, so the week of Mon 12 Oct), 19, 20 and 22 Oct;
    # REP-2026-00290 completed 10 Oct.
    assert tren["label"] == ["05/10–11/10", "12/10–18/10", "19/10–25/10"]
    assert tren["masuk"] == [1, 1, 3]
    assert tren["selesai"] == [1, 0, 0]


def test_tren_mingguan_minggu_kosong_tetap_ada():
    from app.controllers.kontrol_laporan_kinerja import tren_mingguan
    b = [{"mulai": wib(1, 9), "status": "Selesai", "selesai": wib(20, 9)}]
    tren = tren_mingguan(b)
    assert len(tren["label"]) == 4  # weeks of 28 Sep, 5, 12, 19 Oct
    assert tren["masuk"] == [1, 0, 0, 0] and tren["selesai"] == [0, 0, 0, 1]
    assert tren_mingguan([]) == {"label": [], "masuk": [], "selesai": []}


def test_grafik_mengikuti_filter_wilayah(db_bersih):
    g = rekap(tanggal_mulai="2026-10-01", tanggal_akhir="2026-10-31", wilayah="WIL-02")["grafik"]
    assert g["wilayah"]["label"] == ["Wilayah Benowo"] and g["wilayah"]["total"] == [1]
    assert dict(zip(g["prioritas"]["label"], g["prioritas"]["jumlah"]))["Tinggi"] == 1


def test_periode_kosong_tanpa_grafik(db_bersih):
    assert rekap(tanggal_mulai="2025-01-01", tanggal_akhir="2025-01-31")["grafik"] is None
    html = klien(KABID).get("/laporan-kinerja?tanggal_mulai=2025-01-01&tanggal_akhir=2025-01-31").text
    assert "dataGrafikKinerja" not in html and "<canvas" not in html and "chart.js@" not in html


def test_halaman_memuat_grafik_dan_data_json(db_bersih):
    html = klien(KABID).get("/laporan-kinerja?tanggal_mulai=2026-10-01&tanggal_akhir=2026-10-31").text
    assert 'id="dataGrafikKinerja"' in html and html.count("<canvas") == 4
    for judul in ("Tren Tiket Masuk vs Selesai per Minggu", "Distribusi Prioritas",
                  "Rata-rata Durasi per Tahap", "Rekap per Wilayah"):
        assert f'data-grafik="{judul}"' in html


def test_tiket_ditutup_tidak_masuk_grafik(db_bersih):
    from app.controllers.kontrol_verifikasi import KontrolVerifikasi
    ubah_wo("REP-2026-00341", status_work_order="Dilaporkan")
    db = SessionLocal()
    try:
        assert KontrolVerifikasi(db).tolak_tiket("REP-2026-00341", "Laporan tidak valid", ADMIN)["success"]
    finally:
        db.close()
    data = rekap(tanggal_mulai="2026-10-01", tanggal_akhir="2026-10-31")
    g = data["grafik"]
    assert dict(zip(g["prioritas"]["label"], g["prioritas"]["jumlah"])) == {
        "Urgent": 1, "Tinggi": 2, "Borderline": 1, "Rendah": 0}
    assert sum(g["tren"]["masuk"]) == 4 and sum(g["tren"]["selesai"]) == 1
    assert data["total"]["tingkat_penyelesaian"] == 25.0
