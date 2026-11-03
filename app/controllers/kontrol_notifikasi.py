"""UC-I: daftar notifikasi Warga dan penandaan sudah dibaca."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Notifikasi


class KontrolNotifikasi:
    def __init__(self, db: Session):
        self.db = db

    def daftar(self, id_warga: str, batas: int = 50):
        return (self.db.query(Notifikasi).filter_by(id_warga=id_warga)
                .order_by(Notifikasi.waktu_kirim.desc(), Notifikasi.id_notifikasi.desc())
                .limit(batas).all())

    def jumlah_belum_dibaca(self, id_warga: str) -> int:
        return self.db.query(Notifikasi).filter_by(id_warga=id_warga, status_baca=False).count()

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
