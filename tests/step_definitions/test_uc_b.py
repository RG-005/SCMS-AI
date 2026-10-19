import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from app.database import SessionLocal
from database.seed import seed_data
from app.controllers.kontrol_verifikasi import KontrolVerifikasi

scenarios("../features/uc_b_verifikasi.feature")

@pytest.fixture
def ver_context():
    seed_data()
    db = SessionLocal()
    yield {
        "db": db,
        "controller": KontrolVerifikasi(db),
        "ticket_id": None,
        "detail": None,
        "wo": None
    }
    db.close()

@given(parsers.parse('I open ticket "{ticket_id}" with Risk Score "{risk_label}"'))
def open_ticket_with_score(ver_context, ticket_id, risk_label):
    ver_context["ticket_id"] = ticket_id
    detail = ver_context["controller"].lihat_detail_tiket(ticket_id)
    ver_context["detail"] = detail
    assert detail["risk_score_label"] == risk_label

@given(parsers.parse('I see ticket "{ticket_id}" marked "{opsi}"'))
def see_ticket_marked_option(ver_context, ticket_id, opsi):
    ver_context["ticket_id"] = ticket_id
    detail = ver_context["controller"].lihat_detail_tiket(ticket_id)
    ver_context["detail"] = detail
    assert detail["opsi_verifikasi"] == opsi

@given(parsers.parse('I see ticket "{ticket_id}" marked as ambiguous'))
def see_ticket_ambiguous(ver_context, ticket_id):
    ver_context["ticket_id"] = ticket_id
    detail = ver_context["controller"].lihat_detail_tiket(ticket_id)
    ver_context["detail"] = detail
    assert detail["is_ambiguous"] is True

@when('I press the "Setujui Tiket" button')
def press_approve_button(ver_context):
    ver_context["wo"] = ver_context["controller"].setujui_tiket(ver_context["ticket_id"])

@when("I view the ticket detail")
def view_ticket_detail(ver_context):
    ver_context["detail"] = ver_context["controller"].lihat_detail_tiket(ver_context["ticket_id"])

@when(parsers.parse('I select "Tugaskan Inspeksi Tambahan" and assign Penilik Jalan "{nama_penilik}"'))
def assign_additional_inspection(ver_context, nama_penilik):
    ver_context["wo"] = ver_context["controller"].tugaskan_inspeksi_tambahan(
        ver_context["ticket_id"], nama_penilik
    )

@when('I press the "Lanjutkan Tanpa Inspeksi" button')
def proceed_without_inspection(ver_context):
    ver_context["wo"] = ver_context["controller"].lanjutkan_tanpa_inspeksi(
        ver_context["ticket_id"], "admin@dpupr.surabaya.go.id"
    )

@then(parsers.parse('I see the ticket status change to "{expected_status}"'))
def check_ticket_status(ver_context, expected_status):
    assert ver_context["wo"].status_work_order == expected_status

@then(parsers.parse('I see the option "{expected_option}"'))
def check_verification_option(ver_context, expected_option):
    assert ver_context["detail"]["opsi_verifikasi"] == expected_option

@then(parsers.parse('I see my decision logged as "{expected_log}"'))
def check_manual_decision_log(ver_context, expected_log):
    assert ver_context["wo"].log_keputusan == expected_log
