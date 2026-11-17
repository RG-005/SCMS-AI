"""UC-L: Kepala Bidang melihat dan mengunduh Laporan Kinerja Infrastruktur, dengan grafiknya (Sprint 3)."""
import csv
import io
import json
import re

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from app.controllers.kontrol_verifikasi import KontrolVerifikasi
from app.database import SessionLocal
from app.models.entities import Laporan, WorkOrder
from database.seed import seed_data

scenarios("../features/uc_l_laporan_kinerja.feature")
# Sprint 3 backlog 3: the chart feature shares the page and most steps with the table feature above.
scenarios("../features/uc_l_grafik_kinerja.feature")

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
    assert baris.find_element(By.CSS_SELECTOR, '[data-kolom="penyelesaian"]').text.strip()


@then(parsers.parse('the average duration of stage "{tahap}" is "{durasi}"'))
def durasi_rata_tahap(ctx, tahap, durasi):
    tabel = ctx["browser"].find_element(By.ID, "tabelDurasiTahap")
    judul = [th.text.strip().lower() for th in tabel.find_elements(By.CSS_SELECTOR, "thead th")]
    kolom = judul.index(tahap.lower())
    sel = tabel.find_elements(By.CSS_SELECTOR, 'tr[data-kelompok="Keseluruhan"] td')[kolom]
    assert sel.text.strip().startswith(durasi), sel.text


@then(parsers.parse('the oldest active ticket is "{id_tiket}" in stage "{tahap}"'))
def tiket_aktif_tertua(ctx, id_tiket, tahap):
    pertama = ctx["browser"].find_element(By.CSS_SELECTOR, "#tabelTiketAktif tbody tr")
    assert pertama.get_attribute("data-tiket") == id_tiket
    assert pertama.find_element(By.CSS_SELECTOR, '[data-kolom="tahap"]').text.strip() == tahap
    assert pertama.find_element(By.CSS_SELECTOR, '[data-kolom="umur"]').text.strip().endswith("hari")


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
    assert baris[0][0] == "Wilayah" and "Rata-rata Durasi Inspeksi Lapangan (hari)" in baris[0]
    assert not any("SLA" in kolom for kolom in baris[0])
    assert any(r and r[0] == wilayah for r in baris[1:])
    assert baris[-1][0] == "TOTAL"


@then(parsers.parse('the system displays the message "{pesan}"'))
def pesan_kosong(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanKosong").text.strip() == pesan


@then("the download buttons are not shown")
def tombol_unduh_tidak_ada(ctx):
    assert not ctx["browser"].find_elements(By.ID, "unduhWilayah")
    assert not ctx["browser"].find_elements(By.ID, "unduhTiket")


# ---------------------------------------------------------------------------
# Sprint 3 backlog 3: charts (uc_l_grafik_kinerja.feature)
# The chart numbers are read from the #dataGrafikKinerja JSON the charts are drawn from,
# so the steps do not depend on Chart.js loading or on reading pixels from a canvas.
# ---------------------------------------------------------------------------
def _grafik(ctx) -> dict:
    el = ctx["browser"].find_element(By.ID, "dataGrafikKinerja")
    return json.loads(el.get_attribute("textContent"))


def _pasangan(teks: str) -> list:
    """'"Urgent" 2, "Tinggi" 2 and "Rendah" 0' -> [("Urgent", 2), ("Tinggi", 2), ("Rendah", 0)]"""
    hasil = [(nama, int(jumlah)) for nama, jumlah in re.findall(r'"([^"]+)" (\d+)', teks)]
    assert hasil, teks
    return hasil


def _baris_total_wilayah(ctx) -> list:
    for tr in ctx["browser"].find_elements(By.CSS_SELECTOR, "#tabelWilayah tbody tr"):
        sel = tr.find_elements(By.TAG_NAME, "td")
        if sel and sel[0].text.strip() == "Total":
            return [td.text.strip() for td in sel]
    raise AssertionError("Baris Total tidak ada di tabel wilayah")


@then(parsers.re(r'the charts (?P<daftar>".+") are displayed'))
def grafik_tampil(ctx, daftar):
    judul = re.findall(r'"([^"]+)"', daftar)
    assert len(judul) == 4, judul
    for j in judul:
        figur = ctx["browser"].find_element(By.CSS_SELECTOR, f'#grafikKinerja [data-grafik="{j}"]')
        assert figur.find_element(By.TAG_NAME, "h3").text.strip() == j
        assert figur.find_element(By.TAG_NAME, "canvas").is_displayed()
    assert _grafik(ctx)  # chart data is on the page


@then(parsers.re(r'the "Distribusi Prioritas" chart shows (?P<pasangan>.+)'))
def grafik_prioritas(ctx, pasangan):
    data = _grafik(ctx)["prioritas"]
    nilai = dict(zip(data["label"], data["jumlah"]))
    for nama, jumlah in _pasangan(pasangan):
        assert nilai[nama] == jumlah, (nama, nilai)


@then(parsers.parse("the weekly trend chart totals {masuk:d} incoming and {selesai:d} completed tickets"))
def grafik_tren(ctx, masuk, selesai):
    tren = _grafik(ctx)["tren"]
    assert len(tren["label"]) == len(tren["masuk"]) == len(tren["selesai"]) >= 1
    assert sum(tren["masuk"]) == masuk
    assert sum(tren["selesai"]) == selesai


@then("every chart value equals the matching value in the recap tables")
def grafik_sama_dengan_tabel(ctx):
    b, data = ctx["browser"], _grafik(ctx)
    # Distribusi Prioritas <-> "Statistik per Tingkat Prioritas" (column "Jumlah Tiket")
    for nama, jumlah in zip(data["prioritas"]["label"], data["prioritas"]["jumlah"]):
        sel = b.find_elements(By.CSS_SELECTOR, f'#tabelPrioritas tr[data-prioritas="{nama}"] td')
        assert int(sel[1].text) == jumlah, nama
    # Rekap per Wilayah <-> "Rekap Kinerja per Wilayah Rayon" (Total, Selesai, Aktif)
    for i, nama in enumerate(data["wilayah"]["label"]):
        sel = b.find_elements(By.CSS_SELECTOR, f'#tabelWilayah tr[data-wilayah="{nama}"] td')
        assert [int(sel[1].text), int(sel[2].text), int(sel[3].text)] == [
            data["wilayah"]["total"][i], data["wilayah"]["selesai"][i], data["wilayah"]["aktif"][i]], nama
    # Rata-rata Durasi per Tahap <-> "Keseluruhan" row of the stage-duration table
    sel = b.find_elements(By.CSS_SELECTOR, '#tabelDurasiTahap tr[data-kelompok="Keseluruhan"] td[data-tahap]')
    assert len(sel) == len(data["tahap"]["hari"])
    for td, hari, jumlah in zip(sel, data["tahap"]["hari"], data["tahap"]["jumlah_tiket"]):
        teks = td.text.strip()
        if hari is None:
            assert teks.startswith("–"), teks
        else:
            assert teks.startswith(f"{hari} hari"), (teks, hari)
            assert f"({jumlah})" in teks, (teks, jumlah)
    # Weekly trend totals <-> the Total row (Total and Selesai columns)
    total = _baris_total_wilayah(ctx)
    assert sum(data["tren"]["masuk"]) == int(total[1])
    assert sum(data["tren"]["selesai"]) == int(total[2])


@then(parsers.parse('the "Rekap per Wilayah" chart shows only "{wilayah}" with {jumlah:d} ticket'))
def grafik_wilayah_saja(ctx, wilayah, jumlah):
    data = _grafik(ctx)["wilayah"]
    assert data["label"] == [wilayah]
    assert data["total"] == [jumlah]


@given(parsers.parse('ticket "{id_wo}" has been closed with reason "{alasan}"'))
def tiket_ditutup(ctx, id_wo, alasan):
    db = SessionLocal()
    try:
        # Like the other Sprint 3 steps, the starting status is prepared directly; the closing
        # itself goes through the official "Tolak" action (PRD 5.3 BR-4 door a).
        wo = db.get(WorkOrder, id_wo)
        wo.status_work_order = "Dilaporkan"
        for lap in db.query(Laporan).filter_by(id_work_order=id_wo):
            lap.status = "Dilaporkan"
        db.commit()
        hasil = KontrolVerifikasi(db).tolak_tiket(id_wo, alasan, "admin@dpupr.surabaya.go.id")
        assert hasil["success"], hasil["message"]
        assert db.get(WorkOrder, id_wo).status_work_order == "Ditutup"
    finally:
        db.close()


@when(parsers.parse('the head of division shows the performance report for "{mulai}" to "{akhir}" and region "{wilayah}"'))
def tampilkan_laporan(ctx, pilih_opsi, klik_dan_tunggu, mulai, akhir, wilayah):
    buka_laporan_kinerja(ctx, "Laporan Kinerja Infrastruktur")
    pilih_periode(ctx, pilih_opsi, mulai, akhir, wilayah)
    klik_tampilkan(ctx, klik_dan_tunggu, "Tampilkan")


@then(parsers.parse('the "Ditutup" section shows {jumlah:d} ticket for reason "{alasan}"'))
def bagian_ditutup(ctx, jumlah, alasan):
    b = ctx["browser"]
    assert b.find_element(By.ID, "jumlahDitutup").text.strip() == str(jumlah)
    sel = b.find_element(By.CSS_SELECTOR, f'#tabelDitutup tr[data-alasan="{alasan}"] [data-kolom="jumlah"]')
    assert sel.text.strip() == str(jumlah)


@then(parsers.parse("the total ticket count is {total:d} and the completed count is still {selesai:d}"))
def total_dan_selesai(ctx, total, selesai):
    assert ctx["browser"].find_element(By.ID, "kpiTotal").text.strip() == str(total)
    baris = _baris_total_wilayah(ctx)
    assert int(baris[1]) == total and int(baris[2]) == selesai


@then(parsers.parse("the completion rate is calculated from {total:d} tickets, not {lama:d}"))
def tingkat_penyelesaian(ctx, total, lama):
    selesai = int(_baris_total_wilayah(ctx)[2])
    teks = ctx["browser"].find_element(By.ID, "kpiPenyelesaian").text.strip()
    assert teks == f"{round(selesai / total * 100, 1):.1f}%", teks
    assert teks != f"{round(selesai / lama * 100, 1):.1f}%"


@then("no chart is displayed")
def tanpa_grafik(ctx):
    b = ctx["browser"]
    assert not b.find_elements(By.ID, "grafikKinerja")
    assert not b.find_elements(By.ID, "dataGrafikKinerja")
    assert not b.find_elements(By.TAG_NAME, "canvas")
