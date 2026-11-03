"""UC-E: Penilik Jalan mencatat hasil inspeksi lapangan."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Inspeksi, Laporan, PenilikJalan, Perbaikan, Wilayah, WorkOrder
from app.services.ai_service import validasi_foto
from app.services.alur_status import DALAM_PROSES, SIAP_INSPEKSI, TERINSPEKSI, ubah_status
from app.services.penyimpanan import id_berurutan, tulis_dengan_foto

PESAN_TIDAK_LENGKAP = "Lengkapi dimensi kerusakan dan rekomendasi teknis penanganan"
PESAN_OK = "Hasil inspeksi berhasil disimpan"
PESAN_STATUS_SALAH = "Tiket ini tidak sedang menunggu inspeksi lapangan"
PESAN_BUKAN_TUGAS = "Tiket ini bukan tugas Anda"
PESAN_TANPA_LAPORAN = "Tiket ini belum memiliki laporan warga yang dapat diinspeksi"

REKOMENDASI_PENANGANAN = (
    "Tambal Hotmix",
    "Tambal Sulam Dingin (Cold Mix)",
    "Pelapisan Ulang (Overlay)",
    "Rekonstruksi Perkerasan",
    "Perbaikan Drainase",
)


class KontrolInspeksi:
    def __init__(self, db: Session):
        self.db = db

    def _penilik(self, id_penilik: str) -> Optional[PenilikJalan]:
        return self.db.get(PenilikJalan, id_penilik)

    @staticmethod
    def boleh_akses(wo: WorkOrder, penilik: PenilikJalan) -> bool:
        """An inspector works on tickets in their own region that are assigned to them or to nobody."""
        return bool(wo and penilik and wo.id_wilayah == penilik.id_wilayah
                    and wo.id_penilik in (None, penilik.id_penilik))

    def daftar_tugas(self, id_penilik: str) -> dict:
        penilik = self._penilik(id_penilik)
        if not penilik:
            return {"inspeksi": [], "perbaikan": [], "nama_wilayah": "-"}
        semua = (self.db.query(WorkOrder).filter_by(id_wilayah=penilik.id_wilayah)
                 .order_by(WorkOrder.risk_score.desc()).all())
        wilayah = self.db.get(Wilayah, penilik.id_wilayah)
        return {
            "inspeksi": [w for w in semua if w.status_work_order in SIAP_INSPEKSI and self.boleh_akses(w, penilik)],
            "perbaikan": [w for w in semua if w.status_work_order == DALAM_PROSES and self.boleh_akses(w, penilik)],
            "nama_wilayah": wilayah.nama_wilayah if wilayah else "-",
        }

    def detail(self, id_work_order: str, id_penilik: str) -> Optional[dict]:
        wo = self.db.get(WorkOrder, id_work_order)
        penilik = self._penilik(id_penilik)
        if not wo or not self.boleh_akses(wo, penilik):
            return None
        laporan = (self.db.query(Laporan).filter_by(id_work_order=wo.id_work_order)
                   .order_by(Laporan.tanggal_lapor).all())
        return {
            "wo": wo,
            "laporan": laporan,
            "inspeksi": (self.db.query(Inspeksi).filter_by(id_work_order=wo.id_work_order)
                         .order_by(Inspeksi.id_inspeksi.desc()).first()),
            "riwayat_perbaikan": (self.db.query(Perbaikan).filter_by(id_work_order=wo.id_work_order)
                                  .order_by(Perbaikan.waktu.desc()).all()),
            "bisa_inspeksi": wo.status_work_order in SIAP_INSPEKSI,
            "bisa_update_perbaikan": wo.status_work_order == DALAM_PROSES,
            "rekomendasi": REKOMENDASI_PENANGANAN,
        }

    def simpan_inspeksi(
        self,
        id_work_order: str,
        id_penilik: str,
        dimensi: str,
        catatan: str,
        rekomendasi: str,
        nama_foto: str = "",
        foto_bytes: Optional[bytes] = None,
    ) -> dict:
        wo = self.db.get(WorkOrder, id_work_order)
        penilik = self._penilik(id_penilik)
        if not wo or not self.boleh_akses(wo, penilik):
            return {"success": False, "message": PESAN_BUKAN_TUGAS}
        if wo.status_work_order not in SIAP_INSPEKSI:
            return {"success": False, "message": PESAN_STATUS_SALAH}
        dimensi = (dimensi or "").strip()
        rekomendasi = (rekomendasi or "").strip()
        if not dimensi or rekomendasi not in REKOMENDASI_PENANGANAN:
            return {"success": False, "message": PESAN_TIDAK_LENGKAP}

        format_gambar = ""
        if foto_bytes:
            val = validasi_foto(nama_foto, 0, foto_bytes)
            if not val.valid:
                return {"success": False, "message": val.message}
            format_gambar = val.format_gambar
        if not self.db.query(Laporan).filter_by(id_work_order=wo.id_work_order).first():
            return {"success": False, "message": PESAN_TANPA_LAPORAN}
        catatan = (catatan or "").strip()
        id_penilik_ = penilik.id_penilik

        def langkah(url_foto):
            wo_ = self.db.get(WorkOrder, id_work_order)
            penilik_ = self._penilik(id_penilik_)
            if wo_.status_work_order not in SIAP_INSPEKSI:
                return {"success": False, "message": PESAN_STATUS_SALAH}
            laporan_pertama = (self.db.query(Laporan).filter_by(id_work_order=wo_.id_work_order)
                               .order_by(Laporan.tanggal_lapor).first())
            self.db.add(Inspeksi(
                id_inspeksi=id_berurutan(self.db, Inspeksi.id_inspeksi, "INS"),
                id_laporan=laporan_pertama.id_laporan,
                id_penilik=penilik_.id_penilik,
                id_work_order=wo_.id_work_order,
                dimensi_kerusakan=dimensi[:50],
                rekomendasi_penanganan=rekomendasi,
                hasil_temuan=catatan or "-",
                url_foto_temuan=url_foto,
            ))
            wo_.id_penilik = penilik_.id_penilik
            ubah_status(self.db, wo_, TERINSPEKSI,
                        f"Dimensi {dimensi}; rekomendasi {rekomendasi}", penilik_.nama_penilik)
            self.db.commit()
            return {"success": True, "message": PESAN_OK}

        return tulis_dengan_foto(self.db, foto_bytes, format_gambar, langkah)
