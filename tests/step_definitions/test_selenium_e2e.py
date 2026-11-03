import time
import pytest
from selenium.webdriver.common.by import By
from database.seed import seed_data


@pytest.fixture(autouse=True)
def reset_db_sebelum_selenium():
    seed_data()


def test_selenium_bdd_uc_k_login_dan_register_nik(browser, live_server, login_as):
    """
    Skenario E2E Selenium 1 (UC-K + Register NIK):
    - Membuka halaman /Register di browser
    - Mendaftarkan Warga baru dengan NIK 16 digit
    - Diarahkan otomatis ke halaman /Login dengan pesan sukses
    """
    browser.get(f"{live_server}/Logout")
    login_as.reset()
    browser.get(f"{live_server}/Register")
    assert "Registrasi Akun Pelapor" in browser.page_source

    # Robot Selenium mengetik data registrasi Warga baru
    browser.find_element(By.ID, "nik").send_keys("3578012410990009")
    browser.find_element(By.ID, "nama_lengkap").send_keys("Rizaldi Warga Surabaya")
    browser.find_element(By.ID, "no_hp").send_keys("081234567899")
    browser.find_element(By.ID, "email").send_keys("rizaldi.warga@gmail.com")
    browser.find_element(By.ID, "alamat_domisili").send_keys("Jl. Airlangga No. 4, Gubeng")
    browser.find_element(By.ID, "password").send_keys("password123")
    browser.find_element(By.ID, "konfirmasi_password").send_keys("password123")

    # Klik tombol Daftar
    browser.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(0.5)

    # Pastikan berhasil masuk ke halaman Login dan muncul notifikasi sukses
    assert "Registrasi berhasil" in browser.page_source


def test_selenium_bdd_uc_k_login_admin_ke_dashboard(browser, live_server, login_as):
    """
    Skenario E2E Selenium 2 (UC-K -> UC-H):
    - Admin membuka halaman /Login
    - Mengetik email & password Admin lalu menekan tombol Masuk
    - Browser berpindah ke halaman /Dashboard dan merender Peta GIS & Priority Queue
    """
    browser.get(f"{live_server}/Logout")
    login_as.reset()
    browser.get(f"{live_server}/Login")

    input_id = browser.find_element(By.ID, "identifier")
    input_pw = browser.find_element(By.ID, "password")

    input_id.clear()
    input_id.send_keys("admin@dpupr.surabaya.go.id")
    input_pw.clear()
    input_pw.send_keys("password123")

    # Klik tombol Masuk
    browser.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(0.8)

    # Verifikasi halaman berpindah ke Dashboard Prioritas (UC-H)
    assert "/Dashboard" in browser.current_url
    assert "REP-2026-00341" in browser.page_source
    assert "Ir. Hendra Kusuma" in browser.page_source  # nama pengguna yang benar-benar login


def test_selenium_bdd_uc_b_verifikasi_dan_uc_g_penugasan(browser, live_server, login_as):
    """
    Skenario E2E Selenium 3 (UC-B & UC-G):
    - Membuka halaman Verifikasi Laporan (/verifikasi) untuk mengecek tiket ambigu REP-2026-00355
    - Membuka halaman Penugasan Penilik (/work-orders) untuk melihat daftar SPK
    """
    login_as("admin@dpupr.surabaya.go.id")
    # 1. Cek halaman Verifikasi (UC-B) pada tiket skor ambigu REP-2026-00355
    browser.get(f"{live_server}/verifikasi?ticket_id=REP-2026-00355")
    time.sleep(0.5)
    assert "REP-2026-00355" in browser.page_source
    assert "Butuh Verifikasi Lapangan" in browser.page_source

    # 2. Cek halaman Penugasan Work Order (UC-G)
    browser.get(f"{live_server}/work-orders?select_ticket=REP-2026-00341")
    time.sleep(0.5)
    assert "REP-2026-00341" in browser.page_source
    assert "24 jam" in browser.page_source