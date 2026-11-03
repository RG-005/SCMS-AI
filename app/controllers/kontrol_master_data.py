"""UC-D: kelola data master Wilayah Rayon dan Penilik Jalan (Admin)."""
import re
import secrets
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Admin, PenilikJalan, Warga, Wilayah, WorkOrder
from app.services.alur_status import SELESAI
from app.services.penyimpanan import id_berurutan

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PESAN_OK = "Data master berhasil diperbarui"
PESAN_DUPLIKAT = "Kode Wilayah atau NIP Penilik Jalan sudah terdaftar di sistem"
PESAN_TIDAK_LENGKAP = "Data belum lengkap, isi semua kolom wajib"
PESAN_NIP_TIDAK_VALID = "Format NIP tidak valid (18 digit angka)"
PESAN_KODE_TIDAK_VALID = "Kode Wilayah hanya boleh berisi huruf, angka, dan tanda hubung (2-20 karakter)"
PESAN_EMAIL_DIPAKAI = "Email sudah dipakai akun lain"
STATUS_KETERSEDIAAN = ("Tersedia", "Penuh", "Cuti")


class KontrolMasterData:
    def __init__(self, db: Session):
        self.db = db

    def muat(self) -> dict:
        wilayah = self.db.query(Wilayah).order_by(Wilayah.id_wilayah).all()
        penilik = self.db.query(PenilikJalan).order_by(PenilikJalan.id_wilayah, PenilikJalan.nama_penilik).all()
        beban = dict(
            self.db.query(WorkOrder.id_penilik, func.count())
            .filter(WorkOrder.id_penilik.isnot(None), WorkOrder.status_work_order != SELESAI)
            .group_by(WorkOrder.id_penilik).all()
        )
        nama_wilayah = {w.id_wilayah: w.nama_wilayah for w in wilayah}
        return {
            "wilayah": [
                {"w": w, "jumlah_penilik": sum(1 for p in penilik if p.id_wilayah == w.id_wilayah)}
                for w in wilayah
            ],
            "penilik": [
                {"p": p, "nama_wilayah": nama_wilayah.get(p.id_wilayah, "-"), "beban_aktif": beban.get(p.id_penilik, 0)}
                for p in penilik
            ],
        }

    def tambah_wilayah(self, kode: str, nama: str, kecamatan: str = "") -> dict:
        kode = (kode or "").strip().upper()
        nama = (nama or "").strip()
        if not kode or not nama:
            return {"success": False, "message": PESAN_TIDAK_LENGKAP}
        if not re.fullmatch(r"[A-Z0-9-]{2,20}", kode):
            return {"success": False, "message": PESAN_KODE_TIDAK_VALID}
        sudah_ada = (self.db.get(Wilayah, kode)
                     or self.db.query(Wilayah).filter(func.lower(Wilayah.nama_wilayah) == nama.lower()).first())
        if sudah_ada:
            return {"success": False, "message": PESAN_DUPLIKAT}
        self.db.add(Wilayah(id_wilayah=kode, nama_wilayah=nama[:50], kecamatan=(kecamatan or "").strip()[:100] or None))
        self.db.commit()
        return {"success": True, "message": PESAN_OK}

    def _email_dipakai(self, email: str) -> bool:
        e = email.lower()
        return bool(
            self.db.query(Admin).filter(func.lower(Admin.email_admin) == e).first()
            or self.db.query(PenilikJalan).filter(func.lower(PenilikJalan.email_penilik) == e).first()
            or self.db.query(Warga).filter(func.lower(Warga.email) == e).first()
        )

    def tambah_penilik(self, nip: str, nama: str, id_wilayah: str, email: Optional[str] = None) -> dict:
        nip = (nip or "").strip()
        nama = (nama or "").strip()
        email = (email or "").strip() or None
        # A registered NIP is reported first, even if the rest of the form is still empty.
        if nip and self.db.query(PenilikJalan).filter_by(nip=nip).first():
            return {"success": False, "message": PESAN_DUPLIKAT}
        if not nip or not nama or not id_wilayah:
            return {"success": False, "message": PESAN_TIDAK_LENGKAP}
        if not re.fullmatch(r"\d{18}", nip):
            return {"success": False, "message": PESAN_NIP_TIDAK_VALID}
        if not self.db.get(Wilayah, id_wilayah):
            return {"success": False, "message": PESAN_TIDAK_LENGKAP}
        if email and (not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or self._email_dipakai(email)):
            return {"success": False, "message": PESAN_EMAIL_DIPAKAI}

        sandi_sementara = secrets.token_urlsafe(9)
        penilik = PenilikJalan(
            id_penilik=id_berurutan(self.db, PenilikJalan.id_penilik, "PNL", digit=2, per_tahun=False),
            id_wilayah=id_wilayah,
            nama_penilik=nama[:50],
            nip=nip,
            email_penilik=email,
            password_hash=pwd_context.hash(sandi_sementara),
            status_ketersediaan="Tersedia",
            is_active=True,
        )
        self.db.add(penilik)
        self.db.commit()
        return {
            "success": True,
            "message": PESAN_OK,
            # shown once to the admin so the new inspector can log in (with NIP or email)
            "akun_baru": {"nama": penilik.nama_penilik, "nip": nip, "email": email, "sandi_sementara": sandi_sementara},
        }

    def ubah_ketersediaan(self, id_penilik: str, status: str) -> dict:
        penilik = self.db.get(PenilikJalan, id_penilik)
        if not penilik or status not in STATUS_KETERSEDIAAN:
            return {"success": False, "message": PESAN_TIDAK_LENGKAP}
        penilik.status_ketersediaan = status
        self.db.commit()
        return {"success": True, "message": PESAN_OK}
