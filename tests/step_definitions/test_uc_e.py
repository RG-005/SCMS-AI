"""UC-E: Penilik Jalan mencatat hasil inspeksi lapangan."""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from app.database import SessionLocal
from app.models.entities import Inspeksi, Laporan, Notifikasi
from database.seed import seed_data

scenarios("../features/uc_e_inspeksi_lapangan.feature")

TOMBOL = {"Simpan Hasil Inspeksi": "simpanInspeksi"}


@pytest.fixture
def ctx(browser, live_server, login_as, alur):
    seed_data(verbose=False)
    login_as("budi.santoso@dpupr.surabaya.go.id")
    return {"browser": browser, "base": live_server, "alur": alur}


def _isi(ctx, element_id, nilai):
    el = ctx["browser"].find_element(By.ID, element_id)
    el.clear()
    if nilai:
        el.send_keys(nilai)


@given(parsers.parse('the road inspector opens report details for "{id_laporan}" with status "{status}"'))
def buka_detail(ctx, id_laporan, status):
    assert ctx["alur"]["status"](id_laporan) == status
    ctx["id_laporan"] = id_laporan
    ctx["id_wo"] = ctx["alur"]["id_wo"](id_laporan)
    ctx["browser"].get(f"{ctx['base']}/TugasLapangan/{ctx['id_wo']}")
    assert id_laporan in ctx["browser"].page_source
    assert ctx["browser"].find_element(By.ID, "formInspeksi")


@when(parsers.parse('the road inspector inputs damage dimensions "{dimensi}"'))
def isi_dimensi(ctx, dimensi):
    ctx["dimensi"] = dimensi
    _isi(ctx, "dimensi_kerusakan", dimensi)


@when(parsers.parse('the road inspector inputs technical notes "{catatan}"'))
def isi_catatan(ctx, catatan):
    _isi(ctx, "catatan_teknis", catatan)


@when(parsers.parse('the road inspector selects treatment recommendation "{rekomendasi}" and uploads survey photo "{foto}"'))
def pilih_rekomendasi_dan_foto(ctx, pilih_opsi, foto_uji, rekomendasi, foto):
    ctx["rekomendasi"] = rekomendasi
    pilih_opsi("rekomendasi", rekomendasi)
    ctx["browser"].find_element(By.ID, "foto_survei").send_keys(foto_uji(foto))


@when("the road inspector leaves mandatory fields like damage dimensions or recommendations blank")
def kosongkan(ctx, pilih_opsi):
    _isi(ctx, "dimensi_kerusakan", "")
    pilih_opsi("rekomendasi", "— Pilih rekomendasi —")


@when(parsers.parse('the road inspector clicks the "{tombol}" button'))
def klik(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, TOMBOL[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


def _inspeksi(ctx):
    db = SessionLocal()
    try:
        return db.query(Inspeksi).filter_by(id_work_order=ctx["id_wo"]).all()
    finally:
        db.close()


@then("the system saves the data to the Inspection table")
def tersimpan(ctx):
    data = _inspeksi(ctx)
    assert len(data) == 1
    ins = data[0]
    assert (ins.dimensi_kerusakan, ins.rekomendasi_penanganan, ins.id_penilik) == (ctx["dimensi"], ctx["rekomendasi"], "PNL-01")
    assert ins.url_foto_temuan and ins.url_foto_temuan.startswith("static/uploads/")


@then(parsers.parse('the system updates the report status of "{id_laporan}" to "{status}"'))
def status_laporan(ctx, id_laporan, status):
    db = SessionLocal()
    try:
        assert db.get(Laporan, id_laporan).status == status
    finally:
        db.close()
    assert ctx["alur"]["status"](id_laporan) == status
    assert "Hasil inspeksi berhasil disimpan" in ctx["browser"].page_source


@then("the system generates an automatic notification for the reporting citizen")
def notifikasi(ctx):
    db = SessionLocal()
    try:
        n = db.query(Notifikasi).filter_by(id_laporan=ctx["id_laporan"], id_warga="USR-01",
                                           judul="Laporan telah disurvei", status_baca=False).all()
        assert len(n) == 1
    finally:
        db.close()


@then("the system aborts saving the inspection data")
def batal(ctx):
    assert _inspeksi(ctx) == []
    assert ctx["alur"]["status"](ctx["id_laporan"]) == "Disetujui"


@then(parsers.parse('the system displays a warning message "{pesan}"'))
def peringatan(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan
