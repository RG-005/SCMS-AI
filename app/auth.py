"""
Session-based login and role checks.

After a successful login the session cookie (signed by Starlette's
SessionMiddleware) holds the user's id, role, name and email. Routes declare
who may use them with `Depends(wajib_peran(...))`.
"""
from typing import Optional
from urllib.parse import quote

from fastapi import Request

PERAN_WARGA = "Warga"
PERAN_ADMIN = "Admin"
PERAN_KABID = "Kepala Bidang"
PERAN_PENILIK = "Penilik Jalan"
PERAN_STAF = (PERAN_ADMIN, PERAN_KABID, PERAN_PENILIK)

HALAMAN_AWAL = {
    PERAN_WARGA: "/Beranda",
    PERAN_ADMIN: "/Dashboard",
    PERAN_KABID: "/Dashboard",
    PERAN_PENILIK: "/Dashboard",
}


class LoginDiperlukan(Exception):
    def __init__(self, tujuan: str):
        self.tujuan = tujuan


class AksesDitolak(Exception):
    def __init__(self, pengguna: dict):
        self.pengguna = pengguna


def pengguna_saat_ini(request: Request) -> Optional[dict]:
    return request.session.get("pengguna")


def simpan_login(request: Request, hasil_autentikasi: dict) -> None:
    request.session.clear()
    request.session["pengguna"] = {
        "id": hasil_autentikasi["id"],
        "peran": hasil_autentikasi["role"],
        "nama": hasil_autentikasi["nama"],
        "email": hasil_autentikasi.get("email"),
    }


def keluar(request: Request) -> None:
    request.session.clear()


def tujuan_aman(tujuan: Optional[str]) -> Optional[str]:
    """Allow only same-site relative paths as post-login redirect targets."""
    if tujuan and tujuan.startswith("/") and not tujuan.startswith("//") and "\\" not in tujuan:
        return tujuan
    return None


def akun_masih_aktif(pengguna: dict) -> bool:
    """Re-check the account on every request, so deactivating it ends existing sessions."""
    from app.database import SessionLocal
    from app.models.entities import Admin, PenilikJalan, Warga

    model = {PERAN_WARGA: Warga, PERAN_ADMIN: Admin, PERAN_KABID: Admin, PERAN_PENILIK: PenilikJalan}.get(pengguna.get("peran"))
    if model is None:
        return False
    db = SessionLocal()
    try:
        akun = db.get(model, pengguna.get("id"))
        if akun is None or not akun.is_active:
            return False
        if model is Admin and (pengguna["peran"] == PERAN_KABID) != bool(akun.is_kepala_bidang):
            return False  # role changed since login
        return True
    finally:
        db.close()


def wajib_peran(*peran_diizinkan: str):
    """FastAPI dependency: require a logged-in user with one of the given roles."""

    def _cek(request: Request) -> dict:
        pengguna = pengguna_saat_ini(request)
        if pengguna and not akun_masih_aktif(pengguna):
            keluar(request)
            pengguna = None
        if not pengguna:
            # Come back to the same page after login (GET only: a POST action can't be replayed as GET).
            tujuan = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            raise LoginDiperlukan(quote(tujuan, safe="") if request.method == "GET" else "")
        if peran_diizinkan and pengguna["peran"] not in peran_diizinkan:
            raise AksesDitolak(pengguna)
        return pengguna

    return _cek
