from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models.entities import WorkOrder, Wilayah
from app.controllers.kontrol_dashboard import KontrolDashboard

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SCMS-AI Dinas PUPR Kota Surabaya - Modul Dashboard Prioritas (UC-H)")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/views/templates")

@app.get("/")
def root():
    return RedirectResponse(url="/Dashboard")

@app.get("/Dashboard", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def halaman_dashboard_prioritas(
    request: Request,
    wilayah: str = "Semua",
    status: str = "Semua",
    kategori: str = "Semua",
    db: Session = Depends(get_db)
):
    controller = KontrolDashboard(db)
    if wilayah == "Semua" and status == "Semua" and kategori == "Semua":
        data_dash = controller.muat_dashboard()
    else:
        data_dash = controller.filter_dashboard(wilayah=wilayah, status=status, kategori=kategori)

    semua_wo = db.query(WorkOrder).all()
    daftar_wilayah = db.query(Wilayah).all()

    total_aduan = len(semua_wo)
    kasus_ditangani = sum(1 for w in semua_wo if w.status_work_order != "Selesai")
    kasus_selesai = sum(1 for w in semua_wo if w.status_work_order == "Selesai")
    kasus_darurat = sum(1 for w in semua_wo if w.risk_score >= 8.0)

    return templates.TemplateResponse(
        request=request,
        name="dashboard_prioritas.html",
        context={
            "daftar_tiket": data_dash["daftar_tiket"],
            "pesan_kosong": data_dash["message"],
            "daftar_wilayah": daftar_wilayah,
            "filter_wilayah": wilayah,
            "filter_status": status,
            "filter_kategori": kategori,
            "total_aduan": total_aduan,
            "kasus_ditangani": kasus_ditangani,
            "kasus_selesai": kasus_selesai,
            "kasus_darurat": kasus_darurat
        }
    )
