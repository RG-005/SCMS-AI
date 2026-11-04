"""UC-L: Kepala Bidang melihat dan mengunduh Laporan Kinerja Infrastruktur."""
import csv
import io

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from database.seed import seed_data

scenarios("../features/uc_l_laporan_kinerja.feature")

AKUN_KABID = "kabid@dpupr.surabaya.go.id"
TOMBOL_UNDUH = {"Unduh Rekap Wilayah (CSV)": "unduhWilayah", "Unduh Detail Tiket (CSV)": "unduhTiket"}


@pytest.fixture
def ctx(browser, live_server, login_as):
    seed_data(verbose=False)
    login_as(AKUN_KABID)
    return {"browser": browser, "base": live_server, "csv": None}


def _teks(browser) -> str:
    return browser.find_element(By.TAG_NAME, "body").text


@given(parsers.parse('the head of division opens the "{halaman}" page'))
def buka_laporan_kinerja(ctx, halaman):
    ctx["browser"].get(f"{ctx['base']}/laporan-kinerja")
    assert halaman in _teks(ctx["browser"])


@when(parsers.parse('the head of division selects the period "{mulai}" to "{akhir}" and region "{wilayah}"'))
def pilih_periode(ctx, pilih_opsi, mulai, akhir, wilayah):
    # <input type="date"> typing depends on the browser locale, so set the ISO value directly
    for element_id, nilai in (("tanggal_mulai", mulai), ("tanggal_akhir", akhir)):
        ctx["browser"].execute_script("document.getElementById(arguments[0]).value = arguments[1];", element_id, nilai)
    pilih_opsi("filter_wilayah", wilayah)


@when(parsers.parse('the head of division clicks the "{tombol}" button'))
def klik_tampilkan(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, "tampilkanLaporan")
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


@then(parsers.parse('the system displays the performance recap for region "{wilayah}" with {jumlah:d} tickets'))
def rekap_wilayah_tampil(ctx, wilayah, jumlah):
    baris = ctx["browser"].find_element(By.CSS_SELECTOR, f'#tabelWilayah tr[data-wilayah="{wilayah}"]')
    sel = baris.find_elements(By.TAG_NAME, "td")
    assert sel[0].text.strip() == wilayah
    assert int(sel[1].text) == jumlah
    assert baris.find_element(By.CSS_SELECTOR, '[data-kolom="kepatuhan"]').text.strip()


@then(parsers.parse('the SLA status of ticket "{id_tiket}" is "{status_sla}"'))
def status_sla_tiket(ctx, id_tiket, status_sla):
    baris = ctx["browser"].find_element(By.CSS_SELECTOR, f'#tabelTiket tr[data-tiket="{id_tiket}"]')
    assert baris.find_element(By.CSS_SELECTOR, '[data-kolom="status-sla"]').text.strip() == status_sla


@when(parsers.parse('the head of division downloads the "{tombol}" file'))
def unduh_csv(ctx, tombol):
    link = ctx["browser"].find_element(By.ID, TOMBOL_UNDUH[tombol])
    assert link.text.strip() == tombol
    # Fetch the link's target with the logged-in browser session instead of saving to disk.
    hasil = ctx["browser"].execute_async_script(
        "var selesai = arguments[arguments.length - 1];"
        "fetch(arguments[0], {credentials: 'same-origin'})"
        "  .then(r => r.text().then(t => selesai({status: r.status, type: r.headers.get('content-type'),"
        "                                         disposition: r.headers.get('content-disposition'), body: t})))"
        "  .catch(e => selesai({status: 0, body: String(e)}));",
        link.get_attribute("href"))
    assert hasil["status"] == 200, hasil
    assert hasil["type"].startswith("text/csv")
    assert "attachment" in hasil["disposition"] and ".csv" in hasil["disposition"]
    ctx["csv"] = hasil["body"]


@then(parsers.parse('the downloaded CSV file contains the recap row of "{wilayah}"'))
def csv_berisi_wilayah(ctx, wilayah):
    baris = list(csv.reader(io.StringIO(ctx["csv"].lstrip("﻿"))))
    assert baris[0][0] == "Wilayah" and "Kepatuhan SLA (%)" in baris[0]
    assert any(r and r[0] == wilayah for r in baris[1:])
    assert baris[-1][0] == "TOTAL"


@then(parsers.parse('the system displays the message "{pesan}"'))
def pesan_kosong(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanKosong").text.strip() == pesan


@then("the download buttons are not shown")
def tombol_unduh_tidak_ada(ctx):
    assert not ctx["browser"].find_elements(By.ID, "unduhWilayah")
    assert not ctx["browser"].find_elements(By.ID, "unduhTiket")
