"""UC-L: rekap kinerja penanganan infrastruktur (Kepala Bidang / Admin).

Builds the performance recap shown on /laporan-kinerja and exported as CSV:
handling performance, SLA compliance and risk statistics per rayon region.

SLA clock: a ticket's clock starts when it is first recorded (its first entry in
`riwayat_status`, i.e. "Laporan warga diterima sistem"; for old data without
history, the earliest citizen report). It stops at `tanggal_selesai`. The SLA
length is the ticket's `sla_rekomendasi` (24 jam, 48 jam, 3x24 jam, 7x24 jam).
"""
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Laporan, Rating, RiwayatStatus, Wilayah, WorkOrder
from app.services.alur_status import SELESAI

WIB = timezone(timedelta(hours=7))

TEPAT_WAKTU = "Tepat Waktu"
TERLAMBAT = "Terlambat"
DALAM_SLA = "Dalam SLA"
MELEWATI_SLA = "Melewati SLA"
TIDAK_DIKETAHUI = "Tidak Diketahui"

PESAN_KOSONG = "Tidak ada data kinerja pada periode yang dipilih"
PESAN_TANGGAL_TIDAK_VALID = "Format tanggal tidak valid (gunakan YYYY-MM-DD)"
PESAN_RENTANG_TERBALIK = "Tanggal mulai tidak boleh setelah tanggal akhir"

URUTAN_PRIORITAS = ("Urgent", "Tinggi", "Borderline", "Rendah")


def jam_sla(sla_rekomendasi: Optional[str]) -> Optional[int]:
    """'24 jam' -> 24, '3x24 jam' -> 72, '7x24 jam' -> 168. None if it cannot be read."""
    if not sla_rekomendasi:
        return None
    teks = sla_rekomendasi.lower().replace(" ", "").replace("×", "x")
    m = re.match(r"^(?:(\d+)x)?(\d+)jam$", teks)
    if not m:
        return None
    return int(m.group(1) or 1) * int(m.group(2))


def _utc(waktu: Optional[datetime]) -> Optional[datetime]:
    """Stored timestamps are UTC; SQLite returns them without tzinfo."""
    if waktu is None:
        return None
    return waktu.replace(tzinfo=timezone.utc) if waktu.tzinfo is None else waktu.astimezone(timezone.utc)


def _format_wib(waktu: Optional[datetime]) -> str:
    return waktu.astimezone(WIB).strftime("%d-%m-%Y %H:%M") if waktu else ""


def baca_tanggal(teks: Optional[str]) -> Optional[date]:
    """'' / None -> None; raises ValueError on a malformed date."""
    teks = (teks or "").strip()
    return date.fromisoformat(teks) if teks else None


def _persen(bagian: int, total: int) -> Optional[float]:
    return round(bagian / total * 100, 1) if total else None


def _rata(nilai: list) -> Optional[float]:
    return round(sum(nilai) / len(nilai), 1) if nilai else None


def aman_untuk_spreadsheet(nilai):
    """Stop CSV formula injection: text typed by citizens (e.g. a street name
    starting with '=') must not run as a formula when the file is opened in Excel."""
    if isinstance(nilai, str) and nilai[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + nilai
    return nilai


class KontrolLaporanKinerja:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ data
    def _waktu_mulai(self) -> dict:
        """id_work_order -> UTC time the ticket was first recorded."""
        mulai = {
            id_wo: _utc(waktu)
            for id_wo, waktu in self.db.query(RiwayatStatus.id_work_order, func.min(RiwayatStatus.waktu))
            .group_by(RiwayatStatus.id_work_order).all()
        }
        for id_wo, waktu in (self.db.query(Laporan.id_work_order, func.min(Laporan.tanggal_lapor))
                             .filter(Laporan.id_work_order.isnot(None))
                             .group_by(Laporan.id_work_order).all()):
            if id_wo not in mulai or mulai[id_wo] is None:
                mulai[id_wo] = _utc(waktu)
        return mulai

    def _rating_per_tiket(self) -> dict:
        """id_work_order -> list of star ratings given by its reporters."""
        hasil: dict = {}
        for id_wo, nilai in (self.db.query(Laporan.id_work_order, Rating.nilai_bintang)
                             .join(Rating, Rating.id_laporan == Laporan.id_laporan).all()):
            hasil.setdefault(id_wo, []).append(nilai)
        return hasil

    def _baris_tiket(self, wo: WorkOrder, mulai: Optional[datetime], nama_wilayah: str,
                     rating: list, sekarang: datetime) -> dict:
        batas_jam = jam_sla(wo.sla_rekomendasi)
        selesai = wo.status_work_order == SELESAI
        waktu_selesai = _utc(wo.tanggal_selesai) if selesai else None
        akhir = waktu_selesai if selesai else sekarang
        durasi_jam = round((akhir - mulai).total_seconds() / 3600, 1) if (mulai and akhir) else None

        if durasi_jam is None or batas_jam is None:
            status_sla = TIDAK_DIKETAHUI
        elif selesai:
            status_sla = TEPAT_WAKTU if durasi_jam <= batas_jam else TERLAMBAT
        else:
            status_sla = DALAM_SLA if durasi_jam <= batas_jam else MELEWATI_SLA

        return {
            "id_work_order": wo.id_work_order,
            "id_wilayah": wo.id_wilayah,
            "nama_wilayah": nama_wilayah,
            "kategori": wo.kategori_kerusakan,
            "lokasi": wo.lokasi_jalan or "",
            "prioritas": wo.prioritas,
            "risk_score": wo.risk_score or 0.0,
            "exposure": wo.exposure_count or 1,
            "status": wo.status_work_order,
            "sla": wo.sla_rekomendasi,
            "jam_sla": batas_jam,
            "mulai": mulai,
            "selesai": waktu_selesai,
            "mulai_wib": _format_wib(mulai),
            "selesai_wib": _format_wib(waktu_selesai),
            "durasi_jam": durasi_jam,
            "status_sla": status_sla,
            "rating": rating,
        }

    @staticmethod
    def _ringkas(baris: list) -> dict:
        selesai = [b for b in baris if b["status"] == SELESAI]
        aktif = [b for b in baris if b["status"] != SELESAI]
        tepat = sum(1 for b in selesai if b["status_sla"] == TEPAT_WAKTU)
        terlambat = sum(1 for b in selesai if b["status_sla"] == TERLAMBAT)
        lewat = sum(1 for b in aktif if b["status_sla"] == MELEWATI_SLA)
        durasi_selesai = [b["durasi_jam"] for b in selesai if b["durasi_jam"] is not None]
        skor = [b["risk_score"] for b in baris]
        rating = [r for b in baris for r in b["rating"]]
        return {
            "total": len(baris),
            "selesai": len(selesai),
            "aktif": len(aktif),
            "tingkat_penyelesaian": _persen(len(selesai), len(baris)),
            "tepat_waktu": tepat,
            "terlambat": terlambat,
            "aktif_lewat_sla": lewat,
            # compliance = closed on time / closed with a known duration
            "kepatuhan_sla": _persen(tepat, tepat + terlambat),
            "rata_durasi_jam": _rata(durasi_selesai),
            "rata_risk": _rata(skor),
            "risk_tertinggi": max(skor) if skor else None,
            "jumlah_urgent": sum(1 for b in baris if b["prioritas"] == "Urgent"),
            "rata_rating": _rata(rating),
            "jumlah_rating": len(rating),
        }

    # ------------------------------------------------------------- public API
    def rekap(self, tanggal_mulai: Optional[str] = None, tanggal_akhir: Optional[str] = None,
              wilayah: str = "Semua", sekarang: Optional[datetime] = None) -> dict:
        """Performance recap for tickets first recorded between the two dates (WIB, inclusive)."""
        sekarang = _utc(sekarang) or datetime.now(timezone.utc)
        daftar_wilayah = self.db.query(Wilayah).order_by(Wilayah.id_wilayah).all()
        filter_ = {"tanggal_mulai": (tanggal_mulai or "").strip(), "tanggal_akhir": (tanggal_akhir or "").strip(),
                   "wilayah": wilayah or "Semua"}
        hasil = {"success": True, "message": None, "filter": filter_, "daftar_wilayah": daftar_wilayah,
                 "tiket": [], "per_wilayah": [], "per_prioritas": [], "total": self._ringkas([]),
                 "dibuat_pada": _format_wib(sekarang)}

        try:
            dari, sampai = baca_tanggal(tanggal_mulai), baca_tanggal(tanggal_akhir)
        except ValueError:
            return {**hasil, "success": False, "message": PESAN_TANGGAL_TIDAK_VALID}
        if dari and sampai and dari > sampai:
            return {**hasil, "success": False, "message": PESAN_RENTANG_TERBALIK}

        nama_wilayah = {w.id_wilayah: w.nama_wilayah for w in daftar_wilayah}
        query = self.db.query(WorkOrder)
        if filter_["wilayah"] != "Semua":
            query = query.filter(WorkOrder.id_wilayah == filter_["wilayah"])
        mulai_per_tiket = self._waktu_mulai()
        rating_per_tiket = self._rating_per_tiket()

        baris = []
        for wo in query.all():
            mulai = mulai_per_tiket.get(wo.id_work_order)
            tanggal_wib = mulai.astimezone(WIB).date() if mulai else None
            if (dari or sampai) and tanggal_wib is None:
                continue  # unknown start date cannot be placed in a period
            if dari and tanggal_wib < dari:
                continue
            if sampai and tanggal_wib > sampai:
                continue
            baris.append(self._baris_tiket(wo, mulai, nama_wilayah.get(wo.id_wilayah, "Tanpa Wilayah"),
                                           rating_per_tiket.get(wo.id_work_order, []), sekarang))
        baris.sort(key=lambda b: (-b["risk_score"], b["id_work_order"]))

        if not baris:
            return {**hasil, "message": PESAN_KOSONG}

        per_wilayah = []
        for w in daftar_wilayah:
            if filter_["wilayah"] != "Semua" and w.id_wilayah != filter_["wilayah"]:
                continue
            isi = [b for b in baris if b["id_wilayah"] == w.id_wilayah]
            per_wilayah.append({"id_wilayah": w.id_wilayah, "nama_wilayah": w.nama_wilayah, **self._ringkas(isi)})
        tanpa_wilayah = [b for b in baris if b["id_wilayah"] not in nama_wilayah]
        if tanpa_wilayah:
            per_wilayah.append({"id_wilayah": None, "nama_wilayah": "Tanpa Wilayah", **self._ringkas(tanpa_wilayah)})

        per_prioritas = [{"prioritas": p, **self._ringkas([b for b in baris if b["prioritas"] == p])}
                         for p in URUTAN_PRIORITAS]

        return {**hasil, "tiket": baris, "per_wilayah": per_wilayah, "per_prioritas": per_prioritas,
                "total": self._ringkas(baris)}

    # ------------------------------------------------------------------- CSV
    @staticmethod
    def _csv(header: list, rows: Iterable[list]) -> str:
        buf = io.StringIO()
        tulis = csv.writer(buf)
        tulis.writerow(header)
        for row in rows:
            tulis.writerow(["" if v is None else aman_untuk_spreadsheet(v) for v in row])
        # BOM so Excel opens the UTF-8 file with the right encoding
        return "﻿" + buf.getvalue()

    def csv_per_wilayah(self, data: dict) -> str:
        header = ["Wilayah", "Total Tiket", "Selesai", "Aktif", "Tingkat Penyelesaian (%)",
                  "Selesai Tepat Waktu", "Selesai Terlambat", "Aktif Melewati SLA", "Kepatuhan SLA (%)",
                  "Rata-rata Waktu Penyelesaian (jam)", "Rata-rata Risk Score", "Risk Score Tertinggi",
                  "Tiket Urgent", "Rata-rata Rating", "Jumlah Rating"]
        baris = [r for r in data["per_wilayah"]] + [{"nama_wilayah": "TOTAL", **data["total"]}]
        return self._csv(header, (
            [r["nama_wilayah"], r["total"], r["selesai"], r["aktif"], r["tingkat_penyelesaian"],
             r["tepat_waktu"], r["terlambat"], r["aktif_lewat_sla"], r["kepatuhan_sla"],
             r["rata_durasi_jam"], r["rata_risk"], r["risk_tertinggi"], r["jumlah_urgent"],
             r["rata_rating"], r["jumlah_rating"]]
            for r in baris
        ))

    def csv_per_tiket(self, data: dict) -> str:
        header = ["ID Tiket", "Wilayah", "Kategori", "Lokasi", "Prioritas", "Risk Score", "Jumlah Pelapor",
                  "Status", "SLA", "Dilaporkan (WIB)", "Selesai (WIB)", "Durasi (jam)", "Status SLA",
                  "Rata-rata Rating"]
        return self._csv(header, (
            [b["id_work_order"], b["nama_wilayah"], b["kategori"], b["lokasi"], b["prioritas"], b["risk_score"],
             b["exposure"], b["status"], b["sla"], b["mulai_wib"], b["selesai_wib"], b["durasi_jam"],
             b["status_sla"], _rata(b["rating"])]
            for b in data["tiket"]
        ))
