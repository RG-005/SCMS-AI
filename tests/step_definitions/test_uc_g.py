import time
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from app.database import SessionLocal
from database.seed import seed_data
from app.controllers.kontrol_penugasan import KontrolPenugasan

scenarios("../features/uc_g_penugasan.feature")


@pytest.fixture
def context(browser, live_server, login_as):
    seed_data()
    login_as("admin@dpupr.surabaya.go.id")
    db = SessionLocal()
    yield {
        "db": db,
        "controller": KontrolPenugasan(db),
        "browser": browser,
        "base_url": live_server,
        "ticket_id": None,
        "info_tiket": None,
        "wo": None
    }
    db.close()


def _open_work_orders_page(context, ticket_id: str):
    driver = context["browser"]
    driver.get(f"{context['base_url']}/work-orders?select_ticket={ticket_id}")
    time.sleep(0.35)


@given(parsers.parse('I have verified ticket "{ticket_id}"'))
def verified_ticket(context, ticket_id):
    context["ticket_id"] = ticket_id
    _open_work_orders_page(context, ticket_id)


@when("I select the ticket")
def select_ticket(context):
    context["info_tiket"] = context["controller"].cek_sla_dan_ketersediaan_penilik(context["ticket_id"])


@then(parsers.parse('I see an SLA recommendation of "{sla}" along with a list of available Penilik Jalan in "{wilayah}"'))
def check_sla_and_penilik(context, sla, wilayah):
    info = context["info_tiket"]
    assert info["sla_rekomendasi"] == sla
    assert info["nama_wilayah"] == wilayah
    assert len(info["daftar_penilik"]) > 0
    assert sla in context["browser"].page_source


@when(parsers.parse('I select "{nama_penilik}" as the Penilik Jalan'))
def assign_penilik(context, nama_penilik):
    context["wo"] = context["controller"].tugaskan_penilik(context["ticket_id"], nama_penilik)
    _open_work_orders_page(context, context["ticket_id"])


@then(parsers.parse('I see the ticket status change to "{expected_status}"'))
def verify_status_changed(context, expected_status):
    assert context["wo"].status_work_order == expected_status


@given(parsers.parse('I see ticket "{ticket_id}" located in "{wilayah}"'))
def ticket_in_region(context, ticket_id, wilayah):
    context["ticket_id"] = ticket_id
    _open_work_orders_page(context, ticket_id)
    info = context["controller"].cek_sla_dan_ketersediaan_penilik(ticket_id)
    assert info["nama_wilayah"] == wilayah


@when("I attempt to make an assignment and find no available Penilik Jalan in that region")
def attempt_assignment_no_penilik(context):
    context["wo"] = context["controller"].tugaskan_penilik(context["ticket_id"])
    _open_work_orders_page(context, context["ticket_id"])


@then(parsers.parse('I see the ticket marked as "{expected_status}"'))
def verify_waiting_status(context, expected_status):
    assert context["wo"].status_work_order == expected_status