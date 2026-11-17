"""Sprint 3 backlog 2: live notification badge, in-page toast and browser notification (UC-I).

The page polls GET /api/notifikasi/belum-dibaca every SCMS_POLL_NOTIF_DETIK seconds (1 s in tests,
see conftest.py). Browser notification permission cannot be granted from WebDriver in a portable
way, so the steps replace window.Notification with a recorder that has the wanted permission.
"""
import time

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when
from selenium.webdriver.common.by import By

from app.controllers.kontrol_penugasan import KontrolPenugasan
from app.database import SessionLocal
from app.main import app, interval_poll_notif
from app.models.entities import WorkOrder
from database.seed import seed_data

scenarios("../features/uc_i_push_notifikasi.feature")

ADMIN = "admin@dpupr.surabaya.go.id"
URL_API = "/api/notifikasi/belum-dibaca"


@pytest.fixture
def ctx(browser, live_server, login_as):
    # Leave any citizen page first: its 1-second polling must not run while seed_data() drops
    # and recreates the tables. Log in again afterwards instead of trusting the cached login.
    browser.get("about:blank")
    seed_data(verbose=False)
    login_as.reset()
    return {"browser": browser, "base": live_server, "login_as": login_as, "respons": None}


def _batas_tunggu() -> float:
    """'Within one polling interval': one interval plus time for the request and the page update."""
    return interval_poll_notif() + 4.0


def _tunggu(kondisi, pesan: str):
    akhir = time.time() + _batas_tunggu()
    while time.time() < akhir:
        nilai = kondisi()
        if nilai:
            return nilai
        time.sleep(0.2)
    raise AssertionError(pesan)


def _pasang_penanda(browser):
    """Marker that disappears if the page reloads, plus a collector for script errors."""
    browser.execute_script(
        "window.__tanpaMuatUlang = true;"
        "window.__galatSkrip = [];"
        "window.addEventListener('error', function (e) { window.__galatSkrip.push(String(e.message)); });"
        "window.addEventListener('unhandledrejection', function (e) { window.__galatSkrip.push(String(e.reason)); });")


# ------------------------------------------------------------------ given
@given(parsers.parse('the citizen "{no_hp}" is on the "{halaman}" page with notification badge "{jumlah}"'))
def warga_di_halaman_dengan_badge(ctx, no_hp, halaman, jumlah):
    warga_di_halaman(ctx, no_hp, halaman)
    assert ctx["browser"].find_element(By.ID, "badgeNotif").text.strip() == jumlah


@given(parsers.parse('the citizen "{no_hp}" is on the "{halaman}" page'))
def warga_di_halaman(ctx, no_hp, halaman):
    ctx["login_as"](no_hp)
    ctx["browser"].get(f"{ctx['base']}/{halaman}")
    assert ctx["browser"].find_element(By.ID, "menuNotifikasi")
    assert ctx["browser"].find_element(By.ID, "konfigNotifLangsung")
    _pasang_penanda(ctx["browser"])


@given(parsers.parse('the browser notification permission is "{izin}"'))
def izin_notifikasi_browser(ctx, izin):
    ctx["browser"].execute_script(
        "window.__notifBrowser = [];"
        "var Rekam = function (judul, opsi) { window.__notifBrowser.push({judul: judul, isi: (opsi || {}).body}); };"
        "Rekam.permission = arguments[0];"
        "Rekam.requestPermission = function () { return Promise.resolve(arguments[0]); };"
        "window.Notification = Rekam;", izin)


@given("I am not logged in")
def belum_login(ctx):
    ctx["klien"] = TestClient(app)


# ------------------------------------------------------------------- when
@when(parsers.parse('the admin assigns road inspector "{nama}" to ticket "{id_wo}"'))
def admin_menugaskan(ctx, nama, id_wo):
    # The citizen's browser stays on its page; the admin's action runs through the same controller
    # as the Work Order page, so it creates the notification through ubah_status().
    db = SessionLocal()
    try:
        wo = KontrolPenugasan(db).tugaskan_penilik(id_wo, nama)
        assert wo.status_work_order == "Ditugaskan", wo.status_work_order
        assert db.get(WorkOrder, id_wo).penilik.nama_penilik == nama
    finally:
        db.close()


@when("I request the unread notification count endpoint")
def minta_endpoint_anonim(ctx):
    ctx["respons"] = ctx["klien"].get(URL_API)


@when("the admin requests the unread notification count endpoint")
def admin_minta_endpoint(ctx):
    klien = TestClient(app)
    r = klien.post("/Login", data={"identifier": ADMIN, "password": "password123"}, follow_redirects=False)
    assert r.status_code == 303
    ctx["respons"] = klien.get(URL_API)


# ------------------------------------------------------------------- then
@then(parsers.parse('within one polling interval the notification badge shows "{jumlah}" without a page reload'))
def badge_berubah(ctx, jumlah):
    b = ctx["browser"]

    def badge():
        el = b.find_elements(By.ID, "badgeNotif")
        return el and el[0].text.strip() == jumlah
    b.implicitly_wait(0)
    try:
        _tunggu(badge, f'Badge tidak menjadi "{jumlah}"')
    finally:
        b.implicitly_wait(5)
    assert b.execute_script("return window.__tanpaMuatUlang === true;"), "halaman dimuat ulang"


@then(parsers.parse('a toast containing "{teks}" appears on the page'))
@then(parsers.parse('within one polling interval a toast containing "{teks}" appears on the page'))
def toast_muncul(ctx, teks):
    toast = ctx["browser"].find_element(By.ID, "toastNotif")
    _tunggu(lambda: toast.is_displayed() and teks in toast.text, f'Toast berisi "{teks}" tidak muncul')
    assert ctx["browser"].execute_script("return window.__tanpaMuatUlang === true;")


@then(parsers.parse('within one polling interval a browser notification with title "{judul}" is shown'))
def notifikasi_browser_tampil(ctx, judul):
    daftar = _tunggu(lambda: ctx["browser"].execute_script("return window.__notifBrowser;"),
                     "Tidak ada notifikasi browser")
    assert [n["judul"] for n in daftar] == [judul]
    assert "LAP-2026-0001" in daftar[0]["isi"]


@then("no browser notification is shown and no script error is logged")
def tanpa_notifikasi_browser(ctx):
    b = ctx["browser"]
    assert b.execute_script("return window.__notifBrowser;") == []
    assert b.execute_script("return window.__galatSkrip;") == []


@then(parsers.parse("the response status is {kode:d} and contains no notification data"))
def respons_tanpa_data(ctx, kode):
    r = ctx["respons"]
    assert r.status_code == kode
    data = r.json()
    assert "jumlah" not in data and "terbaru" not in data
    assert "LAP-" not in r.text and "NTF-" not in r.text


@then(parsers.parse("the response status is {kode:d}"))
def respons_kode(ctx, kode):
    assert ctx["respons"].status_code == kode
