import re

from sqlalchemy import func
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.models.entities import Warga, Admin, PenilikJalan

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
DOMAIN_EMAIL_STAF = "@dpupr.surabaya.go.id"


class KontrolAutentikasi:
    def __init__(self, db: Session):
        self.db = db

    def autentikasi(self, identifier: str, password: str):
        if not identifier:
            return {'success': False, 'message': 'Akun tidak ditemukan', 'redirect_url': '/Login'}
        identifier = identifier.strip()
        akun, peran, nama, id_akun, email = None, None, None, None, None

        # Staff accounts are matched first, so a citizen account can never
        # shadow a staff email (registration also blocks staff emails).
        identifier_lower = identifier.lower()
        admin = self.db.query(Admin).filter(func.lower(Admin.email_admin) == identifier_lower).first()
        if admin:
            akun, peran, nama = admin, ('Kepala Bidang' if admin.is_kepala_bidang else 'Admin'), admin.nama_admin
            id_akun, email = admin.id_admin, admin.email_admin

        if not akun:
            penilik = self.db.query(PenilikJalan).filter(func.lower(PenilikJalan.email_penilik) == identifier_lower).first()
            if penilik:
                akun, peran, nama = penilik, 'Penilik Jalan', penilik.nama_penilik
                id_akun, email = penilik.id_penilik, penilik.email_penilik

        if not akun:
            # Warga: email, phone number, or 16-digit NIK
            warga = self.db.query(Warga).filter(
                (func.lower(Warga.email) == identifier_lower) |
                (Warga.no_hp == identifier) |
                (Warga.nik == identifier)
            ).first()
            if warga:
                akun, peran, nama = warga, 'Warga', warga.nama_warga
                id_akun, email = warga.id_warga, warga.email

        if not akun:
            return {'success': False, 'message': 'Akun tidak ditemukan', 'redirect_url': '/Login'}
        # Check the password before revealing whether the account is inactive.
        if not pwd_context.verify(password or "", akun.password_hash):
            return {'success': False, 'message': 'Email/nomor HP atau password salah', 'redirect_url': '/Login'}
        if not akun.is_active:
            return {'success': False, 'message': 'Akun Anda tidak aktif, silakan hubungi administrator', 'redirect_url': '/Login'}

        redirect_url = '/Beranda' if peran == 'Warga' else '/Dashboard'
        return {
            'success': True,
            'id': id_akun,
            'email': email,
            'role': peran,
            'nama': nama,
            'identifier': identifier,
            'redirect_url': redirect_url,
            'message': 'Login berhasil'
        }

    def registrasi_warga(
        self,
        nik: str,
        nama_lengkap: str,
        no_hp: str,
        email: str,
        alamat_domisili: str,
        password: str,
        konfirmasi_password: str
    ) -> dict:
        nik_clean = (nik or "").strip()
        nama_clean = (nama_lengkap or "").strip()
        hp_clean = (no_hp or "").strip()
        email_clean = (email or "").strip()
        alamat_clean = (alamat_domisili or "").strip()
        pass_clean = (password or "").strip()
        konf_clean = (konfirmasi_password or "").strip()

        # 1. Validasi kolom wajib
        if not nik_clean or not nama_clean or not hp_clean or not pass_clean:
            return {
                "success": False,
                "message": "NIK, Nama Lengkap, Nomor HP, dan Password wajib diisi",
                "user": None
            }

        # 2. Validasi format NIK (Wajib 16 digit angka)
        if not nik_clean.isdigit() or len(nik_clean) != 16:
            return {
                "success": False,
                "message": "Format NIK tidak valid, NIK wajib terdiri dari 16 digit angka sesuai KTP",
                "user": None
            }

        # 3. Validasi format Nomor HP (Angka, 10-15 digit)
        if not hp_clean.isdigit() or not (10 <= len(hp_clean) <= 15):
            return {
                "success": False,
                "message": "Format Nomor HP tidak valid (gunakan 10-15 digit angka, contoh: 081234567890)",
                "user": None
            }

        # 4. Validasi panjang & kecocokan password
        if len(pass_clean) < 6:
            return {
                "success": False,
                "message": "Password minimal terdiri dari 6 karakter",
                "user": None
            }

        if pass_clean != konf_clean:
            return {
                "success": False,
                "message": "Password dan Konfirmasi Password tidak cocok",
                "user": None
            }

        # 5. Cek keunikan NIK (1 Warga = 1 Akun)
        if self.db.query(Warga).filter(Warga.nik == nik_clean).first():
            return {
                "success": False,
                "message": "NIK sudah terdaftar pada akun lain (1 NIK hanya berlaku untuk 1 akun Warga)",
                "user": None
            }

        # 6. Cek keunikan Nomor HP
        if self.db.query(Warga).filter(Warga.no_hp == hp_clean).first():
            return {
                "success": False,
                "message": "Nomor HP sudah terdaftar pada akun lain, silakan gunakan nomor lain atau login",
                "user": None
            }

        # 7. Email: valid shape, not a staff address, unique across ALL account types
        if email_clean:
            email_lower = email_clean.lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_clean):
                return {"success": False, "message": "Format email tidak valid", "user": None}
            email_staf = (
                email_lower.endswith(DOMAIN_EMAIL_STAF)
                or self.db.query(Admin).filter(func.lower(Admin.email_admin) == email_lower).first()
                or self.db.query(PenilikJalan).filter(func.lower(PenilikJalan.email_penilik) == email_lower).first()
            )
            if email_staf:
                return {
                    "success": False,
                    "message": "Email instansi tidak dapat digunakan untuk akun Warga",
                    "user": None
                }
            if self.db.query(Warga).filter(func.lower(Warga.email) == email_lower).first():
                return {
                    "success": False,
                    "message": "Email sudah terdaftar pada akun lain",
                    "user": None
                }

        # 8. Generate ID Warga baru (USR-03, USR-04, dst.) from the highest existing number
        angka = [int(m.group(1)) for (i,) in self.db.query(Warga.id_warga).all() if (m := re.fullmatch(r"USR-(\d+)", i or ""))]
        id_baru = f"USR-{max(angka, default=0) + 1:02d}"

        # Hash password dengan bcrypt (sama persis dengan seed.py & autentikasi)
        hashed_pw = pwd_context.hash(pass_clean)

        warga_baru = Warga(
            id_warga=id_baru,
            nik=nik_clean,
            nama_warga=nama_clean,
            no_hp=hp_clean,
            email=email_clean if email_clean else f"{hp_clean}@warga.surabaya.id",
            alamat_domisili=alamat_clean if alamat_clean else "Kota Surabaya",
            password_hash=hashed_pw,
            is_active=True,
        )
        self.db.add(warga_baru)
        self.db.commit()
        self.db.refresh(warga_baru)

        return {
            "success": True,
            "message": f"Registrasi berhasil! Akun Warga ({nama_clean} - NIK {nik_clean}) telah aktif, silakan login.",
            "user": warga_baru
        }