"""UC-J: Warga memberi rating & ulasan untuk laporan yang sudah Selesai."""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By

from app.database import SessionLocal
from app.models.entities import Rating
from database.seed import seed_data

scenarios("../features/uc_j_rating_ulasan.feature")

TOMBOL = {"Kirim Ulasan": "tombolKirimUlasan"}


@pytest.fixture
def ctx(browser, live_server, login_as, alur):
    seed_data(verbose=False)
    return {"browser": browser, "base": live_server, "alur": alur, "login_as": login_as}


def _rating(id_laporan):
    db = SessionLocal()
    try:
        return db.query(Rating).filter_by(id_laporan=id_laporan).first()
    finally:
        db.close()


@given(parsers.parse('the citizen opens the details of report "{id_laporan}" with status "{status}" and no existing rating'))
def buka_laporan_selesai(ctx, id_laporan, status):
    ctx["alur"][status](id_laporan)
    assert ctx["alur"]["status"](id_laporan) == status
    assert _rating(id_laporan) is None
    ctx["id_laporan"] = id_laporan
    ctx["login_as"]("0812xxxxxxx")
    ctx["browser"].get(f"{ctx['base']}/lacak?id={id_laporan}")
    assert ctx["browser"].find_element(By.ID, "formRating")


@when(parsers.parse('the citizen selects a "{bintang}" star rating score and writes review "{ulasan}"'))
def pilih_bintang(ctx, bintang, ulasan):
    ctx.update(bintang=int(bintang), ulasan=ulasan)
    ctx["browser"].find_element(By.CSS_SELECTOR, f"label[for='bintang-{bintang}']").click()
    ctx["browser"].find_element(By.ID, "komentar").send_keys(ulasan)


@when(parsers.parse('the citizen clicks the "{tombol}" button'))
def klik(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, TOMBOL[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


@when(parsers.parse('the citizen leaves the star rating option blank and clicks the "{tombol}" button'))
def kirim_tanpa_bintang(ctx, klik_dan_tunggu, tombol):
    klik(ctx, klik_dan_tunggu, tombol)


@then("the system saves the evaluation to the Rating table")
def tersimpan(ctx):
    r = _rating(ctx["id_laporan"])
    assert r is not None and (r.nilai_bintang, r.komentar) == (ctx["bintang"], ctx["ulasan"])


@then(parsers.parse('the system displays a confirmation message "{pesan}"'))
def konfirmasi(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan
    assert ctx["browser"].find_element(By.ID, "ratingTersimpan")


@then("the system rejects the review submission")
def ditolak(ctx):
    assert _rating(ctx["id_laporan"]) is None


@then(parsers.parse('the system displays a warning message "{pesan}"'))
def peringatan(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan
