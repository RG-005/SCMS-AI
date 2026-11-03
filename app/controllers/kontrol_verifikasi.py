from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Admin, Laporan, PenilikJalan, Wilayah, WorkOrder
from app.controllers.kontrol_penugasan import cari_penilik, label_penilik
from app.services.alur_status import DILAPORKAN, DISETUJUI, MENUNGGU_INSPEKSI, MENUNGGU_PENUGASAN, ubah_status

# Verification decisions are only possible before field work starts.
SIAP_VERIFIKASI = (DILAPORKAN, DISETUJUI, MENUNGGU_INSPEKSI, MENUNGGU_PENUGASAN)


class KontrolVerifikasi:
    def __init__(self, db: Session):
        self.db = db

    def _wo(self, id_work_order: str) -> Optional[WorkOrder]:
        return self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()

    def _wo_siap(self, id_work_order: str) -> tuple[Optional[WorkOrder], bool]:
        wo = self._wo(id_work_order)
        return wo, bool(wo and wo.status_work_order in SIAP_VERIFIKASI)

    def _catat_admin(self, wo: WorkOrder, email_admin: Optional[str]):
        if email_admin:
            admin = self.db.query(Admin).filter_by(email_admin=email_admin).first()
            if admin:
                wo.id_admin = admin.id_admin

    def muat_daftar_tiket(self):
        return self.db.query(WorkOrder).order_by(WorkOrder.risk_score.desc()).all()

    def lihat_detail_tiket(self, id_work_order: str):
        wo = self._wo(id_work_order)
        if not wo:
            return None

        laporan = self.db.query(Laporan).filter_by(id_work_order=id_work_order).first()
        wilayah = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
        penilik_list = self.db.query(PenilikJalan).filter_by(id_wilayah=wo.id_wilayah).all()

        is_ambiguous = (4.0 <= wo.risk_score <= 6.0) or (wo.prioritas == "Borderline")
        bisa_diputuskan = wo.status_work_order in SIAP_VERIFIKASI
        opsi_verifikasi = "Butuh Verifikasi Lapangan" if is_ambiguous else "Siap Disetujui"

        return {
            "wo": wo,
            "laporan": laporan,
            "nama_wilayah": wilayah.nama_wilayah if wilayah else "Kota Surabaya",
            "daftar_penilik": [p.nama_penilik for p in penilik_list],
            "opsi_penilik": [(p.id_penilik, label_penilik(p)) for p in penilik_list if p.is_active],
            "is_ambiguous": is_ambiguous,
            "opsi_verifikasi": opsi_verifikasi,
            "risk_score_label": f"{wo.risk_score} ({wo.prioritas})",
            "bisa_diputuskan": bisa_diputuskan,
        }

    def setujui_tiket(self, id_work_order: str, email_admin: Optional[str] = None):
        wo, siap = self._wo_siap(id_work_order)
        if siap:
            ubah_status(self.db, wo, DISETUJUI, "Disetujui oleh Admin", email_admin)
            self._catat_admin(wo, email_admin)
            self.db.commit()
        return wo

    def tugaskan_inspeksi_tambahan(self, id_work_order: str, nama_penilik: str, email_admin: Optional[str] = None):
        wo, siap = self._wo_siap(id_work_order)
        if not siap:
            return wo
        # Only an inspector from the ticket's own region can be assigned.
        penilik = cari_penilik(self.db, nama_penilik, wo.id_wilayah)
        if penilik:
            wo.id_penilik = penilik.id_penilik
            ubah_status(self.db, wo, MENUNGGU_INSPEKSI, f"Inspeksi tambahan oleh {penilik.nama_penilik}", email_admin)
            self._catat_admin(wo, email_admin)
            self.db.commit()
        return wo

    def lanjutkan_tanpa_inspeksi(self, id_work_order: str, email_admin: str = "admin@dpupr.surabaya.go.id"):
        wo, siap = self._wo_siap(id_work_order)
        if siap:
            wo.log_keputusan = f"Log Keputusan Manual - {email_admin}"
            ubah_status(self.db, wo, DISETUJUI, "Disetujui tanpa inspeksi tambahan", email_admin)
            self._catat_admin(wo, email_admin)
            self.db.commit()
        return wo
