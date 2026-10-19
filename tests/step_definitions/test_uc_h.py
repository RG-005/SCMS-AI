import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from app.database import SessionLocal
from database.seed import seed_data
from app.controllers.kontrol_dashboard import KontrolDashboard

scenarios("../features/uc_h_dashboard.feature")

@pytest.fixture
def dash_context():
    seed_data()
    db = SessionLocal()
    yield {
        "db": db,
        "controller": KontrolDashboard(db),
        "active_count": 0,
        "result": None
    }
    db.close()

@given(parsers.parse("I see {count:d} active Work Orders in the system"))
def active_work_orders_count(dash_context, count):
    dash_context["active_count"] = count

@when(parsers.parse('I open the "{page}" page'))
def open_dashboard_page(dash_context, page):
    dash_context["result"] = dash_context["controller"].muat_dashboard()

@then("I see a damage distribution map with color gradation according to severity")
def verify_map_color_gradation(dash_context):
    assert dash_context["result"]["has_color_gradation"] is True
    assert len(dash_context["result"]["daftar_tiket"]) > 0

@then(parsers.parse('I see a list of tickets sorted from highest Risk Score, "{top_ticket}"'))
def verify_sorted_tickets(dash_context, top_ticket):
    assert dash_context["result"]["top_ticket_label"] == top_ticket

@given(parsers.parse('I apply the filter "Wilayah: {wilayah}, Status: {status}, Kategori: {kategori}"'))
def apply_dashboard_filter(dash_context, wilayah, status, kategori):
    dash_context["result"] = dash_context["controller"].filter_dashboard(
        wilayah=wilayah, status=status, kategori=kategori
    )

@then(parsers.parse('I see the message "{expected_message}"'))
def verify_empty_filter_message(dash_context, expected_message):
    assert dash_context["result"]["message"] == expected_message
