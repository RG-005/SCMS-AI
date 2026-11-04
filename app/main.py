import logging
import os
import secrets
from datetime import timedelta, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
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
from app.controllers.kontrol_inspeksi import KontrolInspeksi
from app.controllers.kontrol_lacak import KontrolLacak
from app.controllers.kontrol_laporan_kinerja import KontrolLaporanKinerja
from app.controllers.kontrol_master_data import STATUS_KETERSEDIAAN, KontrolMasterData
from app.controllers.kontrol_notifikasi import KontrolNotifikasi
from app.controllers.kontrol_penanganan import KontrolPenanganan
from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.controllers.kontrol_penugasan import KontrolPenugasan
from app.controllers.kontrol_verifikasi import KontrolVerifikasi
from app.database import Base, SessionLocal, engine, get_db, pastikan_kolom_terbaru
from app.models.entities import Laporan, PenilikJalan, Wilayah, WorkOrder
from app.controllers.kontrol_penugasan import cari_penilik
from app.controllers.kontrol_verifikasi import SIAP_VERIFIKASI
from app.services.ai_service import UKURAN_MAKS_MB, get_ai_service
from app.services.alur_status import DISETUJUI, KonflikStatus, TransisiTidakSah, boleh_transisi

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

WIB = timezone(timedelta(hours=7))  # Surabaya time; Indonesia has no daylight saving


def format_wib(waktu) -> str:
    """Timestamps are stored in UTC; show them in WIB."""
    if not waktu:
        return ""
    if waktu.tzinfo is None:
        waktu = waktu.replace(tzinfo=timezone.utc)
    return waktu.astimezone(WIB).strftime("%d-%m-%Y %H:%M WIB")


templates.env.filters["wib"] = format_wib

BATAS_BACA_FOTO = int(UKURAN_MAKS_MB * 1024 * 1024) + 1

# Pages a citizen may be sent back to after login ("next"); anything else goes to /Beranda.
HALAMAN_WARGA = ("/beranda", "/lapor", "/lacak", "/notifikasi")

# Who may do what
LIHAT_DASHBOARD = wajib_peran(*PERAN_STAF)
LIHAT_VERIFIKASI = wajib_peran(PERAN_ADMIN, PERAN_KABID)
LIHAT_PENUGASAN = wajib_peran(PERAN_ADMIN, PERAN_KABID, PERAN_PENILIK)
AKSI_ADMIN = wajib_peran(PERAN_ADMIN)
HANYA_WARGA = wajib_peran(PERAN_WARGA)


def _jumlah_notif(pengguna: Optional[dict]) -> int:
    if not pengguna or pengguna["peran"] != PERAN_WARGA:
        return 0
    db = SessionLocal()
    try:
        return KontrolNotifikasi(db).jumlah_belum_dibaca(pengguna["id"])
    finally:
        db.close()


def flash(request: Request, pesan: str, jenis: str = "sukses"):
    """One-time message shown on the next page (post-redirect-get)."""
    request.session["flash"] = {"pesan": pesan, "jenis": jenis}


def render(request: Request, name: str, context: dict, status_code: int = 200):
    pengguna = pengguna_saat_ini(request)
    ctx = {
        "pengguna": pengguna,
        "boleh_aksi": bool(pengguna and pengguna["peran"] == PERAN_ADMIN),
        "mode_ai": get_ai_service().mode_cv,
        "ai_simulasi": get_ai_service().is_simulasi,
        "jumlah_notif": _jumlah_notif(pengguna),
        "flash": request.session.pop("flash", None),
    }
    ctx.update(context)
    return templates.TemplateResponse(request=request, name=name, context=ctx, status_code=status_code)


@app.exception_handler(LoginDiperlukan)
def _login_diperlukan(request: Request, exc: LoginDiperlukan):
    return RedirectResponse(url=f"/Login?next={exc.tujuan}" if exc.tujuan else "/Login", status_code=303)


@app.exception_handler(KonflikStatus)
def _konflik_status(request: Request, exc: KonflikStatus):
    return HTMLResponse(
        f"<h1>409 - Tiket baru saja diperbarui</h1><p>Tiket {exc} diubah oleh permintaan lain pada saat yang sama. "
        f"Tidak ada perubahan yang disimpan dari permintaan Anda.</p><p><a href='javascript:history.back()'>Kembali</a></p>",
        status_code=409,
    )


@app.exception_handler(TransisiTidakSah)
def _transisi_tidak_sah(request: Request, exc: TransisiTidakSah):
    return HTMLResponse(
        f"<h1>409 - Perubahan status tidak diizinkan</h1><p>Tiket {exc.id_work_order} tidak dapat diubah dari "
        f"status {exc.dari} ke {exc.ke}. Tidak ada perubahan yang disimpan.</p>"
        f"<p><a href='javascript:history.back()'>Kembali</a></p>",
        status_code=409,
    )


@app.exception_handler(AksesDitolak)
def _akses_ditolak(request: Request, exc: AksesDitolak):
    beranda = HALAMAN_AWAL.get(exc.pengguna["peran"], "/Login")
    return HTMLResponse(
        f"<h1>403 - Akses ditolak</h1><p>Peran Anda tidak memiliki akses ke halaman ini.</p>"
        f"<p><a href='{beranda}'>Kembali</a> &middot; <a href='/Logout'>Keluar</a></p>",
        status_code=403,
    )


def wilayah_penilik(db: Session, pengguna: dict) -> Optional[str]:
    """Region of a logged-in Penilik Jalan (they only see their own rayon); None for other roles."""
    if pengguna["peran"] != PERAN_PENILIK:
        return None
    penilik = db.get(PenilikJalan, pengguna["id"])
    return penilik.id_wilayah if penilik else "-"


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
        if tujuan and hasil["role"] == PERAN_WARGA and not tujuan.lower().startswith(HALAMAN_WARGA):
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
    wil_penilik = wilayah_penilik(db, pengguna)
    if wil_penilik:
        # Penilik Jalan: always limited to their own rayon, whatever the filter says.
        data_dash = controller.filter_dashboard(wilayah=wil_penilik, status=status, kategori=kategori)
        daftar_wilayah = db.query(Wilayah).filter_by(id_wilayah=wil_penilik).all()
        wilayah = daftar_wilayah[0].nama_wilayah if daftar_wilayah else wilayah
        semua_wo = db.query(WorkOrder).filter_by(id_wilayah=wil_penilik).all()
    else:
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
    sebelum = _wo_atau_404(db, ticket_id).status_work_order
    wo = KontrolVerifikasi(db).setujui_tiket(ticket_id, pengguna.get("email"))
    pesan = (f"Tiket {ticket_id} berhasil diubah menjadi Disetujui melalui Aksi Cepat Dashboard."
             if sebelum != "Disetujui" and wo.status_work_order == "Disetujui"
             else f"Tiket {ticket_id} tidak diubah (status saat ini: {wo.status_work_order}).")
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
    if wo.status_work_order != "Disetujui":
        return _kembali_ke_verifikasi(ticket_id, f"Tiket {ticket_id} tidak dapat disetujui pada status {wo.status_work_order}.")
    return _kembali_ke_verifikasi(ticket_id, f"Tiket {ticket_id} disetujui ({wo.status_work_order}).")


@app.post("/verifikasi/{ticket_id}/inspect")
def proses_tugaskan_inspeksi(
    ticket_id: str,
    nama_penilik: str = Form(default=""),
    pengguna: dict = Depends(AKSI_ADMIN),
    db: Session = Depends(get_db),
):
    tiket = _wo_atau_404(db, ticket_id)
    penilik = cari_penilik(db, nama_penilik, tiket.id_wilayah)
    if not penilik:
        return _kembali_ke_verifikasi(ticket_id, f"Penilik Jalan '{nama_penilik}' tidak ditemukan di wilayah tiket ini.")
    wo = KontrolVerifikasi(db).tugaskan_inspeksi_tambahan(ticket_id, penilik.id_penilik, pengguna.get("email"))
    if wo.status_work_order != "Menunggu Inspeksi":
        return _kembali_ke_verifikasi(ticket_id, f"Tiket {ticket_id} tidak dapat diubah pada status {wo.status_work_order}.")
    return _kembali_ke_verifikasi(ticket_id, f"Inspeksi ditugaskan ke {penilik.nama_penilik} ({wo.status_work_order}).")


@app.post("/verifikasi/{ticket_id}/skip-inspection")
def proses_lanjutkan_tanpa_inspeksi(ticket_id: str, pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    sebelum = _wo_atau_404(db, ticket_id).status_work_order
    bisa_diputuskan = sebelum in SIAP_VERIFIKASI and boleh_transisi(sebelum, DISETUJUI)
    wo = KontrolVerifikasi(db).lanjutkan_tanpa_inspeksi(ticket_id, pengguna.get("email"))
    if not bisa_diputuskan:
        return _kembali_ke_verifikasi(ticket_id, f"Tiket {ticket_id} tidak dapat diubah pada status {wo.status_work_order}.")
    return _kembali_ke_verifikasi(ticket_id, f"Tercatat: {wo.log_keputusan}.")


# ================= 5. UC-G: PENUGASAN PENILIK JALAN =================
def _render_work_orders(request: Request, db: Session, pengguna: dict, wilayah: str = "Semua",
                        status: str = "Semua", select_ticket: Optional[str] = None,
                        pesan_sukses: Optional[str] = None, tambahan: Optional[dict] = None):
    controller = KontrolPenugasan(db)
    wil_penilik = wilayah_penilik(db, pengguna)
    if wil_penilik:
        # Penilik Jalan only see Work Orders of their own rayon (same rule as /TugasLapangan).
        wilayah = wil_penilik
        if select_ticket and _wo_atau_404(db, select_ticket).id_wilayah != wil_penilik:
            raise HTTPException(status_code=404, detail=f"Tiket {select_ticket} tidak ditemukan")
    daftar_wo = controller.get_semua_work_order(wilayah, status)
    q_wo = db.query(WorkOrder)
    q_wil = db.query(Wilayah)
    if wil_penilik:
        q_wo, q_wil = q_wo.filter_by(id_wilayah=wil_penilik), q_wil.filter_by(id_wilayah=wil_penilik)
    semua_wo = q_wo.all()
    info_tiket = controller.cek_sla_dan_ketersediaan_penilik(select_ticket) if select_ticket else None

    return render(request, "work_order_list.html", {
        "daftar_wo": daftar_wo,
        "daftar_wilayah": q_wil.all(),
        "filter_wilayah": wilayah,
        "filter_status": status,
        "info_tiket": info_tiket,
        "pesan_sukses": pesan_sukses,
        "total_spk": len(semua_wo),
        "jml_menunggu": sum(1 for w in semua_wo if w.status_work_order in ["Disetujui", "Menunggu Penugasan"]),
        "jml_ditugaskan": sum(1 for w in semua_wo if w.status_work_order in ["Ditugaskan", "Dalam Proses"]),
        "jml_selesai": sum(1 for w in semua_wo if w.status_work_order == "Selesai"),
        "tim_default": TIM_PELAKSANA_DEFAULT,
        "form_progres": {},
        **(tambahan or {}),
    })


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
    return _render_work_orders(request, db, pengguna, wilayah, status, select_ticket, pesan_sukses)


@app.post("/work-orders/{ticket_id}/assign")
def proses_penugasan_penilik(
    ticket_id: str,
    nama_penilik: Optional[str] = Form(default=None),
    pengguna: dict = Depends(AKSI_ADMIN),
    db: Session = Depends(get_db),
):
    sebelum = _wo_atau_404(db, ticket_id)
    status_sebelum, penilik_sebelum = sebelum.status_work_order, sebelum.id_penilik
    wo = KontrolPenugasan(db).tugaskan_penilik(ticket_id, nama_penilik)
    if (wo.status_work_order, wo.id_penilik) == (status_sebelum, penilik_sebelum):
        pesan = f"Tiket {ticket_id} tidak diubah (status saat ini: {wo.status_work_order})."
    else:
        pesan = f"Tiket {ticket_id} berhasil diperbarui menjadi status: {wo.status_work_order}."
    return RedirectResponse(url=f"/work-orders?pesan_sukses={quote(pesan)}", status_code=303)


# =============================================================================
# SPRINT 2
# =============================================================================
TIM_PELAKSANA_DEFAULT = ["Satgas Rayon Gubeng", "Satgas Rayon Benowo", "Satgas Rayon Wonokromo"]
LIHAT_MASTER_DATA = wajib_peran(PERAN_ADMIN, PERAN_KABID)
HANYA_PENILIK = wajib_peran(PERAN_PENILIK)


# ================= UC-C & UC-J: LACAK LAPORAN, RATING (WARGA) =================
def _render_lacak(request: Request, db: Session, pengguna: dict, id_laporan: Optional[str],
                  pesan: Optional[dict] = None, form_rating: Optional[dict] = None, status_code: int = 200):
    controller = KontrolLacak(db)
    detail = controller.detail_lacak(id_laporan, pengguna["id"]) if id_laporan else None
    return render(request, "lacak_laporan.html", {
        "daftar_laporan": controller.daftar_laporan_warga(pengguna["id"]),
        "cari_id": (id_laporan or "").strip(),
        "detail": detail if detail and detail["success"] else None,
        "pesan_cari": detail["message"] if detail and not detail["success"] else None,
        "pesan": pesan,
        "form_rating": form_rating or {},
    }, status_code=status_code)


@app.get("/lacak", response_class=HTMLResponse)
def halaman_lacak(request: Request, id: Optional[str] = None,
                  pengguna: dict = Depends(HANYA_WARGA), db: Session = Depends(get_db)):
    return _render_lacak(request, db, pengguna, id)


@app.post("/lacak/{id_laporan}/rating", response_class=HTMLResponse)
def proses_rating(request: Request, id_laporan: str, nilai_bintang: str = Form(default=""),
                  komentar: str = Form(default=""), pengguna: dict = Depends(HANYA_WARGA),
                  db: Session = Depends(get_db)):
    hasil = KontrolLacak(db).simpan_rating(id_laporan, pengguna["id"], nilai_bintang, komentar)
    if hasil["success"]:
        flash(request, hasil["message"])
        return RedirectResponse(url=f"/lacak?id={quote(id_laporan)}", status_code=303)
    return _render_lacak(request, db, pengguna, id_laporan, {"jenis": "peringatan", "pesan": hasil["message"]},
                         {"komentar": komentar})


# ================= UC-I: NOTIFIKASI (WARGA) =================
@app.get("/notifikasi", response_class=HTMLResponse)
def halaman_notifikasi(request: Request, pengguna: dict = Depends(HANYA_WARGA), db: Session = Depends(get_db)):
    return render(request, "notifikasi.html", {"daftar_notif": KontrolNotifikasi(db).daftar(pengguna["id"])})


@app.get("/notifikasi/{id_notifikasi}/buka")
def buka_notifikasi(id_notifikasi: str, pengguna: dict = Depends(HANYA_WARGA), db: Session = Depends(get_db)):
    id_laporan = KontrolNotifikasi(db).buka(id_notifikasi, pengguna["id"])
    if not id_laporan:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return RedirectResponse(url=f"/lacak?id={quote(id_laporan)}", status_code=303)


@app.post("/notifikasi/baca-semua")
def baca_semua_notifikasi(request: Request, pengguna: dict = Depends(HANYA_WARGA), db: Session = Depends(get_db)):
    KontrolNotifikasi(db).tandai_semua_dibaca(pengguna["id"])
    return RedirectResponse(url="/notifikasi", status_code=303)


# ================= UC-D: DATA MASTER (ADMIN) =================
def _render_master(request: Request, db: Session, pesan: Optional[dict] = None, form: Optional[dict] = None,
                   akun_baru: Optional[dict] = None):
    data = KontrolMasterData(db).muat()
    return render(request, "master_data.html", {
        **data, "pesan": pesan, "form": form or {}, "akun_baru": akun_baru,
        "status_ketersediaan": STATUS_KETERSEDIAAN,
    })


@app.get("/master-data", response_class=HTMLResponse)
def halaman_master_data(request: Request, pengguna: dict = Depends(LIHAT_MASTER_DATA), db: Session = Depends(get_db)):
    return _render_master(request, db)


@app.post("/master-data/wilayah", response_class=HTMLResponse)
def proses_tambah_wilayah(request: Request, kode_wilayah: str = Form(default=""), nama_wilayah: str = Form(default=""),
                          kecamatan: str = Form(default=""), pengguna: dict = Depends(AKSI_ADMIN),
                          db: Session = Depends(get_db)):
    hasil = KontrolMasterData(db).tambah_wilayah(kode_wilayah, nama_wilayah, kecamatan)
    if hasil["success"]:
        flash(request, hasil["message"])
        return RedirectResponse(url="/master-data", status_code=303)
    return _render_master(request, db, {"jenis": "gagal", "pesan": hasil["message"]},
                          {"kode_wilayah": kode_wilayah, "nama_wilayah": nama_wilayah, "kecamatan": kecamatan})


@app.post("/master-data/penilik", response_class=HTMLResponse)
def proses_tambah_penilik(request: Request, nip: str = Form(default=""), nama_penilik: str = Form(default=""),
                          id_wilayah: str = Form(default=""), email_penilik: str = Form(default=""),
                          pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    hasil = KontrolMasterData(db).tambah_penilik(nip, nama_penilik, id_wilayah, email_penilik)
    if hasil["success"]:
        # Rendered directly (not redirected) so the one-time password never goes into the session cookie.
        return _render_master(request, db, {"jenis": "sukses", "pesan": hasil["message"]}, akun_baru=hasil["akun_baru"])
    return _render_master(request, db, {"jenis": "gagal", "pesan": hasil["message"]},
                          {"nip": nip, "nama_penilik": nama_penilik, "id_wilayah": id_wilayah, "email_penilik": email_penilik})


@app.post("/master-data/penilik/{id_penilik}/ketersediaan")
def proses_ubah_ketersediaan(request: Request, id_penilik: str, status: str = Form(default=""),
                             pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    hasil = KontrolMasterData(db).ubah_ketersediaan(id_penilik, status)
    if not hasil["success"]:
        raise HTTPException(status_code=404, detail="Penilik Jalan tidak ditemukan")
    flash(request, hasil["message"])
    return RedirectResponse(url="/master-data", status_code=303)


# ================= UC-E & UC-F: TUGAS LAPANGAN (PENILIK JALAN) =================
@app.get("/TugasLapangan", response_class=HTMLResponse)
@app.get("/tugaslapangan", response_class=HTMLResponse)
def halaman_tugas_lapangan(request: Request, pengguna: dict = Depends(HANYA_PENILIK), db: Session = Depends(get_db)):
    return render(request, "tugas_lapangan.html", KontrolInspeksi(db).daftar_tugas(pengguna["id"]))


def _render_tugas_detail(request: Request, db: Session, pengguna: dict, id_work_order: str,
                         pesan: Optional[dict] = None, form: Optional[dict] = None):
    detail = KontrolInspeksi(db).detail(id_work_order, pengguna["id"])
    if not detail:
        raise HTTPException(status_code=404, detail="Tugas tidak ditemukan")
    return render(request, "tugas_lapangan_detail.html", {**detail, "pesan": pesan, "form": form or {}})


@app.get("/TugasLapangan/{id_work_order}", response_class=HTMLResponse)
def halaman_tugas_detail(request: Request, id_work_order: str, pengguna: dict = Depends(HANYA_PENILIK),
                         db: Session = Depends(get_db)):
    return _render_tugas_detail(request, db, pengguna, id_work_order)


@app.post("/TugasLapangan/{id_work_order}/inspeksi", response_class=HTMLResponse)
def proses_simpan_inspeksi(request: Request, id_work_order: str, dimensi_kerusakan: str = Form(default=""),
                           catatan_teknis: str = Form(default=""), rekomendasi: str = Form(default=""),
                           foto_survei: UploadFile = File(None), pengguna: dict = Depends(HANYA_PENILIK),
                           db: Session = Depends(get_db)):
    if not KontrolInspeksi(db).detail(id_work_order, pengguna["id"]):
        raise HTTPException(status_code=404, detail="Tugas tidak ditemukan")
    nama_foto, data_foto = _baca_foto(foto_survei)
    hasil = KontrolInspeksi(db).simpan_inspeksi(id_work_order, pengguna["id"], dimensi_kerusakan,
                                                catatan_teknis, rekomendasi, nama_foto, data_foto)
    if hasil["success"]:
        flash(request, hasil["message"])
        return RedirectResponse(url=f"/TugasLapangan/{quote(id_work_order)}", status_code=303)
    return _render_tugas_detail(request, db, pengguna, id_work_order, {"jenis": "peringatan", "pesan": hasil["message"]},
                                {"dimensi_kerusakan": dimensi_kerusakan, "catatan_teknis": catatan_teknis,
                                 "rekomendasi": rekomendasi})


@app.post("/TugasLapangan/{id_work_order}/progres", response_class=HTMLResponse)
def proses_progres_penilik(request: Request, id_work_order: str, status_baru: str = Form(default=""),
                           catatan_progres: str = Form(default=""), foto_selesai: UploadFile = File(None),
                           pengguna: dict = Depends(HANYA_PENILIK), db: Session = Depends(get_db)):
    if not KontrolInspeksi(db).detail(id_work_order, pengguna["id"]):
        raise HTTPException(status_code=404, detail="Tugas tidak ditemukan")
    nama_foto, data_foto = _baca_foto(foto_selesai)
    hasil = KontrolPenanganan(db).perbarui_progres(id_work_order, status_baru, catatan_progres,
                                                   nama_foto, data_foto, pengguna["nama"])
    if hasil["success"]:
        flash(request, hasil["message"])
        return RedirectResponse(url=f"/TugasLapangan/{quote(id_work_order)}", status_code=303)
    return _render_tugas_detail(request, db, pengguna, id_work_order, {"jenis": "gagal", "pesan": hasil["message"]},
                                {"status_baru": status_baru, "catatan_progres": catatan_progres})


# ================= UC-F: SPK & PROGRES (ADMIN, DARI HALAMAN WORK ORDER) =================
@app.post("/work-orders/{ticket_id}/spk")
def proses_terbitkan_spk(request: Request, ticket_id: str, nomor_spk: str = Form(default=""),
                         tim_pelaksana: str = Form(default=""), status_awal: str = Form(default="Dalam Proses"),
                         pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    _wo_atau_404(db, ticket_id)
    hasil = KontrolPenanganan(db).terbitkan_spk(ticket_id, nomor_spk, tim_pelaksana, status_awal, pengguna.get("email"))
    flash(request, hasil["message"], "sukses" if hasil["success"] else "gagal")
    return RedirectResponse(url=f"/work-orders?select_ticket={quote(ticket_id)}", status_code=303)


@app.post("/work-orders/{ticket_id}/progres")
def proses_progres_admin(request: Request, ticket_id: str, status_baru: str = Form(default=""),
                         catatan_progres: str = Form(default=""), foto_selesai: UploadFile = File(None),
                         pengguna: dict = Depends(AKSI_ADMIN), db: Session = Depends(get_db)):
    _wo_atau_404(db, ticket_id)
    nama_foto, data_foto = _baca_foto(foto_selesai)
    hasil = KontrolPenanganan(db).perbarui_progres(ticket_id, status_baru, catatan_progres, nama_foto, data_foto,
                                                   pengguna.get("email"))
    if hasil["success"]:
        flash(request, hasil["message"])
        return RedirectResponse(url=f"/work-orders?select_ticket={quote(ticket_id)}", status_code=303)
    # Rendered directly so the typed note and chosen status stay in the form next to the error.
    return _render_work_orders(request, db, pengguna, select_ticket=ticket_id, tambahan={
        "flash": {"pesan": hasil["message"], "jenis": "gagal"},
        "form_progres": {"status_baru": status_baru, "catatan_progres": catatan_progres},
    })


# ================= UC-L: LAPORAN KINERJA INFRASTRUKTUR (KEPALA BIDANG / ADMIN) =================
LIHAT_LAPORAN_KINERJA = wajib_peran(PERAN_ADMIN, PERAN_KABID)
JENIS_UNDUHAN = ("wilayah", "tiket")


@app.get("/laporan-kinerja", response_class=HTMLResponse)
def halaman_laporan_kinerja(request: Request, tanggal_mulai: str = "", tanggal_akhir: str = "",
                            wilayah: str = "Semua", pengguna: dict = Depends(LIHAT_LAPORAN_KINERJA),
                            db: Session = Depends(get_db)):
    data = KontrolLaporanKinerja(db).rekap(tanggal_mulai, tanggal_akhir, wilayah)
    pesan = None if data["success"] else {"jenis": "gagal", "pesan": data["message"]}
    return render(request, "laporan_kinerja.html", {**data, "pesan": pesan},
                  status_code=200 if data["success"] else 400)


@app.get("/laporan-kinerja/unduh")
def unduh_laporan_kinerja(jenis: str = "wilayah", tanggal_mulai: str = "", tanggal_akhir: str = "",
                          wilayah: str = "Semua", pengguna: dict = Depends(LIHAT_LAPORAN_KINERJA),
                          db: Session = Depends(get_db)):
    if jenis not in JENIS_UNDUHAN:
        raise HTTPException(status_code=400, detail="Jenis unduhan harus 'wilayah' atau 'tiket'")
    controller = KontrolLaporanKinerja(db)
    data = controller.rekap(tanggal_mulai, tanggal_akhir, wilayah)
    if not data["success"]:
        raise HTTPException(status_code=400, detail=data["message"])
    isi = controller.csv_per_wilayah(data) if jenis == "wilayah" else controller.csv_per_tiket(data)
    # dates were validated by rekap(), so they are safe to put in the file name
    periode = f"{tanggal_mulai.strip() or 'awal'}_sd_{tanggal_akhir.strip() or 'kini'}"
    return Response(
        content=isi.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="laporan_kinerja_{jenis}_{periode}.csv"'},
    )
