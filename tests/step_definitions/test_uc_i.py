"""UC-I: Warga membuka notifikasi dan diarahkan ke progres laporan."""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from app.database import SessionLocal
from app.models.entities import Notifikasi
from database.seed import seed_data

scenarios("../features/uc_i_notifikasi_status.feature")


@pytest.fixture
def ctx(browser, live_server, login_as):
    seed_data(verbose=False)
    login_as("0812xxxxxxx")
    return {"browser": browser, "base": live_server}


@given(parsers.parse('the citizen has a new unread notification for report "{id_laporan}"'))
def ada_notif_baru(ctx, id_laporan):
    db = SessionLocal()
    try:
        n = (db.query(Notifikasi).filter_by(id_laporan=id_laporan, id_warga="USR-01", status_baca=False)
             .order_by(Notifikasi.waktu_kirim.desc()).first())
        assert n is not None
        ctx.update(id_notif=n.id_notifikasi, id_laporan=id_laporan)
    finally:
        db.close()
    ctx["browser"].get(f"{ctx['base']}/Beranda")


@when(parsers.parse('the citizen opens the "{menu}" menu and clicks the unread notification item'))
def buka_notif(ctx, klik_dan_tunggu, menu):
    b = ctx["browser"]
    tautan_menu = b.find_element(By.ID, "menuNotifikasi")
    assert menu in tautan_menu.text
    klik_dan_tunggu(tautan_menu)
    item = b.find_element(By.ID, f"notif-{ctx['id_notif']}")
    assert "notif-belum-dibaca" in item.get_attribute("class")
    klik_dan_tunggu(item)


@then("the system updates the notification read status to read")
def sudah_dibaca(ctx):
    db = SessionLocal()
    try:
        assert db.get(Notifikasi, ctx["id_notif"]).status_baca is True
    finally:
        db.close()


@then(parsers.parse('the system redirects the citizen to the detail progress page of report "{id_laporan}"'))
def diarahkan(ctx, id_laporan):
    b = ctx["browser"]
    assert f"/lacak?id={id_laporan}" in b.current_url
    assert b.find_element(By.ID, "detailLaporan")
    assert id_laporan in b.page_source
