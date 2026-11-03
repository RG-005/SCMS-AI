"""UC-F: Admin menerbitkan SPK, petugas memperbarui status perbaikan sampai Selesai."""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from app.database import SessionLocal
from app.models.entities import Laporan, Notifikasi, Perbaikan, WorkOrder
from database.seed import seed_data

scenarios("../features/uc_f_update_perbaikan.feature")

TOMBOL = {"Perbarui Status Penanganan": "perbaruiStatus"}


@pytest.fixture
def ctx(browser, live_server, login_as, alur):
    seed_data(verbose=False)
    return {"browser": browser, "base": live_server, "alur": alur, "login_as": login_as}


def _isi(ctx, element_id, nilai):
    el = ctx["browser"].find_element(By.ID, element_id)
    el.clear()
    el.send_keys(nilai)


@given(parsers.parse('report "{id_laporan}" has the status "{status}"'))
def laporan_berstatus(ctx, id_laporan, status):
    ctx["alur"][status](id_laporan)
    assert ctx["alur"]["status"](id_laporan) == status
    ctx.update(id_laporan=id_laporan, id_wo=ctx["alur"]["id_wo"](id_laporan))
    ctx["login_as"]("admin@dpupr.surabaya.go.id")
    ctx["browser"].get(f"{ctx['base']}/work-orders?select_ticket={ctx['id_wo']}")


@given(parsers.parse('report "{id_laporan}" is in "{status}" status on the active Work Order list'))
def laporan_dalam_daftar_aktif(ctx, id_laporan, status):
    ctx["alur"][status](id_laporan)
    ctx.update(id_laporan=id_laporan, id_wo=ctx["alur"]["id_wo"](id_laporan))
    ctx["login_as"]("budi.santoso@dpupr.surabaya.go.id")
    ctx["browser"].get(f"{ctx['base']}/TugasLapangan")
    assert ctx["id_wo"] in ctx["browser"].find_element(By.ID, "daftarPerbaikan").text
    ctx["browser"].get(f"{ctx['base']}/TugasLapangan/{ctx['id_wo']}")
    assert ctx["browser"].find_element(By.ID, "formProgres")


@when(parsers.parse('the admin issues a Work Order with SPK number "{nomor}" and team "{tim}"'))
def isi_spk(ctx, nomor, tim):
    ctx.update(nomor_spk=nomor, tim=tim)
    _isi(ctx, "nomor_spk", nomor)
    _isi(ctx, "tim_pelaksana", tim)


@when(parsers.parse('the admin selects the progress status "{status}"'))
def pilih_status_spk(ctx, pilih_opsi, klik_dan_tunggu, status):
    pilih_opsi("status_awal", status)
    klik_dan_tunggu(ctx["browser"].find_element(By.ID, "terbitkanSpk"))


@when(parsers.parse('the officer selects progress status "{status}"'))
def pilih_status(ctx, pilih_opsi, status):
    pilih_opsi("status_baru", status)


@when(parsers.parse('the officer selects progress status "{status}" without uploading a repair proof photo file'))
def pilih_status_tanpa_foto(ctx, pilih_opsi, status):
    pilih_opsi("status_baru", status)
    _isi(ctx, "catatan_progres", "Sudah selesai")


@when(parsers.parse('the officer inputs completion notes "{catatan}"'))
def isi_catatan(ctx, catatan):
    _isi(ctx, "catatan_progres", catatan)
    ctx["catatan"] = catatan


@when(parsers.parse('the officer uploads repair proof photo "{foto}"'))
def unggah_foto(ctx, foto_uji, foto):
    ctx["browser"].find_element(By.ID, "foto_selesai").send_keys(foto_uji(foto))


@when(parsers.parse('the officer clicks the "{tombol}" button'))
def klik(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, TOMBOL[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


def _wo(ctx):
    db = SessionLocal()
    try:
        return db.get(WorkOrder, ctx["id_wo"])
    finally:
        db.close()


def _status_laporan(id_laporan):
    db = SessionLocal()
    try:
        return db.get(Laporan, id_laporan).status
    finally:
        db.close()


def _notif(ctx, judul):
    db = SessionLocal()
    try:
        return db.query(Notifikasi).filter_by(id_laporan=ctx["id_laporan"], judul=judul).count()
    finally:
        db.close()


@then("the system saves the data to the WorkOrder table")
def spk_tersimpan(ctx):
    wo = _wo(ctx)
    assert (wo.nomor_spk, wo.tim_pelaksana) == (ctx["nomor_spk"], ctx["tim"])


@then(parsers.parse('the system updates the status of report "{id_laporan}" to "{status}"'))
def status_laporan(ctx, id_laporan, status):
    assert _wo(ctx).status_work_order == status
    assert _status_laporan(id_laporan) == status


@then("the system sends a status update notification to the reporting citizen")
def notif_proses(ctx):
    assert _notif(ctx, "Perbaikan dimulai") == 1


@then(parsers.parse('the system updates the WorkOrder status and report status of "{id_laporan}" to "{status}"'))
def status_selesai(ctx, id_laporan, status):
    wo = _wo(ctx)
    assert wo.status_work_order == status and wo.tanggal_selesai is not None
    assert _status_laporan(id_laporan) == status
    db = SessionLocal()
    try:
        bukti = db.query(Perbaikan).filter_by(id_work_order=ctx["id_wo"], status_perbaikan="Selesai").one()
        assert bukti.foto_sesudah and bukti.catatan == ctx["catatan"]
    finally:
        db.close()


@then("the system sends a completion notification to the reporting citizen")
def notif_selesai(ctx):
    assert _notif(ctx, "Perbaikan selesai") == 1


@then("the system rejects the WorkOrder status update")
def ditolak(ctx):
    assert _wo(ctx).status_work_order == "Dalam Proses"
    assert _notif(ctx, "Perbaikan selesai") == 0


@then(parsers.parse('the system displays an error message "{pesan}"'))
def pesan_error(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan
