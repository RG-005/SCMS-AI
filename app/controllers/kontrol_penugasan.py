from datetime import date
from sqlalchemy.orm import Session
from app.models.entities import WorkOrder, PenilikJalan, Wilayah

class KontrolPenugasan:
    def __init__(self, db: Session):
        self.db = db

    def get_semua_work_order(self, filter_wilayah: str = None, filter_status: str = None):
        query = self.db.query(WorkOrder)
        if filter_wilayah and filter_wilayah != "Semua":
            query = query.filter(WorkOrder.id_wilayah == filter_wilayah)
        if filter_status and filter_status != "Semua":
            query = query.filter(WorkOrder.status_work_order == filter_status)
            
        wo_list = query.order_by(WorkOrder.risk_score.desc()).all()
        
        hasil = []
        for wo in wo_list:
            wilayah = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
            penilik = self.db.query(PenilikJalan).filter_by(id_penilik=wo.id_penilik).first() if wo.id_penilik else None
            penilik_tersedia = self.db.query(PenilikJalan).filter_by(
                id_wilayah=wo.id_wilayah,
                status_ketersediaan="Tersedia"
            ).all()
            
            hasil.append({
                "wo": wo,
                "nama_wilayah": wilayah.nama_wilayah if wilayah else "-",
                "nama_penilik": penilik.nama_penilik if penilik else "Belum Ditugaskan",
                "penilik_tersedia": [p.nama_penilik for p in penilik_tersedia]
            })
        return hasil

    def cek_sla_dan_ketersediaan_penilik(self, id_work_order: str):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if not wo:
            return None

        wilayah = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
        penilik_tersedia = self.db.query(PenilikJalan).filter_by(
            id_wilayah=wo.id_wilayah,
            status_ketersediaan="Tersedia"
        ).all()

        return {
            "id_work_order": wo.id_work_order,
            "kategori_kerusakan": wo.kategori_kerusakan,
            "lokasi_jalan": wo.lokasi_jalan,
            "prioritas": wo.prioritas,
            "risk_score": wo.risk_score,
            "status_work_order": wo.status_work_order,
            "sla_rekomendasi": wo.sla_rekomendasi,
            "nama_wilayah": wilayah.nama_wilayah if wilayah else "",
            "daftar_penilik": [p.nama_penilik for p in penilik_tersedia]
        }

    def tugaskan_penilik(self, id_work_order: str, nama_penilik: str = None):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if not wo:
            return None
        penilik_tersedia = self.db.query(PenilikJalan).filter_by(
            id_wilayah=wo.id_wilayah,
            status_ketersediaan="Tersedia"
        ).all()

        if not penilik_tersedia:
            wo.status_work_order = "Menunggu Penugasan"
            self.db.commit()
            return wo

        penilik = next((p for p in penilik_tersedia if p.nama_penilik == nama_penilik), None)
        if penilik:
            wo.id_penilik = penilik.id_penilik
            wo.status_work_order = "Ditugaskan"
            wo.tanggal_ditugaskan = date.today()
            self.db.commit()

        return wo