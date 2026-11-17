"""Sprint 3 backlog 4: one ticket through every actor and status, end to end.

Each actor (citizen, Admin, Penilik Jalan, Kepala Bidang) logs in through POST /Login with
their own client and cookie, and every step uses the same web routes and form fields as the
pages. No status is prepared directly in the database; the database is only read to check the
results. The steps run without a browser, so the whole lifecycle stays fast and deterministic;
the browser behaviour of each feature is covered by its own Selenium scenarios.
"""
import io
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when

import app.services.penyimpanan as modul_penyimpanan
from app.database import SessionLocal
from app.main import app
from app.models.entities import Laporan, Notifikasi, Rating, RiwayatStatus, Warga, WorkOrder
from app.services.alur_status import PESAN_NOTIFIKASI
from database.seed import seed_data

scenarios("../features/integrasi_alur_penuh.feature")

ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"
WIB = timezone(timedelta(hours=7))

# Report locations, each more than 1 km from every seed ticket (no BR-3 merge).
LOKASI = {
    "Jl. Kalijudan No. 99, Surabaya": (-7.2560, 112.7950),
    "Jl. Kertajaya Indah No. 7, Surabaya": (-7.2830, 112.7820),
}


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (100, 100, 100)).save(buf, "JPEG")
    return buf.getvalue()


def _klien(identifier: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/Login", data={"identifier": identifier, "password": "password123"}, follow_redirects=False)
    assert r.status_code == 303 and "/Login" not in r.headers["location"], f"login gagal: {identifier}"
    return c


def _db(fungsi):
    db = SessionLocal()
    try:
        return fungsi(db)
    finally:
        db.close()


def _redirect_ok(r, aksi: str):
    """Form actions answer with a redirect (post-redirect-get); a 200 means the form was rejected."""
    assert r.status_code == 303, f"{aksi}: {r.status_code} {r.text[:300]}"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(modul_penyimpanan, "DIREKTORI_UNGGAHAN", tmp_path)
    return {"klien": {}}


def _aktor(ctx, identifier: str) -> TestClient:
    if identifier not in ctx["klien"]:
        ctx["klien"][identifier] = _klien(identifier)
    return ctx["klien"][identifier]


def _wo(ctx) -> WorkOrder:
    return _db(lambda db: db.get(WorkOrder, ctx["id_wo"]))


def _jumlah_belum_dibaca(ctx) -> int:
    r = _aktor(ctx, ctx["warga"]).get("/api/notifikasi/belum-dibaca")
    assert r.status_code == 200
    return r.json()["jumlah"]


def _hari_ini_wib() -> str:
    return datetime.now(WIB).date().isoformat()


def _laporan_kinerja_hari_ini(ctx) -> str:
    hari = _hari_ini_wib()
    r = _aktor(ctx, KABID).get("/laporan-kinerja", params={"tanggal_mulai": hari, "tanggal_akhir": hari})
    assert r.status_code == 200
    return r.text


# ------------------------------------------------------------------ given
@given("the demo data is loaded")
def data_demo():
    seed_data(verbose=False)


# ------------------------------------------------------------------- when
@when(parsers.parse('the citizen "{no_hp}" submits a report with photo "{foto}" at "{lokasi}"'))
def warga_melapor(ctx, no_hp, foto, lokasi):
    ctx["warga"] = no_hp
    ctx["id_warga"] = _db(lambda db: db.query(Warga).filter_by(no_hp=no_hp).one().id_warga)
    ctx["notif_awal"] = _jumlah_belum_dibaca(ctx)
    sebelum = _db(lambda db: {lap.id_laporan for lap in db.query(Laporan).filter_by(id_warga=ctx["id_warga"])})
    lat, lng = LOKASI[lokasi]
    r = _aktor(ctx, no_hp).post("/lapor", data={
        "lokasi_jalan": lokasi, "latitude": lat, "longitude": lng,
        "deskripsi": "Kerusakan jalan cukup parah, membahayakan pengendara motor",
        "kategori_pilihan": "Retak Permukaan" if "retak" in foto else "Jalan Berlubang",
        "id_wilayah": "WIL-01",
    }, files={"foto": (foto, _jpeg(), "image/jpeg")}, follow_redirects=False)
    _redirect_ok(r, "kirim laporan")
    baru = _db(lambda db: [lap for lap in db.query(Laporan).filter_by(id_warga=ctx["id_warga"])
                           if lap.id_laporan not in sebelum])
    assert len(baru) == 1, "laporan baru tidak tercatat"
    ctx["id_laporan"], ctx["id_wo"] = baru[0].id_laporan, baru[0].id_work_order


@when("the admin approves the new ticket")
def admin_menyetujui(ctx):
    _redirect_ok(_aktor(ctx, ADMIN).post(f"/verifikasi/{ctx['id_wo']}/approve", follow_redirects=False), "setujui")


@when(parsers.parse('the admin assigns road inspector "{nama}" to the new ticket'))
def admin_menugaskan(ctx, nama):
    r = _aktor(ctx, ADMIN).post(f"/work-orders/{ctx['id_wo']}/assign", data={"nama_penilik": nama},
                                follow_redirects=False)
    _redirect_ok(r, "tugaskan penilik")
    assert _db(lambda db: db.get(WorkOrder, ctx["id_wo"]).penilik.nama_penilik) == nama


@when(parsers.parse('the inspector saves the inspection with damage level "{tingkat}" and recommendation "{rekomendasi}"'))
def penilik_inspeksi(ctx, tingkat, rekomendasi):
    ctx["risk_sebelum"] = _wo(ctx).risk_score
    r = _aktor(ctx, PENILIK).post(f"/TugasLapangan/{ctx['id_wo']}/inspeksi", data={
        "dimensi_kerusakan": "1.5m x 1m x 0.1m", "catatan_teknis": "Lapisan aspal terkelupas di jalur kiri",
        "rekomendasi": rekomendasi, "tingkat_kerusakan": tingkat, "kategori_terkonfirmasi": "Jalan Berlubang",
    }, files={"foto_survei": ("survei.jpg", _jpeg(), "image/jpeg")}, follow_redirects=False)
    _redirect_ok(r, "simpan inspeksi")


@when(parsers.parse('the admin issues SPK "{nomor}" to team "{tim}"'))
def admin_spk(ctx, nomor, tim):
    r = _aktor(ctx, ADMIN).post(f"/work-orders/{ctx['id_wo']}/spk", data={"nomor_spk": nomor, "tim_pelaksana": tim},
                                follow_redirects=False)
    _redirect_ok(r, "terbitkan SPK")
    assert _wo(ctx).nomor_spk == nomor


@when("the inspector completes the repair with a proof photo")
def penilik_selesai(ctx):
    r = _aktor(ctx, PENILIK).post(f"/TugasLapangan/{ctx['id_wo']}/progres", data={
        "status_baru": "Selesai", "catatan_progres": "Lubang ditambal hotmix dan dipadatkan",
    }, files={"foto_selesai": ("selesai.jpg", _jpeg(), "image/jpeg")}, follow_redirects=False)
    _redirect_ok(r, "perbaikan selesai")


@when(parsers.parse('the citizen rates the repair {bintang:d} stars with review "{ulasan}"'))
def warga_menilai(ctx, bintang, ulasan):
    r = _aktor(ctx, ctx["warga"]).post(f"/lacak/{ctx['id_laporan']}/rating",
                                       data={"nilai_bintang": str(bintang), "komentar": ulasan}, follow_redirects=False)
    _redirect_ok(r, "beri rating")
    ctx["rating"] = (bintang, ulasan)


@when(parsers.parse('the admin rejects the new ticket with reason "{alasan}"'))
def admin_menolak(ctx, alasan):
    r = _aktor(ctx, ADMIN).post(f"/verifikasi/{ctx['id_wo']}/reject", data={"alasan_tutup": alasan},
                                follow_redirects=False)
    _redirect_ok(r, "tolak laporan")


# ------------------------------------------------------------------- then
@then(parsers.parse('a new ticket is created with status "{status}" and priority "{prioritas}"'))
def tiket_baru(ctx, status, prioritas):
    wo = _wo(ctx)
    assert (wo.status_work_order, wo.prioritas) == (status, prioritas)
    assert wo.id_wilayah == "WIL-01" and wo.exposure_count == 1


@then(parsers.parse("the citizen sees the unread notification count go up by {n:d}"))
def notif_naik(ctx, n):
    assert _jumlah_belum_dibaca(ctx) == ctx["notif_awal"] + n


@then(parsers.parse('the ticket status is "{status}"'))
def status_tiket(ctx, status):
    assert _wo(ctx).status_work_order == status
    # every citizen-facing page agrees with the database
    html = _aktor(ctx, ctx["warga"]).get("/lacak", params={"id": ctx["id_laporan"]}).text
    assert status in html


@then(parsers.parse('the ticket status is "{status}" and its Risk Score is recalculated to {skor:f} "{prioritas}"'))
def status_dan_risk(ctx, status, skor, prioritas):
    status_tiket(ctx, status)
    wo = _wo(ctx)
    assert (wo.risk_score, wo.prioritas) == (skor, prioritas)
    assert wo.risk_score != ctx["risk_sebelum"]
    catatan = _db(lambda db: [r.keterangan or "" for r in db.query(RiwayatStatus).filter_by(id_work_order=wo.id_work_order)])
    assert any(f"Risk Score diperbarui {ctx['risk_sebelum']} → {skor}" in k for k in catatan), catatan


@then("the citizen's timeline shows every stage as done")
def linimasa_lengkap(ctx):
    from app.controllers.kontrol_lacak import KontrolLacak
    detail = _db(lambda db: KontrolLacak(db).detail_lacak(ctx["id_laporan"], ctx["id_warga"]))
    assert detail["success"]
    assert [t["selesai"] for t in detail["tahapan"]] == [True] * len(detail["tahapan"])
    assert detail["boleh_rating"] is True


@then("the citizen received exactly one notification for each status change")
def satu_notifikasi_per_perubahan(ctx):
    judul = _db(lambda db: Counter(n.judul for n in db.query(Notifikasi).filter_by(id_laporan=ctx["id_laporan"])))
    harapan = Counter(["Laporan diterima"] + [PESAN_NOTIFIKASI[s][0] for s in
                                              ("Disetujui", "Ditugaskan", "Terinspeksi", "Dalam Proses", "Selesai")])
    assert judul == harapan, judul


@then("every notification was delivered")
def semua_terkirim(ctx):
    status = _db(lambda db: {n.status_kirim for n in db.query(Notifikasi).filter_by(id_laporan=ctx["id_laporan"])})
    assert status == {"Terkirim"}
    assert ctx["id_laporan"] not in _aktor(ctx, ADMIN).get("/notifikasi-gagal").text


@then("the rating is saved and the report can no longer be rated")
def rating_tersimpan(ctx):
    rating = _db(lambda db: db.query(Rating).filter_by(id_laporan=ctx["id_laporan"]).one())
    assert (rating.nilai_bintang, rating.komentar) == ctx["rating"]
    r = _aktor(ctx, ctx["warga"]).post(f"/lacak/{ctx['id_laporan']}/rating",
                                       data={"nilai_bintang": "1", "komentar": "ulang"}, follow_redirects=False)
    assert r.status_code != 303
    assert _db(lambda db: db.query(Rating).filter_by(id_laporan=ctx["id_laporan"]).count()) == 1


@then(parsers.parse("the performance report for today counts {masuk:d} incoming and {selesai:d} completed ticket in its charts and tables"))
def laporan_kinerja_selesai(ctx, masuk, selesai):
    html = _laporan_kinerja_hari_ini(ctx)
    grafik = json.loads(re.search(r'id="dataGrafikKinerja">(.*?)</script>', html, re.S).group(1))
    assert (sum(grafik["tren"]["masuk"]), sum(grafik["tren"]["selesai"])) == (masuk, selesai)
    assert dict(zip(grafik["prioritas"]["label"], grafik["prioritas"]["jumlah"]))[_wo(ctx).prioritas] == 1
    assert f'data-tiket="{ctx["id_wo"]}"' in html
    assert re.search(r'id="kpiTotal"[^>]*>\s*1\s*<', html)


@then(parsers.parse('the citizen\'s newest notification mentions "{teks}"'))
def notifikasi_terbaru(ctx, teks):
    terbaru = _aktor(ctx, ctx["warga"]).get("/api/notifikasi/belum-dibaca").json()["terbaru"][0]
    assert terbaru["id_laporan"] == ctx["id_laporan"]
    assert teks in terbaru["pesan"]


@then("the citizen cannot rate the closed report")
def tidak_bisa_rating(ctx):
    r = _aktor(ctx, ctx["warga"]).post(f"/lacak/{ctx['id_laporan']}/rating",
                                       data={"nilai_bintang": "5", "komentar": "coba"}, follow_redirects=False)
    assert r.status_code != 303
    assert "tidak dapat dinilai" in r.text
    assert _db(lambda db: db.query(Rating).filter_by(id_laporan=ctx["id_laporan"]).count()) == 0


@then(parsers.parse('the performance report for today lists the ticket under closed reason "{alasan}" without charts'))
def laporan_kinerja_ditutup(ctx, alasan):
    html = _laporan_kinerja_hari_ini(ctx)
    assert 'id="dataGrafikKinerja"' not in html
    baris = re.search(rf'data-alasan="{re.escape(alasan)}">.*?data-kolom="jumlah">(\d+)<', html, re.S)
    assert baris and baris.group(1) == "1"
    assert ctx["id_wo"] in html
