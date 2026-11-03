from datetime import date
from sqlalchemy.orm import Session
from app.models.entities import Inspeksi, Perbaikan, WorkOrder, PenilikJalan, Wilayah
from app.services.alur_status import (
    BOLEH_MENUNGGU_PENUGASAN, DITUGASKAN, MENUNGGU_PENUGASAN, SIAP_PENUGASAN, ubah_status,
)


def cari_penilik(db: Session, pilihan: str, id_wilayah: str, hanya_tersedia: bool = False):
    """Resolve an inspector chosen in a form by ID (preferred, names can repeat) or by name."""
    if not pilihan:
        return None
    q = db.query(PenilikJalan).filter_by(id_wilayah=id_wilayah, is_active=True)
    if hanya_tersedia:
        q = q.filter_by(status_ketersediaan="Tersedia")
    return (q.filter(PenilikJalan.id_penilik == pilihan).first()
            or q.filter(PenilikJalan.nama_penilik == pilihan).order_by(PenilikJalan.id_penilik).first())


def label_penilik(p: PenilikJalan) -> str:
    return f"{p.nama_penilik} ({p.nip})" if p.nip else p.nama_penilik

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
            "daftar_penilik": [p.nama_penilik for p in penilik_tersedia],
            "opsi_penilik": [(p.id_penilik, label_penilik(p)) for p in penilik_tersedia],
            "boleh_ditugaskan": wo.status_work_order in SIAP_PENUGASAN,
            "wo": wo,
            "inspeksi": self.db.query(Inspeksi).filter_by(id_work_order=wo.id_work_order)
                            .order_by(Inspeksi.id_inspeksi.desc()).first(),
            "riwayat_perbaikan": self.db.query(Perbaikan).filter_by(id_work_order=wo.id_work_order)
                                     .order_by(Perbaikan.waktu.desc()).all(),
        }

    def tugaskan_penilik(self, id_work_order: str, nama_penilik: str = None):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if not wo:
            return None
        if wo.status_work_order not in SIAP_PENUGASAN:
            return wo  # not verified yet, or field work already started/finished
        ada_tersedia = self.db.query(PenilikJalan).filter_by(
            id_wilayah=wo.id_wilayah, status_ketersediaan="Tersedia", is_active=True,
        ).first()

        if not ada_tersedia:
            # Park only tickets nobody is working on; never move an assigned ticket backwards.
            if wo.status_work_order in BOLEH_MENUNGGU_PENUGASAN:
                ubah_status(self.db, wo, MENUNGGU_PENUGASAN, "Tidak ada Penilik Jalan tersedia di wilayah ini")
                self.db.commit()
            return wo

        penilik = cari_penilik(self.db, nama_penilik, wo.id_wilayah, hanya_tersedia=True)
        if not penilik:
            return wo
        sudah_ditugaskan = wo.status_work_order == DITUGASKAN
        if sudah_ditugaskan and penilik.id_penilik == wo.id_penilik:
            return wo  # same inspector again: nothing changes
        wo.id_penilik = penilik.id_penilik
        wo.tanggal_ditugaskan = date.today()
        # Changing the inspector keeps the status but is still recorded and notified.
        ubah_status(self.db, wo, DITUGASKAN, f"Ditugaskan kepada {penilik.nama_penilik}",
                    catat_walau_sama=sudah_ditugaskan)
        self.db.commit()
        return wo