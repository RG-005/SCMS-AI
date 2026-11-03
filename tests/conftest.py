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
        driver = webdriver.Chrome(options=chrome_opts)
    except Exception:
        edge_opts = EdgeOptions()
        if headless_mode:
            edge_opts.add_argument("--headless=new")
        edge_opts.add_argument("--window-size=1280,820")
        driver = webdriver.Edge(options=edge_opts)

    driver.implicitly_wait(5)
    yield driver
    driver.quit()


@pytest.fixture(scope="session")
def login_as(browser, live_server):
    """Masuk lewat form Login sungguhan sebagai akun tertentu (dilewati jika sudah masuk sebagai akun itu)."""
    status = {"akun": None}

    def _login(identifier: str, password: str = PASSWORD_DEMO):
        if status["akun"] == identifier:
            return
        browser.get(f"{live_server}/Logout")
        browser.get(f"{live_server}/Login")
        kolom_id = browser.find_element(By.ID, "identifier")
        kolom_id.clear()
        kolom_id.send_keys(identifier)
        kolom_pw = browser.find_element(By.ID, "password")
        kolom_pw.clear()
        kolom_pw.send_keys(password)
        browser.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(0.4)
        assert "/Login" not in browser.current_url, f"Login gagal untuk {identifier}"
        status["akun"] = identifier

    _login.reset = lambda: status.update(akun=None)
    return _login
