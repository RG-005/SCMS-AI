import logging
import os
import secrets
from typing import Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    HALAMAN_AWAL, PERAN_ADMIN, PERAN_KABID, PERAN_PENILIK, PERAN_STAF, PERAN_WARGA,
    AksesDitolak, LoginDiperlukan, keluar, pengguna_saat_ini, simpan_login, tujuan_aman, wajib_peran,
)
from app.controllers.kontrol_autentikasi import KontrolAutentikasi
from app.controllers.kontrol_dashboard import KontrolDashboard
from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.controllers.kontrol_penugasan import KontrolPenugasan
from app.controllers.kontrol_verifikasi import KontrolVerifikasi
from app.database import Base, engine, get_db, pastikan_kolom_terbaru
from app.models.entities import Laporan, PenilikJalan, Wilayah, WorkOrder
from app.services.ai_service import UKURAN_MAKS_MB, get_ai_service

logger = logging.getLogger("scms")

Base.metadata.create_all(bind=engine)
pastikan_kolom_terbaru()

app = FastAPI(
    title="SCMS-AI Dinas PUPR Kota Surabaya",
    description="Sistem Triage dan Prioritisasi Laporan Kerusakan Jalan Berbasis AI",
    version="1.1.0"
)

CONTOH_SECRET = {"", "ganti_dengan_string_acak_panjang", "changeme", "secret"}


def pilih_secret(nilai: Optional[str]) -> str:
    """Never sign sessions with a missing, short or published example key:
    anyone who knows it could forge an Admin session cookie."""
    nilai = (nilai or "").strip()
    if nilai in CONTOH_SECRET or len(nilai) < 16:
        logger.warning("SCMS_SECRET_KEY is missing, too short or the .env.example value; "
                       "using a random key instead (sessions reset on restart)")
        return secrets.token_hex(32)
    return nilai


_secret = pilih_secret(os.getenv("SCMS_SECRET_KEY"))
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret,
    session_cookie="scms_session",
    max_age=8 * 60 * 60,
    same_site="lax",
    https_only=os.getenv("SCMS_HTTPS_ONLY", "0") == "1",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/views/templates")

BATAS_BACA_FOTO = int(UKURAN_MAKS_MB * 1024 * 1024) + 1

# Who may do what
LIHAT_DASHBOARD = wajib_peran(*PERAN_STAF)
LIHAT_VERIFIKASI = wajib_peran(PERAN_ADMIN, PERAN_KABID)
LIHAT_PENUGASAN = wajib_peran(PERAN_ADMIN, PERAN_KABID, PERAN_PENILIK)
AKSI_ADMIN = wajib_peran(PERAN_ADMIN)
HANYA_WARGA = wajib_peran(PERAN_WARGA)


def render(request: Request, name: str, context: dict, status_code: int = 200):
    pengguna = pengguna_saat_ini(request)
    ctx = {
        "pengguna": pengguna,
        "boleh_aksi": bool(pengguna and pengguna["peran"] == PERAN_ADMIN),
        "mode_ai": get_ai_service().mode_cv,
        "ai_simulasi": get_ai_service().is_simulasi,
    }
    ctx.update(context)
    return templates.TemplateResponse(request=request, name=name, context=ctx, status_code=status_code)


@app.exception_handler(LoginDiperlukan)
def _login_diperlukan(request: Request, exc: LoginDiperlukan):
    return RedirectResponse(url=f"/Login?next={exc.tujuan}" if exc.tujuan else "/Login", status_code=303)


@app.exception_handler(AksesDitolak)
def _akses_ditolak(request: Request, exc: AksesDitolak):
    beranda = HALAMAN_AWAL.get(exc.pengguna["peran"], "/Login")
    return HTMLResponse(
        f"<h1>403 - Akses ditolak</h1><p>Peran Anda tidak memiliki akses ke halaman ini.</p>"
        f"<p><a href='{beranda}'>Kembali</a> &middot; <a href='/Logout'>Keluar</a></p>",
        status_code=403,
    )


def _wo_atau_404(db: Session, ticket_id: str) -> WorkOrder:
    wo = db.query(WorkOrder).filter_by(id_work_order=ticket_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail=f"Tiket {ticket_id} tidak ditemukan")
    return wo


@app.get("/")
def root(request: Request):
    pengguna = pengguna_saat_ini(request)
    return RedirectResponse(url=HALAMAN_AWAL.get(pengguna["peran"], "/Login") if pengguna else "/Login")


# ================= 1. UC-K: LOGIN & REGISTRASI WARGA =================
@app.get("/Login", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def halaman_login(request: Request, pesan_sukses: Optional[str] = None, next: Optional[str] = None):
    return render(request, "login.html", {
        "error_message": None,
        "success_message": pesan_sukses,
        "entered_identifier": "",
        "next_url": tujuan_aman(next) or "",
    })


@app.post("/Login", response_class=HTMLResponse)
@app.post("/login", response_class=HTMLResponse)
def proses_login(
    request: Request,
    identifier: str = Form(default=""),
    password: str = Form(default=""),
    next: str = Form(default=""),
    db: Session = Depends(get_db)
):
    hasil = KontrolAutentikasi(db).autentikasi(identifier, password)
    if hasil["success"]:
        simpan_login(request, hasil)
        tujuan = tujuan_aman(next)
        # Only follow "next" if this role may open it; otherwise use the role's home page.
        if tujuan and hasil["role"] == PERAN_WARGA and not tujuan.lower().startswith(("/beranda", "/lapor")):
            tujuan = None
        return RedirectResponse(url=tujuan or hasil["redirect_url"], status_code=303)
    return render(request, "login.html", {
        "error_message": hasil["message"],
        "success_message": None,
        "entered_identifier": identifier,
        "next_url": tujuan_aman(next) or "",
    })


@app.get("/Logout")
@app.get("/logout")
@app.post("/Logout")
def proses_logout(request: Request):
    keluar(request)
    return RedirectResponse(url="/Login", status_code=303)


@app.get("/Register", response_class=HTMLResponse)
@app.get("/register", response_class=HTMLResponse)
def halaman_register(request: Request):
    return render(request, "register.html", {
        "error_message": None,
        "form_data": {"nik": "", "nama_lengkap": "", "no_hp": "", "email": "", "alamat_domisili": ""},
    })


@app.post("/Register", response_class=HTMLResponse)
@app.post("/register", response_class=HTMLResponse)
def proses_register(
    request: Request,
    nik: str = Form(default=""),
    nama_lengkap: str = Form(default=""),
    no_hp: str = Form(default=""),
    email: str = Form(default=""),
    alamat_domisili: str = Form(default=""),
    password: str = Form(default=""),
    konfirmasi_password: str = Form(default=""),
    db: Session = Depends(get_db)
):
    hasil = KontrolAutentikasi(db).registrasi_warga(
        nik=nik, nama_lengkap=nama_lengkap, no_hp=no_hp, email=email,
        alamat_domisili=alamat_domisili, password=password, konfirmasi_password=konfirmasi_password,
    )
    if hasil["success"]:
        return render(request, "login.html", {
            "error_message": None,
            "success_message": hasil["message"],
            "entered_identifier": no_hp,
            "next_url": "",
        })
    return render(request, "register.html", {
        "error_message": hasil["message"],
        "form_data": {"nik": nik, "nama_lengkap": nama_lengkap, "no_hp": no_hp, "email": email,
                      "alamat_domisili": alamat_domisili},
    })


# ================= 2. UC-A: BERANDA & BUAT LAPORAN WARGA =================
@app.get("/Beranda", response_class=HTMLResponse)
@app.get("/beranda", response_class=HTMLResponse)
def halaman_beranda_warga(request: Request, pengguna: dict = Depends(HANYA_WARGA), db: Session = Depends(get_db)):
    laporan_saya = (db.query(Laporan).filter_by(id_warga=pengguna["id"])
                    .order_by(Laporan.tanggal_lapor.desc()).limit(10).all())
    return render(request, "beranda_warga.html", {"laporan_saya": laporan_saya})


def _form_lapor_default() -> dict:
    return {
        "lokasi_jalan": "",
        # No default coordinates: a default point would make unrelated reports look co-located.
        "latitude": None,
        "longitude": None,
        "deskripsi": "",
        "kategori_pilihan": "Jalan Berlubang",
        "id_wilayah": "WIL-01",
    }


@app.get("/lapor", response_class=HTMLResponse)
def halaman_buat_laporan(request: Request, pengguna: dict = Depends(HANYA_WARGA), db: Session = Depends(get_db)):
    return render(request, "buat_laporan.html", {
        "daftar_wilayah": db.query(Wilayah).all(),
        "hasil": request.session.pop("hasil_lapor", None),
        "form_data": _form_lapor_default(),
    })


def _baca_foto(foto: Optional[UploadFile]) -> tuple[str, Optional[bytes]]:
    if foto is None or not foto.filename:
        return "", None
    return foto.filename, foto.file.read(BATAS_BACA_FOTO)


@app.post("/api/analisis-foto")
def api_analisis_foto(foto: UploadFile = File(None), pengguna: dict = Depends(HANYA_WARGA)):
    """Step 1 preview: validate and analyse the photo with the same AI service the submit uses."""
    nama, data = _baca_foto(foto)
    ai = get_ai_service()
    val = ai.validasi_foto(nama, 0, data)
    if not val.valid:
        return JSONResponse({"valid": False, "detected": False, "message": val.message, "mode": ai.mode_cv,
                             "ukuran_mb": round(val.ukuran_mb, 2)})
    cv = ai.analisis_foto(nama, data)
    return JSONResponse({
        "valid": True,
        "detected": cv.detected,
        "message": cv.message,
        "kategori": cv.rekomendasi_kategori,
        "severity": cv.severity_score,
        "confidence": cv.confidence,
        "mode": cv.sumber,
        "ukuran_mb": val.ukuran_mb,
    })


@app.post("/lapor", response_class=HTMLResponse)
def proses_kirim_laporan(
    request: Request,
    foto: UploadFile = File(None),
    lokasi_jalan: str = Form(default=""),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
    deskripsi: str = Form(default=""),
    kategori_pilihan: str = Form(default="Jalan Berlubang"),
    id_wilayah: str = Form(default="WIL-01"),
    pengguna: dict = Depends(HANYA_WARGA),
    db: Session = Depends(get_db)
):
    nama_foto, data_foto = _baca_foto(foto)
    hasil = KontrolPelaporan(db).kirim_laporan(
        filename=nama_foto,
        file_size_mb=0,
        lokasi_jalan=lokasi_jalan,
        latitude=latitude,
        longitude=longitude,
        deskripsi=deskripsi,
        kategori_pilihan=kategori_pilihan,
        id_wilayah=id_wilayah,
        id_warga=pengguna["id"],
        foto_bytes=data_foto,
    )
    if hasil["success"]:
        # Redirect so refreshing the page cannot submit the same report again.
        request.session["hasil_lapor"] = hasil
        return RedirectResponse(url="/lapor", status_code=303)
    form_data = {
        "lokasi_jalan": lokasi_jalan,
        "latitude": latitude,
        "longitude": longitude,
        "deskripsi": deskripsi,
        "kategori_pilihan": kategori_pilihan,
        "id_wilayah": id_wilayah,
    }
    return render(request, "buat_laporan.html", {
        "daftar_wilayah": db.query(Wilayah).all(),
        "hasil": hasil,
        "form_data": form_data,
    })


# ================= 3. UC-H: DASHBOARD PRIORITAS & PETA GIS =================
@app.get("/Dashboard", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def halaman_dashboard_prioritas(
    request: Request,
    wilayah: str = "Semua",
    status: str = "Semua",
    kategori: str = "Semua",
    pesan_aksi: Optional[str] = None,
    pengguna: dict = Depends(LIHAT_DASHBOARD),
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
    aktif = [w for w in semua_wo if w.status_work_order != "Selesai"]
    kasus_selesai = total_aduan - len(aktif)
    kasus_darurat = sum(1 for w in aktif if w.risk_score >= 8.0)
    persentase_selesai = round((kasus_selesai / total_aduan * 100), 1) if total_aduan > 0 else 0.0

    ringkasan_wilayah = []
    for w in daftar_wilayah:
        wo_wil = [item for item in aktif if item.id_wilayah == w.id_wilayah]
        tertinggi = max(wo_wil, key=lambda item: item.risk_score, default=None)
        ringkasan_wilayah.append({
            "nama_wilayah": w.nama_wilayah,
            "jumlah_tiket": len(wo_wil),
            "max_score": tertinggi.risk_score if tertinggi else 0.0,
            "tiket_tertinggi": tertinggi.id_work_order if tertinggi else None,
        })

    peta_tiket = [
        {
            "id": t["wo"].id_work_order,
            "label": t["label_skor"],
            "kategori": t["wo"].kategori_kerusakan,
            "lokasi": t["wo"].lokasi_jalan or "",
            "prioritas": t["wo"].prioritas,
            "lat": t["lat"],
            "lng": t["lng"],
            "warna": t["warna_marker"],
        }
        for t in data_dash["daftar_tiket"]
        if t["lat"] is not None and t["lng"] is not None
    ]

    return render(request, "dashboard_prioritas.html", {
        "daftar_tiket": data_dash["daftar_tiket"],
        "peta_tiket": peta_tiket,
        "pesan_kosong": data_dash["message"],
        "pesan_aksi": pesan_aksi,
        "daftar_wilayah": daftar_wilayah,
        "ringkasan_wilayah": ringkasan_wilayah,
        "filter_wilayah": wilayah,
        "filter_status": status,
        "filter_kategori": kategori,
        "total_aduan": total_aduan,
        "total_aktif": len(aktif),
        "kasus_ditangani": len(aktif),
        "kasus_selesai": kasus_selesai,
        "kasus_darurat": kasus_darurat,
        "persentase_selesai": persentase_selesai,
    })


@app.post("/Dashboard/{ticket_id}/quick-approve")
def aksi_cepat_setujui(ticket_id: str, pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    _wo_atau_404(db, ticket_id)
    KontrolVerifikasi(db).setujui_tiket(ticket_id, pengguna.get("email"))
    pesan = f"Tiket {ticket_id} berhasil diubah menjadi Disetujui melalui Aksi Cepat Dashboard."
    return RedirectResponse(url=f"/Dashboard?pesan_aksi={quote(pesan)}", status_code=303)


# ================= 4. UC-B: VERIFIKASI LAPORAN =================
@app.get("/verifikasi", response_class=HTMLResponse)
def halaman_verifikasi(
    request: Request,
    ticket_id: Optional[str] = None,
    pesan_sukses: Optional[str] = None,
    pengguna: dict = Depends(LIHAT_VERIFIKASI),
    db: Session = Depends(get_db)
):
    controller = KontrolVerifikasi(db)
    semua_tiket = controller.muat_daftar_tiket()
    detail = controller.lihat_detail_tiket(ticket_id) if ticket_id else None
    if not detail and semua_tiket:
        detail = controller.lihat_detail_tiket(semua_tiket[0].id_work_order)

    return render(request, "verifikasi_detail.html", {
        "semua_tiket": semua_tiket, "detail": detail, "pesan_sukses": pesan_sukses,
    })


def _kembali_ke_verifikasi(ticket_id: str, pesan: str):
    return RedirectResponse(url=f"/verifikasi?ticket_id={quote(ticket_id)}&pesan_sukses={quote(pesan)}", status_code=303)


@app.post("/verifikasi/{ticket_id}/approve")
def proses_setujui_tiket(ticket_id: str, pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    _wo_atau_404(db, ticket_id)
    wo = KontrolVerifikasi(db).setujui_tiket(ticket_id, pengguna.get("email"))
    return _kembali_ke_verifikasi(ticket_id, f"Tiket {ticket_id} disetujui ({wo.status_work_order}).")


@app.post("/verifikasi/{ticket_id}/inspect")
def proses_tugaskan_inspeksi(
    ticket_id: str,
    nama_penilik: str = Form(default=""),
    pengguna: dict = Depends(AKSI_ADMIN),
    db: Session = Depends(get_db),
):
    tiket = _wo_atau_404(db, ticket_id)
    if not db.query(PenilikJalan).filter_by(nama_penilik=nama_penilik, id_wilayah=tiket.id_wilayah).first():
        return _kembali_ke_verifikasi(ticket_id, f"Penilik Jalan '{nama_penilik}' tidak ditemukan di wilayah tiket ini.")
    wo = KontrolVerifikasi(db).tugaskan_inspeksi_tambahan(ticket_id, nama_penilik, pengguna.get("email"))
    return _kembali_ke_verifikasi(ticket_id, f"Inspeksi ditugaskan ke {nama_penilik} ({wo.status_work_order}).")


@app.post("/verifikasi/{ticket_id}/skip-inspection")
def proses_lanjutkan_tanpa_inspeksi(ticket_id: str, pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    _wo_atau_404(db, ticket_id)
    wo = KontrolVerifikasi(db).lanjutkan_tanpa_inspeksi(ticket_id, pengguna.get("email"))
    return _kembali_ke_verifikasi(ticket_id, f"Tercatat: {wo.log_keputusan}.")


# ================= 5. UC-G: PENUGASAN PENILIK JALAN =================
@app.get("/work-orders", response_class=HTMLResponse)
def halaman_work_orders(
    request: Request,
    wilayah: str = "Semua",
    status: str = "Semua",
    select_ticket: Optional[str] = None,
    pesan_sukses: Optional[str] = None,
    pengguna: dict = Depends(LIHAT_PENUGASAN),
    db: Session = Depends(get_db)
):
    controller = KontrolPenugasan(db)
    daftar_wo = controller.get_semua_work_order(wilayah, status)
    semua_wo = db.query(WorkOrder).all()
    info_tiket = controller.cek_sla_dan_ketersediaan_penilik(select_ticket) if select_ticket else None

    return render(request, "work_order_list.html", {
        "daftar_wo": daftar_wo,
        "daftar_wilayah": db.query(Wilayah).all(),
        "filter_wilayah": wilayah,
        "filter_status": status,
        "info_tiket": info_tiket,
        "pesan_sukses": pesan_sukses,
        "total_spk": len(semua_wo),
        "jml_menunggu": sum(1 for w in semua_wo if w.status_work_order in ["Disetujui", "Menunggu Penugasan"]),
        "jml_ditugaskan": sum(1 for w in semua_wo if w.status_work_order in ["Ditugaskan", "Dalam Proses"]),
        "jml_selesai": sum(1 for w in semua_wo if w.status_work_order == "Selesai"),
    })


@app.post("/work-orders/{ticket_id}/assign")
def proses_penugasan_penilik(
    ticket_id: str,
    nama_penilik: Optional[str] = Form(default=None),
    pengguna: dict = Depends(AKSI_ADMIN),
    db: Session = Depends(get_db),
):
    _wo_atau_404(db, ticket_id)
    wo = KontrolPenugasan(db).tugaskan_penilik(ticket_id, nama_penilik)
    pesan = f"Tiket {ticket_id} berhasil diperbarui menjadi status: {wo.status_work_order}."
    return RedirectResponse(url=f"/work-orders?pesan_sukses={quote(pesan)}", status_code=303)
