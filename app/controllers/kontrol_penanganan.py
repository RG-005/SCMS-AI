"""UC-F: Admin menerbitkan SPK; petugas memperbarui progres sampai Selesai."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Perbaikan, WorkOrder
from app.services.ai_service import validasi_foto
from app.services.alur_status import DALAM_PROSES, SELESAI, TERINSPEKSI, ubah_status
from app.services.penyimpanan import dengan_coba_ulang, id_berurutan, tulis_dengan_foto

PESAN_FOTO_WAJIB = "Foto bukti penyelesaian perbaikan wajib diunggah untuk menutup laporan"
PESAN_OK = "Status perbaikan berhasil diperbarui"
PESAN_SPK_OK = "SPK berhasil diterbitkan, status tiket menjadi Dalam Proses"
PESAN_SPK_TIDAK_LENGKAP = "Nomor SPK dan tim pelaksana wajib diisi"
PESAN_SPK_DUPLIKAT = "Nomor SPK sudah dipakai tiket lain"
PESAN_BELUM_INSPEKSI = "SPK hanya dapat diterbitkan untuk tiket berstatus Terinspeksi"
PESAN_BUKAN_PROSES = "Progres hanya dapat diperbarui untuk tiket berstatus Dalam Proses"
PESAN_CATATAN_WAJIB = "Isi catatan progres pengerjaan"
PESAN_STATUS_TIDAK_VALID = "Pilih status progres yang valid"

STATUS_PROGRES = (DALAM_PROSES, SELESAI)


class KontrolPenanganan:
    def __init__(self, db: Session):
        self.db = db

    def terbitkan_spk(self, id_work_order: str, nomor_spk: str, tim_pelaksana: str,
                      status_awal: str = DALAM_PROSES, aktor: Optional[str] = None) -> dict:
        wo = self.db.get(WorkOrder, id_work_order)
        if not wo:
            return {"success": False, "message": PESAN_BELUM_INSPEKSI}
        if wo.status_work_order != TERINSPEKSI:
            return {"success": False, "message": PESAN_BELUM_INSPEKSI}
        nomor_spk = (nomor_spk or "").strip()
        tim_pelaksana = (tim_pelaksana or "").strip()
        if not nomor_spk or not tim_pelaksana:
            return {"success": False, "message": PESAN_SPK_TIDAK_LENGKAP}
        if status_awal != DALAM_PROSES:
            return {"success": False, "message": PESAN_STATUS_TIDAK_VALID}
        def langkah():
            wo_ = self.db.get(WorkOrder, id_work_order)
            if wo_.status_work_order != TERINSPEKSI:
                return {"success": False, "message": PESAN_BELUM_INSPEKSI}
            if self.db.query(WorkOrder).filter(func.upper(WorkOrder.nomor_spk) == nomor_spk.upper()).first():
                return {"success": False, "message": PESAN_SPK_DUPLIKAT}
            wo_.nomor_spk = nomor_spk[:50]
            wo_.tim_pelaksana = tim_pelaksana[:100]
            self.db.add(Perbaikan(
                id_perbaikan=id_berurutan(self.db, Perbaikan.id_perbaikan, "PRB"),
                id_work_order=wo_.id_work_order,
                status_perbaikan=DALAM_PROSES,
                catatan=f"SPK {wo_.nomor_spk} diterbitkan untuk {wo_.tim_pelaksana}",
                dicatat_oleh=aktor,
            ))
            ubah_status(self.db, wo_, DALAM_PROSES, f"SPK {wo_.nomor_spk} - {wo_.tim_pelaksana}", aktor)
            self.db.commit()
            return {"success": True, "message": PESAN_SPK_OK}

        return dengan_coba_ulang(self.db, langkah)

    def perbarui_progres(self, id_work_order: str, status_baru: str, catatan: str,
                         nama_foto: str = "", foto_bytes: Optional[bytes] = None,
                         aktor: Optional[str] = None) -> dict:
        wo = self.db.get(WorkOrder, id_work_order)
        if not wo or wo.status_work_order != DALAM_PROSES:
            return {"success": False, "message": PESAN_BUKAN_PROSES}
        if status_baru not in STATUS_PROGRES:
            return {"success": False, "message": PESAN_STATUS_TIDAK_VALID}
        catatan = (catatan or "").strip()

        format_gambar = ""
        if foto_bytes:
            val = validasi_foto(nama_foto, 0, foto_bytes)
            if not val.valid:
                return {"success": False, "message": val.message}
            format_gambar = val.format_gambar
        if status_baru == SELESAI and not foto_bytes:
            return {"success": False, "message": PESAN_FOTO_WAJIB}
        if status_baru == DALAM_PROSES and not catatan:
            return {"success": False, "message": PESAN_CATATAN_WAJIB}

        def langkah(url_foto):
            wo_ = self.db.get(WorkOrder, id_work_order)
            if wo_.status_work_order != DALAM_PROSES:
                return {"success": False, "message": PESAN_BUKAN_PROSES}
            sekarang = datetime.now(timezone.utc)
            self.db.add(Perbaikan(
                id_perbaikan=id_berurutan(self.db, Perbaikan.id_perbaikan, "PRB"),
                id_work_order=wo_.id_work_order,
                status_perbaikan=status_baru,
                catatan=catatan or None,
                foto_sesudah=url_foto,
                tanggal_selesai=sekarang if status_baru == SELESAI else None,
                dicatat_oleh=aktor,
            ))
            if status_baru == SELESAI:
                wo_.tanggal_selesai = sekarang
            ubah_status(self.db, wo_, status_baru, catatan, aktor, catat_walau_sama=True)
            self.db.commit()
            return {"success": True, "message": PESAN_OK}

        return tulis_dengan_foto(self.db, foto_bytes, format_gambar, langkah)
