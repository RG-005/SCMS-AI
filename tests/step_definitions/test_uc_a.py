import re
import time
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from selenium.webdriver.common.by import By
from app.database import SessionLocal
from database.seed import seed_data
from app.models.entities import WorkOrder
from app.controllers.kontrol_pelaporan import KontrolPelaporan

scenarios("../features/uc_a_buat_laporan.feature")


@pytest.fixture
def report_context(browser, live_server, login_as):
    seed_data()
    db = SessionLocal()
    yield {
        "db": db,
        "controller": KontrolPelaporan(db),
        "browser": browser,
        "login_as": login_as,
        "base_url": live_server,
        "existing_ids": {w.id_work_order for w in db.query(WorkOrder).all()},
        "filename": None,
        "file_size_mb": 2.0,
        "lokasi": "Jl. Sudirman No. 45, Surabaya",
        "deskripsi": "Lubang besar di tengah jalan membahayakan pengendara motor",
        "kategori": None,
        "initial_exposure": 0,
        "cv_result": None,
        "result": None
    }
    db.close()


def _open_lapor_page(report_context):
    report_context["login_as"]("0812xxxxxxx")
    driver = report_context["browser"]
    driver.get(f"{report_context['base_url']}/lapor")
    time.sleep(0.35)


@given('I am logged in and on the "Buat Laporan" page')
def logged_in_on_create_report_page(report_context):
    report_context["page"] = "Buat Laporan"
    _open_lapor_page(report_context)


@given('I am on the "Buat Laporan" page')
def on_create_report_page(report_context):
    report_context["page"] = "Buat Laporan"
    _open_lapor_page(report_context)


@given(parsers.parse('there is already an active report "{ticket_id}" at "{lokasi}" with category "{kategori}"'))
def active_report_exists(report_context, ticket_id, lokasi, kategori):
    wo = report_context["db"].query(WorkOrder).filter_by(id_work_order=ticket_id).first()
    assert wo is not None
    assert wo.status_work_order != "Selesai", "duplicate detection only merges into active tickets (BR-3)"
    assert wo.kategori_kerusakan == kategori
    report_context["initial_exposure"] = wo.exposure_count
    report_context["lokasi"] = lokasi
    report_context["kategori"] = kategori
    _open_lapor_page(report_context)


@when(parsers.parse('I upload a road damage photo "{filename}" (size {size:f}MB)'))
def upload_valid_photo(report_context, filename, size):
    report_context["filename"] = filename
    report_context["file_size_mb"] = size
    report_context["cv_result"] = report_context["controller"].analisis_ai_cv(filename)
    driver = report_context["browser"]
    driver.execute_script(
        "if(typeof goStep === 'function'){ goStep(2); }"
    )
    time.sleep(0.25)


@when(parsers.parse('I select the location "{lokasi}" via GPS'))
def select_gps_location(report_context, lokasi):
    report_context["lokasi"] = lokasi
    driver = report_context["browser"]
    try:
        loc_input = driver.find_element(By.ID, "inputLokasi")
        driver.execute_script("arguments[0].value = arguments[1];", loc_input, lokasi)
        driver.execute_script("if(typeof goStep === 'function'){ goStep(3); }")
        time.sleep(0.25)
    except Exception:
        pass


@when(parsers.parse('I see the AI category recommendation "{expected_cat}" and keep it as is'))
def verify_and_keep_ai_category(report_context, expected_cat):
    assert report_context["cv_result"]["rekomendasi_kategori"] == expected_cat
    report_context["kategori"] = expected_cat


@when(parsers.parse('I enter the description "{deskripsi}"'))
def enter_report_description(report_context, deskripsi):
    report_context["deskripsi"] = deskripsi
    driver = report_context["browser"]
    try:
        desc_input = driver.find_element(By.ID, "inputDeskripsi")
        driver.execute_script("arguments[0].value = arguments[1];", desc_input, deskripsi)
        driver.execute_script("if(typeof goStep === 'function'){ goStep(4); }")
        time.sleep(0.25)
    except Exception:
        pass


@when('I press the "Kirim Laporan" button')
def press_submit_report(report_context):
    report_context["result"] = report_context["controller"].kirim_laporan(
        filename=report_context["filename"],
        file_size_mb=report_context["file_size_mb"],
        lokasi_jalan=report_context["lokasi"],
        deskripsi=report_context["deskripsi"],
        kategori_pilihan=report_context["kategori"],
    )


@when('I upload a file with size 15MB or in ".pdf" format')
def upload_invalid_file(report_context):
    report_context["result"] = report_context["controller"].kirim_laporan(
        filename="dokumen_laporan.pdf",
        file_size_mb=15.0,
        lokasi_jalan=report_context["lokasi"],
        deskripsi=report_context["deskripsi"]
    )
    time.sleep(0.25)


@when(parsers.parse('I upload a photo that does not show road damage, such as "{filename}"'))
def upload_non_road_photo(report_context, filename):
    report_context["result"] = report_context["controller"].kirim_laporan(
        filename=filename,
        file_size_mb=1.8,
        lokasi_jalan=report_context["lokasi"],
        deskripsi=report_context["deskripsi"]
    )
    time.sleep(0.25)


@when("I submit a new report at the same location with a similar description")
def submit_duplicate_report(report_context):
    report_context["result"] = report_context["controller"].kirim_laporan(
        filename="jalan_berlubang_sudirman_2.jpg",
        file_size_mb=2.1,
        lokasi_jalan=report_context["lokasi"],
        deskripsi="Ada jalan berlubang cukup dalam di depan gedung Sudirman",
        kategori_pilihan=report_context["kategori"],
    )
    time.sleep(0.25)


@then(parsers.parse('I receive a new ticket number with initial status "{status}"'))
def check_ticket_created(report_context, status):
    hasil = report_context["result"]
    assert hasil["success"] is True
    assert hasil["is_duplicate"] is False
    assert re.fullmatch(r"REP-\d{4}-\d{5}", hasil["ticket_id"])
    assert hasil["ticket_id"] not in report_context["existing_ids"]
    assert hasil["status_work_order"] == status


@then(parsers.parse('I see the error message "{expected_msg}"'))
def check_format_error_message(report_context, expected_msg):
    assert report_context["result"]["message"] == expected_msg


@then("I cannot proceed to the next step")
def check_cannot_proceed(report_context):
    assert report_context["result"]["success"] is False


@then(parsers.parse('I see the warning "{expected_warning}"'))
def check_cv_warning(report_context, expected_warning):
    assert report_context["result"]["message"] == expected_warning


@then("my report is not saved")
def check_report_not_saved(report_context):
    assert report_context["result"]["success"] is False


@then(parsers.parse('my report is merged into ticket "{ticket_id}" and its exposure count increases by 1'))
def check_merged_and_exposure_increased(report_context, ticket_id):
    assert report_context["result"]["success"] is True
    assert report_context["result"]["is_duplicate"] is True
    assert report_context["result"]["ticket_id"] == ticket_id
    assert report_context["result"]["exposure_count"] == report_context["initial_exposure"] + 1


@then(parsers.parse('I receive the notification "{expected_notif}"'))
def check_duplicate_notification(report_context, expected_notif):
    assert report_context["result"]["message"] == expected_notif