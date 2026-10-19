from sqlalchemy.orm import Session
from app.models.entities import WorkOrder, Wilayah

class KontrolDashboard:
    def __init__(self, db: Session):
        self.db = db

    def muat_dashboard(self):
        wo_list = self.db.query(WorkOrder).order_by(WorkOrder.risk_score.desc()).all()
        return self._format_hasil(wo_list)

    def filter_dashboard(self, wilayah: str = None, status: str = None, kategori: str = None):
        query = self.db.query(WorkOrder)

        if wilayah and wilayah != "Semua":
            wil_obj = self.db.query(Wilayah).filter(
                (Wilayah.nama_wilayah.ilike(f"%{wilayah}%")) | (Wilayah.id_wilayah == wilayah)
            ).first()
            if wil_obj:
                query = query.filter(WorkOrder.id_wilayah == wil_obj.id_wilayah)
            else:
                return {
                    "daftar_tiket": [],
                    "top_ticket_label": None,
                    "message": "Tidak ada laporan sesuai filter"
                }

        if status and status != "Semua":
            query = query.filter(WorkOrder.status_work_order == status)

        if kategori and kategori != "Semua":
            query = query.filter(WorkOrder.kategori_kerusakan.ilike(f"%{kategori}%"))

        wo_list = query.order_by(WorkOrder.risk_score.desc()).all()
        if not wo_list:
            return {
                "daftar_tiket": [],
                "top_ticket_label": None,
                "message": "Tidak ada laporan sesuai filter"
            }

        return self._format_hasil(wo_list)

    def _format_hasil(self, wo_list):
        koordinat_default = {
            "REP-2026-00341": (-7.2655, 112.7470), # Jl. Sudirman / Gubeng
            "REP-2026-00298": (-7.2680, 112.7455),
            "REP-2026-00360": (-7.2245, 112.6320), # Wilayah Benowo
            "REP-2026-00355": (-7.2735, 112.7520), # Jl. Raya Gubeng
        }

        hasil_tiket = []
        for wo in wo_list:
            wilayah_obj = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
            lat, lng = koordinat_default.get(wo.id_work_order, (-7.2575, 112.7521))
            
            if wo.risk_score >= 8.0:
                warna = "#DC2626" # Merah (Darurat / Urgent)
            elif wo.risk_score >= 6.0:
                warna = "#EA580C" # Oranye (Tinggi)
            else:
                warna = "#D97706" # Kuning (Sedang / Borderline)

            hasil_tiket.append({
                "wo": wo,
                "nama_wilayah": wilayah_obj.nama_wilayah if wilayah_obj else "Kota Surabaya",
                "label_skor": f"{wo.id_work_order} ({wo.risk_score})",
                "lat": lat,
                "lng": lng,
                "warna_marker": warna
            })

        top_label = hasil_tiket[0]["label_skor"] if hasil_tiket else None
        return {
            "has_color_gradation": True,
            "daftar_tiket": hasil_tiket,
            "top_ticket_label": top_label,
            "message": None
        }
