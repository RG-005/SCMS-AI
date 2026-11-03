"""UC-D: Admin mengelola data master Penilik Jalan."""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from app.database import SessionLocal
from app.models.entities import PenilikJalan
from database.seed import seed_data

scenarios("../features/uc_d_kelola_master_data.feature")

TOMBOL = {"Simpan Data": "simpanPenilik"}


@pytest.fixture
def ctx(browser, live_server, login_as):
    seed_data(verbose=False)
    login_as("admin@dpupr.surabaya.go.id")
    return {"browser": browser, "base": live_server, "nip": None, "jumlah_awal": _jumlah_penilik()}


def _jumlah_penilik(nip=None):
    db = SessionLocal()
    try:
        q = db.query(PenilikJalan)
        return (q.filter_by(nip=nip) if nip else q).count()
    finally:
        db.close()


@given(parsers.parse('the admin opens the "{halaman}" page'))
def buka_master(ctx, halaman):
    ctx["browser"].get(f"{ctx['base']}/master-data")
    assert halaman in ctx["browser"].find_element(By.TAG_NAME, "body").text


@given(parsers.parse('NIP "{nip}" is already registered in the system'))
def nip_terdaftar(ctx, nip):
    assert _jumlah_penilik(nip) == 1


def _isi(ctx, element_id, nilai):
    el = ctx["browser"].find_element(By.ID, element_id)
    el.clear()
    el.send_keys(nilai)


@when(parsers.parse('the admin inputs NIP "{nip}", name "{nama}", and selects region "{wilayah}"'))
def isi_form_penilik(ctx, pilih_opsi, nip, nama, wilayah):
    ctx.update(nip=nip, nama=nama)
    _isi(ctx, "nip", nip)
    _isi(ctx, "nama_penilik", nama)
    pilih_opsi("id_wilayah_penilik", wilayah)


@when(parsers.parse('the admin enters NIP "{nip}" on the add Road Inspector form'))
def isi_nip_saja(ctx, nip):
    ctx["nip"] = nip
    _isi(ctx, "nip", nip)


@when(parsers.parse('the admin clicks the "{tombol}" button'))
def klik(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, TOMBOL[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


@then("the system saves the new Road Inspector data to the database")
def tersimpan(ctx):
    db = SessionLocal()
    try:
        p = db.query(PenilikJalan).filter_by(nip=ctx["nip"]).one()
        assert p.nama_penilik == ctx["nama"]
        assert p.id_wilayah == "WIL-01"  # Wilayah Gubeng
        assert p.status_ketersediaan == "Tersedia"
    finally:
        db.close()
    assert _jumlah_penilik() == ctx["jumlah_awal"] + 1


@then(parsers.parse('the system displays a confirmation message "{pesan}"'))
def pesan_konfirmasi(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan


@then("the system rejects saving the master data")
def ditolak(ctx):
    assert _jumlah_penilik(ctx["nip"]) == 1
    assert _jumlah_penilik() == ctx["jumlah_awal"]


@then(parsers.parse('the system displays an error message "{pesan}"'))
def pesan_error(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan
