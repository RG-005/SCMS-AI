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
        wilayah_map = {w.id_wilayah: w.nama_wilayah for w in self.db.query(Wilayah).all()}

        hasil_tiket = []
        for wo in wo_list:
            # Tickets without stored coordinates are listed but get no map marker (lat/lng None).
            lat, lng = wo.latitude, wo.longitude

            if wo.risk_score >= 8.0:
                warna = "#DC2626" # Merah (Darurat / Urgent)
            elif wo.risk_score >= 6.0:
                warna = "#EA580C" # Oranye (Tinggi)
            else:
                warna = "#D97706" # Kuning (Sedang / Borderline)

            hasil_tiket.append({
                "wo": wo,
                "nama_wilayah": wilayah_map.get(wo.id_wilayah, "Kota Surabaya"),
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
