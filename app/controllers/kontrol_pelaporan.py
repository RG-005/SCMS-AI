import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Laporan, Wilayah, WorkOrder
from app.services import risk_scoring
from app.services.ai_service import KATEGORI_VALID, AIService, get_ai_service
from app.services.deduplikasi import cari_duplikat

DIREKTORI_UNGGAHAN = Path(__file__).resolve().parents[1] / "static" / "uploads"
POLA_ID_WORK_ORDER = r"REP-\d{4}-(\d+)"
POLA_ID_LAPORAN = r"LAP-(\d+)"


def _nomor_berikutnya(nilai: list[str], pola: str) -> int:
    angka = [int(m.group(1)) for v in nilai if (m := re.fullmatch(pola, v or ""))]
    return max(angka, default=0) + 1


class KontrolPelaporan:
    def __init__(self, db: Session, ai: Optional[AIService] = None):
        self.db = db
        self.ai = ai or get_ai_service()

    # ---- helpers kept for the BDD step definitions --------------------------
    def validasi_foto(self, filename: str, file_size_mb: float, data: Optional[bytes] = None):
        hasil = self.ai.validasi_foto(filename, file_size_mb, data)
        return {"valid": hasil.valid, "message": hasil.message}

    def analisis_ai_cv(self, filename: str, data: Optional[bytes] = None):
        h = self.ai.analisis_foto(filename, data)
        return {
            "detected": h.detected,
            "message": h.message,
            "rekomendasi_kategori": h.rekomendasi_kategori,
            "severity_score": h.severity_score,
            "confidence": h.confidence,
            "sumber": h.sumber,
        }

    # ---- ID generation -------------------------------------------------------
    def _id_work_order_baru(self) -> str:
        tahun = datetime.now(timezone.utc).year
        semua = [r[0] for r in self.db.query(WorkOrder.id_work_order).all()]
        nomor = _nomor_berikutnya(semua, POLA_ID_WORK_ORDER)
        return f"REP-{tahun}-{nomor:05d}"

    def _id_laporan_baru(self) -> str:
        semua = [r[0] for r in self.db.query(Laporan.id_laporan).all()]
        nomor = _nomor_berikutnya(semua, POLA_ID_LAPORAN)
        return f"LAP-{nomor:03d}"

    def _simpan_foto(self, data: Optional[bytes], ekstensi: str, nama_asli: str) -> str:
        if data is None:
            # No bytes (unit tests / scripts calling the controller directly):
            # keep a reference to the original name only.
            return f"static/uploads/{Path(nama_asli).name}"[:255]
        DIREKTORI_UNGGAHAN.mkdir(parents=True, exist_ok=True)
        ekstensi_simpan = {"jpeg": "jpg", "JPEG": "jpg", "PNG": "png"}.get(ekstensi, ekstensi.lower())
        nama = f"{uuid.uuid4().hex}.{ekstensi_simpan}"
        (DIREKTORI_UNGGAHAN / nama).write_bytes(data)
        return f"static/uploads/{nama}"

    # ---- main flow (UC-A) ----------------------------------------------------
    def kirim_laporan(
        self,
        filename: str,
        file_size_mb: float,
        lokasi_jalan: str,
        deskripsi: str,
        kategori_pilihan: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        id_warga: str = "USR-01",
        id_wilayah: str = "WIL-01",
        foto_bytes: Optional[bytes] = None,
    ):
        # Step 1: file format & size, checked against the real bytes when given (REQ-RPT-1)
        val = self.ai.validasi_foto(filename, file_size_mb, foto_bytes)
        if not val.valid:
            return {"success": False, "step": 1, "message": val.message}

        # Step 2: location (REQ-RPT-4)
        lokasi = (lokasi_jalan or "").strip()
        if not lokasi:
            return {"success": False, "step": 2, "message": "Lokasi kerusakan jalan wajib ditentukan"}
        if latitude is not None and longitude is not None:
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return {"success": False, "step": 2, "message": "Koordinat lokasi tidak valid"}
        if not self.db.get(Wilayah, id_wilayah):
            return {"success": False, "step": 2, "message": "Wilayah rayon tidak valid"}

        # Step 3: damage detection & description (REQ-RPT-2, 3, 5, 6)
        cv = self.ai.analisis_foto(filename, foto_bytes)
        if not cv.detected:
            return {"success": False, "step": 3, "message": cv.message}
        deskripsi = (deskripsi or "").strip()
        if len(deskripsi) < 10:
            return {"success": False, "step": 3, "message": "Deskripsi laporan minimal harus terdiri dari 10 karakter"}

        kategori = kategori_pilihan if kategori_pilihan in KATEGORI_VALID else cv.rekomendasi_kategori
        severity = cv.severity_score
        lokasi_simpan = lokasi[:100]
        lokasi_teks = lokasi[:100]
        status_laporan = "Diterima" if self.ai.is_simulasi else "Terverifikasi AI"

        # Step 4: spatial-semantic deduplication (REQ-RPT-7, REQ-RPT-8, PRD BR-3)
        duplikat = cari_duplikat(self.db, self.ai, kategori, lokasi, deskripsi, latitude, longitude)
        url_foto = self._simpan_foto(foto_bytes, val.format_gambar or val.ekstensi, filename)
        if duplikat:
            wo = duplikat.work_order
            # Exposure = number of DIFFERENT citizens reporting this damage; the same
            # citizen reporting again is recorded but does not raise the priority.
            sudah_melapor = self.db.query(Laporan).filter_by(id_work_order=wo.id_work_order, id_warga=id_warga).first()
            if not sudah_melapor:
                wo.exposure_count = (wo.exposure_count or 1) + 1
            wo.severity_score_kasus = max(wo.severity_score_kasus or 0.0, severity)
            risk_scoring.terapkan_ke_work_order(wo)
            self.db.add(Laporan(
                id_laporan=self._id_laporan_baru(),
                id_warga=id_warga,
                id_work_order=wo.id_work_order,
                id_wilayah=wo.id_wilayah,
                url_foto=url_foto,
                lokasi_teks=lokasi_teks,
                latitude=latitude,
                longitude=longitude,
                deskripsi=deskripsi,
                severity_score=severity,
                status="Digabungkan",
            ))
            self.db.commit()
            return self._hasil(True, wo, cv, kategori, severity, latitude, longitude,
                               f"Laporan Anda telah digabungkan dengan laporan serupa yang sudah aktif ({wo.id_work_order})")

        # New Work Order (REQ-RPT-9)
        for _ in range(5):  # retry if another request took the same ID
            try:
                wo = WorkOrder(
                    id_work_order=self._id_work_order_baru(),
                    id_wilayah=id_wilayah,
                    kategori_kerusakan=kategori,
                    lokasi_jalan=lokasi_simpan,
                    latitude=latitude,
                    longitude=longitude,
                    kelas_jalan=risk_scoring.KELAS_JALAN_DEFAULT,
                    severity_score_kasus=severity,
                    exposure_count=1,
                    vulnerability_score=risk_scoring.VULNERABILITY_DEFAULT,
                    status_work_order="Dilaporkan",
                )
                risk_scoring.terapkan_ke_work_order(wo)
                self.db.add(wo)
                self.db.flush()
                self.db.add(Laporan(
                    id_laporan=self._id_laporan_baru(),
                    id_warga=id_warga,
                    id_work_order=wo.id_work_order,
                    id_wilayah=id_wilayah,
                    url_foto=url_foto,
                    lokasi_teks=lokasi_teks,
                    latitude=latitude,
                    longitude=longitude,
                    deskripsi=deskripsi,
                    severity_score=severity,
                    status=status_laporan,
                ))
                self.db.commit()
                break
            except IntegrityError:
                self.db.rollback()
        else:
            return {"success": False, "step": 4, "message": "Gagal menerbitkan nomor tiket, silakan coba lagi"}

        return self._hasil(False, wo, cv, kategori, severity, latitude, longitude,
                           f"Laporan berhasil dikirim dengan nomor tiket {wo.id_work_order}")

    def _hasil(self, is_duplikat, wo, cv, kategori, severity, lat, lng, pesan):
        return {
            "success": True,
            "is_duplicate": is_duplikat,
            "ticket_id": wo.id_work_order,
            "status_work_order": wo.status_work_order,
            "exposure_count": wo.exposure_count,
            "risk_score": wo.risk_score,
            "prioritas": wo.prioritas,
            "rekomendasi_kategori": cv.rekomendasi_kategori,
            "kategori_final": kategori,
            "severity_score": severity,
            "confidence": cv.confidence,
            "mode_ai": cv.sumber,
            "koordinat": f"{lat:.5f}, {lng:.5f}" if lat is not None and lng is not None else "-",
            "message": pesan,
        }
