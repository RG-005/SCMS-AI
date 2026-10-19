from sqlalchemy.orm import Session
from app.models.entities import WorkOrder, Laporan, PenilikJalan, Wilayah

class KontrolVerifikasi:
    def __init__(self, db: Session):
        self.db = db

    def muat_daftar_tiket(self):
        return self.db.query(WorkOrder).order_by(WorkOrder.risk_score.desc()).all()

    def lihat_detail_tiket(self, id_work_order: str):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if not wo:
            return None

        laporan = self.db.query(Laporan).filter_by(id_work_order=id_work_order).first()
        wilayah = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
        penilik_list = self.db.query(PenilikJalan).filter_by(id_wilayah=wo.id_wilayah).all()

        is_ambiguous = (4.0 <= wo.risk_score <= 6.0) or (wo.prioritas == "Borderline")
        opsi_verifikasi = "Butuh Verifikasi Lapangan" if is_ambiguous else "Siap Disetujui"

        return {
            "wo": wo,
            "laporan": laporan,
            "nama_wilayah": wilayah.nama_wilayah if wilayah else "Kota Surabaya",
            "daftar_penilik": [p.nama_penilik for p in penilik_list],
            "is_ambiguous": is_ambiguous,
            "opsi_verifikasi": opsi_verifikasi,
            "risk_score_label": f"{wo.risk_score} ({wo.prioritas})"
        }

    def setujui_tiket(self, id_work_order: str):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if wo:
            wo.status_work_order = "Disetujui"
            self.db.commit()
        return wo

    def tugaskan_inspeksi_tambahan(self, id_work_order: str, nama_penilik: str):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        penilik = self.db.query(PenilikJalan).filter_by(nama_penilik=nama_penilik).first()
        if wo and penilik:
            wo.id_penilik = penilik.id_penilik
            wo.status_work_order = "Menunggu Inspeksi"
            self.db.commit()
        return wo

    def lanjutkan_tanpa_inspeksi(self, id_work_order: str, email_admin: str = "admin@dpupr.surabaya.go.id"):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if wo:
            wo.log_keputusan = f"Log Keputusan Manual - {email_admin}"
            wo.status_work_order = "Disetujui"
            self.db.commit()
        return wo
