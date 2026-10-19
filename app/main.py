from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.controllers.kontrol_verifikasi import KontrolVerifikasi

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SCMS-AI Dinas PUPR Kota Surabaya - Modul Verifikasi (UC-B)")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/views/templates")

@app.get("/")
def root():
    return RedirectResponse(url="/verifikasi")

@app.get("/verifikasi", response_class=HTMLResponse)
def halaman_verifikasi(
    request: Request,
    ticket_id: str = "REP-2026-00341",
    pesan_sukses: str = None,
    db: Session = Depends(get_db)
):
    controller = KontrolVerifikasi(db)
    semua_tiket = controller.muat_daftar_tiket()
    detail = controller.lihat_detail_tiket(ticket_id)
    if not detail and semua_tiket:
        detail = controller.lihat_detail_tiket(semua_tiket[0].id_work_order)

    return templates.TemplateResponse(
        request=request,
        name="verifikasi_detail.html",
        context={
            "semua_tiket": semua_tiket,
            "detail": detail,
            "pesan_sukses": pesan_sukses
        }
    )

@app.post("/verifikasi/{ticket_id}/approve", response_class=HTMLResponse)
def proses_setujui_tiket(
    request: Request,
    ticket_id: str,
    db: Session = Depends(get_db)
):
    controller = KontrolVerifikasi(db)
    wo = controller.setujui_tiket(ticket_id)
    pesan = f"Tiket {ticket_id} telah disetujui (Status: {wo.status_work_order})."
    return halaman_verifikasi(request=request, ticket_id=ticket_id, pesan_sukses=pesan, db=db)

@app.post("/verifikasi/{ticket_id}/inspect", response_class=HTMLResponse)
def proses_tugaskan_inspeksi(
    request: Request,
    ticket_id: str,
    nama_penilik: str = Form(default="Budi Santoso"),
    db: Session = Depends(get_db)
):
    controller = KontrolVerifikasi(db)
    wo = controller.tugaskan_inspeksi_tambahan(ticket_id, nama_penilik)
    pesan = f"Inspeksi tambahan untuk tiket {ticket_id} ditugaskan kepada {nama_penilik} (Status: {wo.status_work_order})."
    return halaman_verifikasi(request=request, ticket_id=ticket_id, pesan_sukses=pesan, db=db)

@app.post("/verifikasi/{ticket_id}/skip-inspection", response_class=HTMLResponse)
def proses_lanjutkan_tanpa_inspeksi(
    request: Request,
    ticket_id: str,
    db: Session = Depends(get_db)
):
    controller = KontrolVerifikasi(db)
    wo = controller.lanjutkan_tanpa_inspeksi(ticket_id, "admin@dpupr.surabaya.go.id")
    pesan = f"Keputusan manual tercatat: '{wo.log_keputusan}'. Status tiket: {wo.status_work_order}."
    return halaman_verifikasi(request=request, ticket_id=ticket_id, pesan_sukses=pesan, db=db)
