import os

# Tests always use their own throwaway database, never the DATABASE_URL in .env
# (seed_data() drops every table). Must be set before the app is imported.
os.environ["DATABASE_URL"] = os.environ.get("SCMS_TEST_DATABASE_URL", "sqlite:///./scms_test.db")
os.environ.setdefault("SCMS_SECRET_KEY", "test-secret-key-for-pytest-only")

import time
import socket
import threading
import pytest
import uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions

from app.main import app
from database.seed import seed_data

TEST_HOST = "127.0.0.1"
TEST_PORT = 8005
BASE_URL = f"http://{TEST_HOST}:{TEST_PORT}"
PASSWORD_DEMO = "password123"
AKUN_WARGA = "0812xxxxxxx"
AKUN_ADMIN = "admin@dpupr.surabaya.go.id"


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


@pytest.fixture(scope="session")
def live_server():
    """Menyalakan server FastAPI otomatis di background selama sesi pytest berjalan."""
    seed_data()
    if not _is_port_in_use(TEST_HOST, TEST_PORT):
        config = uvicorn.Config(app, host=TEST_HOST, port=TEST_PORT, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        for _ in range(30):
            if _is_port_in_use(TEST_HOST, TEST_PORT):
                break
            time.sleep(0.2)

    yield BASE_URL


def _tanpa_pengelola_sandi(opts):
    """Turn off Chrome/Edge's password manager for the test browser.

    After logging in with a demo password such as "password123", Chrome can show its own
    "Change your password" (leak detection) or "Save password?" dialog over the tab. While it
    is open, WebDriver clicks and keystrokes never reach the page (JavaScript still runs), so a
    submit click does nothing and typed text stays empty. This only happens on machines that can
    reach Google's leak-check service, which is why the same tests pass offline.
    """
    opts.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.password_manager_leak_detection": False,
    })
    opts.add_argument("--disable-features=PasswordLeakDetection,PasswordManagerOnboarding")
    return opts


@pytest.fixture(scope="session")
def browser(live_server):
    """Membuka 1 jendela browser Selenium untuk mengeksekusi seluruh skenario BDD secara berurutan."""
    headless_mode = os.environ.get("HEADLESS", "0") == "1"
    driver = None

    try:
        chrome_opts = ChromeOptions()
        if headless_mode:
            chrome_opts.add_argument("--headless=new")
        chrome_opts.add_argument("--window-size=1280,820")
        chrome_opts.add_argument("--disable-gpu")
        chrome_opts.add_argument("--no-sandbox")
        _tanpa_pengelola_sandi(chrome_opts)
        driver = webdriver.Chrome(options=chrome_opts)
    except Exception:
        edge_opts = EdgeOptions()
        if headless_mode:
            edge_opts.add_argument("--headless=new")
        edge_opts.add_argument("--window-size=1280,820")
        _tanpa_pengelola_sandi(edge_opts)
        driver = webdriver.Edge(options=edge_opts)

    driver.implicitly_wait(5)
    yield driver
    driver.quit()


def tunggu_halaman_baru(browser, aksi, batas: float = 15.0):
    """Run `aksi` (e.g. a submit click) and wait until the NEXT page has fully loaded.

    WebDriver's click() may return before a form POST and its redirect finish, so
    checking the URL, page or database right after it is a race on slower machines.
    A marker is put on the current page; the new page is loaded once it is gone.
    """
    browser.execute_script("window.__halamanLama = true;")
    aksi()
    akhir = time.time() + batas
    while time.time() < akhir:
        try:
            if browser.execute_script(
                    "return window.__halamanLama === undefined && document.readyState === 'complete';"):
                return
        except Exception:
            pass  # the page is navigating right now
        time.sleep(0.1)
    raise AssertionError(f"Halaman berikutnya tidak termuat dalam {batas:.0f} detik (url: {browser.current_url})")


@pytest.fixture(scope="session")
def klik_dan_tunggu(browser):
    """klik_dan_tunggu(elemen): click a submit button/link and wait for the resulting page."""
    return lambda elemen: tunggu_halaman_baru(browser, elemen.click)


@pytest.fixture(scope="session")
def login_as(browser, live_server):
    """Masuk lewat form Login sungguhan sebagai akun tertentu (dilewati jika sudah masuk sebagai akun itu)."""
    status = {"akun": None}

    def _login(identifier: str, password: str = PASSWORD_DEMO):
        if status["akun"] == identifier:
            return
        status["akun"] = None  # unknown until this login is confirmed
        browser.get(f"{live_server}/Logout")
        browser.get(f"{live_server}/Login")
        kolom_id = browser.find_element(By.ID, "identifier")
        kolom_id.clear()
        kolom_id.send_keys(identifier)
        kolom_pw = browser.find_element(By.ID, "password")
        kolom_pw.clear()
        kolom_pw.send_keys(password)
        tombol = browser.find_element(By.CSS_SELECTOR, "button[type='submit']")
        tunggu_halaman_baru(browser, tombol.click)
        if "/Login" in browser.current_url:
            teks = browser.find_element(By.TAG_NAME, "body").text.replace("\n", " | ")[:300]
            raise AssertionError(f"Login gagal untuk {identifier} (url {browser.current_url}): {teks}")
        status["akun"] = identifier

    _login.reset = lambda: status.update(akun=None)
    return _login


# --------------------------------------------------------------------------- #
# Sprint 2 helpers
# --------------------------------------------------------------------------- #
AKUN_PENILIK = "budi.santoso@dpupr.surabaya.go.id"


def _jpeg_bytes() -> bytes:
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (110, 110, 110)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(scope="session")
def foto_uji(tmp_path_factory):
    """foto_uji("survei_0001.jpg") -> absolute path of a real small JPEG with that name (for file inputs)."""
    folder = tmp_path_factory.mktemp("foto_uji")

    def _buat(nama: str) -> str:
        path = folder / nama
        if not path.exists():
            path.write_bytes(_jpeg_bytes())
        return str(path)

    return _buat


@pytest.fixture(scope="session")
def pilih_opsi(browser):
    """Select a <select> option by its visible text (works for any WebDriver)."""
    def _pilih(element_id: str, teks: str):
        ok = browser.execute_script(
            "var s = document.getElementById(arguments[0]);"
            "for (var i = 0; i < s.options.length; i++) {"
            "  if (s.options[i].text.trim() === arguments[1]) { s.selectedIndex = i; return true; }"
            "} return false;", element_id, teks)
        assert ok, f"Opsi '{teks}' tidak ada di #{element_id}"
    return _pilih


@pytest.fixture
def alur():
    """Bring a citizen report's ticket to a given stage through the real controllers."""
    from app.database import SessionLocal
    from app.models.entities import Laporan, WorkOrder
    from app.controllers.kontrol_inspeksi import KontrolInspeksi
    from app.controllers.kontrol_penanganan import KontrolPenanganan

    def id_wo(id_laporan: str) -> str:
        db = SessionLocal()
        try:
            return db.get(Laporan, id_laporan).id_work_order
        finally:
            db.close()

    def status(id_laporan: str) -> str:
        db = SessionLocal()
        try:
            return db.get(WorkOrder, id_wo(id_laporan)).status_work_order
        finally:
            db.close()

    def _jalankan(fungsi):
        db = SessionLocal()
        try:
            hasil = fungsi(db)
            assert hasil["success"], hasil["message"]
        finally:
            db.close()

    def sampai_terinspeksi(id_laporan: str):
        _jalankan(lambda db: KontrolInspeksi(db).simpan_inspeksi(
            id_wo(id_laporan), "PNL-01", "2m x 1.5m x 0.15m", "Lapisan aspal terkelupas", "Tambal Hotmix"))

    def sampai_dalam_proses(id_laporan: str):
        sampai_terinspeksi(id_laporan)
        _jalankan(lambda db: KontrolPenanganan(db).terbitkan_spk(
            id_wo(id_laporan), "SPK/PUPR/XI/2026/001", "Satgas Rayon Gubeng", "Dalam Proses", AKUN_ADMIN))

    def sampai_selesai(id_laporan: str):
        sampai_dalam_proses(id_laporan)
        _jalankan(lambda db: KontrolPenanganan(db).perbarui_progres(
            id_wo(id_laporan), "Selesai", "Lubang sudah ditambal", "selesai.jpg", _jpeg_bytes(), "Budi Santoso"))

    return {"id_wo": id_wo, "status": status, "Terinspeksi": sampai_terinspeksi,
            "Dalam Proses": sampai_dalam_proses, "Selesai": sampai_selesai}
