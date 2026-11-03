"""UC-C: Warga melacak status & linimasa laporan melalui halaman Riwayat & Lacak Laporan."""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from app.database import SessionLocal
from app.models.entities import Laporan
from database.seed import seed_data

scenarios("../features/uc_c_lacak_status.feature")

WARGA = "0812xxxxxxx"


@pytest.fixture
def ctx(browser, live_server, login_as):
    seed_data(verbose=False)
    login_as(WARGA)
    return {"browser": browser, "base": live_server}


def _buka_lacak(ctx):
    ctx["browser"].get(f"{ctx['base']}/lacak")


@given(parsers.parse('the citizen has accessed the "{halaman}" page'))
def buka_halaman_lacak(ctx, halaman):
    _buka_lacak(ctx)
    assert halaman in ctx["browser"].find_element(By.TAG_NAME, "body").text


@given("the citizen is on the report tracking page")
def di_halaman_lacak(ctx):
    _buka_lacak(ctx)
    assert ctx["browser"].find_element(By.ID, "cari_id")


@given(parsers.parse('a registered report with ID "{id_laporan}" exists for the citizen'))
def laporan_milik_warga(ctx, id_laporan):
    db = SessionLocal()
    try:
        lap = db.get(Laporan, id_laporan)
        assert lap is not None and lap.id_warga == "USR-01"
    finally:
        db.close()


def _cari(ctx, id_laporan, klik_dan_tunggu):
    kolom = ctx["browser"].find_element(By.ID, "cari_id")
    kolom.clear()
    kolom.send_keys(id_laporan)
    klik_dan_tunggu(ctx["browser"].find_element(By.ID, "tombolCari"))


@when(parsers.parse('the citizen searches for report ID "{id_laporan}"'))
def cari_laporan(ctx, klik_dan_tunggu, id_laporan):
    _cari(ctx, id_laporan, klik_dan_tunggu)


@when(parsers.parse('the citizen enters unregistered report ID "{id_laporan}"'))
def cari_laporan_tidak_ada(ctx, klik_dan_tunggu, id_laporan):
    _cari(ctx, id_laporan, klik_dan_tunggu)


@then("the system displays the report details along with the AI severity score and priority level")
def tampil_detail(ctx):
    b = ctx["browser"]
    assert b.find_element(By.ID, "detailLaporan")
    assert b.find_element(By.ID, "skorSeverity").text.strip() == "8.4 / 10"
    assert b.find_element(By.ID, "prioritasLaporan").text.strip() == "Urgent"


@then(parsers.parse('the system displays the current progress timeline for report "{id_laporan}"'))
def tampil_linimasa(ctx, id_laporan):
    sumber = ctx["browser"].page_source
    assert id_laporan in sumber
    assert 'id="linimasa"' in sumber
    # Seeded ticket was reported and approved: the first two stages are done
    assert sumber.count("tahap-selesai") == 2
    assert "Disetujui oleh Admin" in ctx["browser"].find_element(By.ID, "riwayatStatus").text


@then("the system rejects the search")
def pencarian_ditolak(ctx):
    assert 'id="detailLaporan"' not in ctx["browser"].page_source


@then(parsers.parse('the system displays an error message "{pesan}"'))
def pesan_error(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanCari").text.strip() == pesan
