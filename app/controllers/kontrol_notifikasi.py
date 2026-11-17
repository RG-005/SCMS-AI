"""UC-I: daftar notifikasi Warga dan penandaan sudah dibaca; Sprint 3 BR-8: Notifikasi Gagal dan Kirim Ulang."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Notifikasi
from app.services.pengiriman_notifikasi import KIRIM_GAGAL, KIRIM_MENUNGGU, jalankan_siklus_kirim

PESAN_KIRIM_ULANG_OK = "Notifikasi berhasil dikirim ulang"
PESAN_KIRIM_ULANG_GAGAL = "Pengiriman ulang gagal, silakan coba lagi"
PESAN_BUKAN_GAGAL = ("Notifikasi laporan {id_laporan} berstatus {status}, bukan Gagal, "
                     "sehingga tidak dikirim ulang")
PESAN_TIDAK_ADA_GAGAL = "Tidak ada notifikasi gagal"


class KontrolNotifikasi:
    def __init__(self, db: Session):
        self.db = db

    def daftar(self, id_warga: str, batas: int = 50):
        return (self.db.query(Notifikasi).filter_by(id_warga=id_warga)
                .order_by(Notifikasi.waktu_kirim.desc(), Notifikasi.id_notifikasi.desc())
                .limit(batas).all())

    def jumlah_belum_dibaca(self, id_warga: str) -> int:
        return self.db.query(Notifikasi).filter_by(id_warga=id_warga, status_baca=False).count()

    def belum_dibaca_terbaru(self, id_warga: str, batas: int = 5) -> list:
        """Sprint 3 backlog 2: the citizen's newest unread notifications, for the live badge and toast."""
        return (self.db.query(Notifikasi).filter_by(id_warga=id_warga, status_baca=False)
                .order_by(Notifikasi.waktu_kirim.desc(), Notifikasi.id_notifikasi.desc())
                .limit(batas).all())

    def buka(self, id_notifikasi: str, id_warga: str) -> Optional[str]:
        """Mark a citizen's own notification as read; return the report it points to."""
        notif = self.db.query(Notifikasi).filter_by(id_notifikasi=id_notifikasi, id_warga=id_warga).first()
        if not notif:
            return None
        if not notif.status_baca:
            notif.status_baca = True
            self.db.commit()
        return notif.id_laporan

    def tandai_semua_dibaca(self, id_warga: str) -> int:
        jumlah = (self.db.query(Notifikasi).filter_by(id_warga=id_warga, status_baca=False)
                  .update({Notifikasi.status_baca: True}))
        self.db.commit()
        return jumlah

    # ---------------- Sprint 3 BR-8: Notifikasi Gagal & Kirim Ulang (staf) ----------------
    def daftar_gagal(self):
        """Notifications whose outside delivery failed (Admin + Kepala Bidang may view)."""
        return (self.db.query(Notifikasi).filter_by(status_kirim=KIRIM_GAGAL)
                .order_by(Notifikasi.waktu_percobaan_terakhir.desc(), Notifikasi.id_notifikasi.desc())
                .all())

    def jumlah_gagal(self) -> int:
        return self.db.query(Notifikasi).filter_by(status_kirim=KIRIM_GAGAL).count()

    def kirim_ulang(self, id_notifikasi: str) -> Optional[dict]:
        """Admin "Kirim Ulang": one more send cycle (1 + max 3 retries) for a Gagal notification.
        None when the notification does not exist. Only Gagal is resent: the row is claimed with a
        compare-and-set, so two simultaneous clicks cannot send it twice."""
        notif = self.db.get(Notifikasi, id_notifikasi)
        if notif is None:
            return None
        diklaim = (self.db.query(Notifikasi)
                   .filter(Notifikasi.id_notifikasi == id_notifikasi, Notifikasi.status_kirim == KIRIM_GAGAL)
                   .update({Notifikasi.status_kirim: KIRIM_MENUNGGU}, synchronize_session=False))
        if diklaim != 1:
            self.db.rollback()
            return {"success": False, "jenis": "peringatan", "message": PESAN_BUKAN_GAGAL.format(
                id_laporan=notif.id_laporan, status=notif.status_kirim or "-")}
        self.db.refresh(notif)
        berhasil = jalankan_siklus_kirim(notif)
        self.db.commit()
        if berhasil:
            return {"success": True, "jenis": "sukses", "message": PESAN_KIRIM_ULANG_OK}
        return {"success": False, "jenis": "gagal", "message": PESAN_KIRIM_ULANG_GAGAL}
