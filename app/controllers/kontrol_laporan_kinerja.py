"""UC-L: rekap kinerja penanganan infrastruktur (Kepala Bidang / Admin).

Builds the performance recap shown on /laporan-kinerja and exported as CSV:
handling performance, time spent per handling stage, age of active tickets and
risk statistics per rayon region and per priority.

There is no completion-time target (SLA). It was removed after the teaching
assistant's review: road repairs go through procurement and bureaucracy, so
fixed targets (24 jam ... 7x24 jam) are not realistic. Urgency is shown by the
BR-2 priority level only; this report measures how long each stage actually took.

Ticket start: the ticket's first entry in `riwayat_status` ("Laporan warga
diterima sistem"); for old data without history, the earliest citizen report.

Stage durations come from `riwayat_status`, using the FIRST time each status
was reached. A stage is counted for a ticket only when the ticket reached both
its start and its end status (and the end is not before the start), so a stage
the ticket skipped or has not finished yet is left out for that ticket. Example:
the additional-inspection path (Dilaporkan -> Menunggu Inspeksi -> Terinspeksi)
never reaches `Ditugaskan`, so "Penugasan" and "Inspeksi Lapangan" are not
counted for it; its other stages are.

Ratings: one rating per citizen per ticket (UC-J). If old data holds several ratings from
the same citizen for one ticket (two merged reports), only their first rating is counted.
"""
import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.controllers.kontrol_dashboard import warna_prioritas
from app.models.entities import Laporan, Rating, RiwayatStatus, Wilayah, WorkOrder
from app.services.alur_status import (
    ALASAN_TUTUP, DALAM_PROSES, DILAPORKAN, DISETUJUI, DITUGASKAN, DITUTUP, MENUNGGU_INSPEKSI, MENUNGGU_PENUGASAN,
    SELESAI, TERINSPEKSI,
)

WIB = timezone(timedelta(hours=7))
DETIK_PER_HARI = 86400

PESAN_KOSONG = "Tidak ada data kinerja pada periode yang dipilih"
PESAN_TANGGAL_TIDAK_VALID = "Format tanggal tidak valid (gunakan YYYY-MM-DD)"
PESAN_RENTANG_TERBALIK = "Tanggal mulai tidak boleh setelah tanggal akhir"

URUTAN_PRIORITAS = ("Urgent", "Tinggi", "Borderline", "Rendah")

# Marker for "the moment the ticket was received" (first history entry).
MASUK = "__masuk__"

# (code, label, start statuses, end statuses). The first time any start status was
# reached is the start; the first time any end status was reached is the end.
TAHAP = (
    ("verifikasi", "Verifikasi", (MASUK,), (DISETUJUI, MENUNGGU_INSPEKSI)),
    ("penugasan", "Penugasan", (DISETUJUI, MENUNGGU_INSPEKSI), (DITUGASKAN,)),
    ("inspeksi", "Inspeksi Lapangan", (DITUGASKAN,), (TERINSPEKSI,)),
    ("spk", "Penerbitan SPK", (TERINSPEKSI,), (DALAM_PROSES,)),
    ("perbaikan", "Perbaikan", (DALAM_PROSES,), (SELESAI,)),
)
LABEL_TAHAP = {kode: label for kode, label, _, _ in TAHAP}

TAHAP_MENUNGGU_KUNJUNGAN = "Perbaikan (menunggu kunjungan lanjutan)"

# Stage an active ticket is currently in, by its status.
TAHAP_SAAT_INI = {
    DILAPORKAN: "Menunggu Verifikasi",
    DISETUJUI: "Menunggu Penugasan",
    MENUNGGU_PENUGASAN: "Menunggu Penugasan",
    MENUNGGU_INSPEKSI: "Inspeksi Tambahan",
    DITUGASKAN: "Inspeksi Lapangan",
    TERINSPEKSI: "Menunggu SPK",
    DALAM_PROSES: "Perbaikan",
}


def _utc(waktu: Optional[datetime]) -> Optional[datetime]:
    """Stored timestamps are UTC; SQLite returns them without tzinfo."""
    if waktu is None:
        return None
    return waktu.replace(tzinfo=timezone.utc) if waktu.tzinfo is None else waktu.astimezone(timezone.utc)


def _format_wib(waktu: Optional[datetime]) -> str:
    return waktu.astimezone(WIB).strftime("%d-%m-%Y %H:%M") if waktu else ""


def _hari(dari: Optional[datetime], sampai: Optional[datetime]) -> Optional[float]:
    """Exact (unrounded) number of days between two times; None if either is missing or reversed."""
    if dari is None or sampai is None or sampai < dari:
        return None
    return (sampai - dari).total_seconds() / DETIK_PER_HARI


def _bulat(nilai: Optional[float]) -> Optional[float]:
    return round(nilai, 1) if nilai is not None else None


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


def durasi_tahap(waktu_status: dict) -> dict:
    """Days spent in each stage (unrounded), from {status or MASUK: first time reached}.
    A stage is None when the ticket did not reach both of its ends."""
    def pertama(daftar):
        ada = [waktu_status[s] for s in daftar if waktu_status.get(s) is not None]
        return min(ada) if ada else None

    return {kode: _hari(pertama(awal), pertama(akhir)) for kode, _, awal, akhir in TAHAP}


def _senin(tanggal: date) -> date:
    return tanggal - timedelta(days=tanggal.weekday())


def tren_mingguan(baris: list) -> dict:
    """Tickets received vs completed per week (Monday-Sunday, WIB) for the tickets in the recap.

    A ticket counts as received in the week it was first recorded and as completed in the week it
    reached Selesai, so the totals equal the recap's "Total Tiket" and "Selesai". Weeks without any
    ticket in between are kept (as 0) so the time axis has no gaps."""
    masuk: dict = {}
    selesai: dict = {}
    for b in baris:
        if b["mulai"] is not None:
            minggu = _senin(b["mulai"].astimezone(WIB).date())
            masuk[minggu] = masuk.get(minggu, 0) + 1
        if b["status"] == SELESAI and b["selesai"] is not None:
            minggu = _senin(b["selesai"].astimezone(WIB).date())
            selesai[minggu] = selesai.get(minggu, 0) + 1
    semua = set(masuk) | set(selesai)
    if not semua:
        return {"label": [], "masuk": [], "selesai": []}
    minggu, akhir, label = min(semua), max(semua), []
    daftar = []
    while minggu <= akhir:
        daftar.append(minggu)
        minggu += timedelta(days=7)
    for m in daftar:
        label.append(f"{m.strftime('%d/%m')}–{(m + timedelta(days=6)).strftime('%d/%m')}")
    return {"label": label, "masuk": [masuk.get(m, 0) for m in daftar], "selesai": [selesai.get(m, 0) for m in daftar]}


def data_grafik(baris: list, per_wilayah: list, per_prioritas: list, total: dict) -> dict:
    """Numbers for the four Laporan Kinerja charts (Sprint 3 backlog 3).

    Everything except the weekly trend is copied from the structures the tables are rendered
    from, so a chart can never disagree with its table. Closed tickets are not in `baris`
    (PRD 5.3 BR-4), so they are left out of the charts just like the totals."""
    return {
        "tren": tren_mingguan(baris),
        "prioritas": {"label": [r["prioritas"] for r in per_prioritas], "jumlah": [r["total"] for r in per_prioritas],
                      "warna": [warna_prioritas(r["prioritas"]) for r in per_prioritas]},
        "tahap": {"label": [label for _, label, _, _ in TAHAP],
                  "hari": [total["rata_tahap"][kode] for kode, _, _, _ in TAHAP],
                  "jumlah_tiket": [total["jumlah_tahap"][kode] for kode, _, _, _ in TAHAP]},
        "wilayah": {"label": [r["nama_wilayah"] for r in per_wilayah],
                    "selesai": [r["selesai"] for r in per_wilayah],
                    "aktif": [r["aktif"] for r in per_wilayah],
                    "total": [r["total"] for r in per_wilayah]},
    }


class KontrolLaporanKinerja:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ data
    def _riwayat_per_tiket(self) -> dict:
        """id_work_order -> {"pertama": {status: first time}, "masuk": first entry, "terakhir": last entry}."""
        hasil: dict = {}
        for id_wo, status, waktu in (self.db.query(RiwayatStatus.id_work_order, RiwayatStatus.status,
                                                   RiwayatStatus.waktu)
                                     .order_by(RiwayatStatus.waktu, RiwayatStatus.id_riwayat).all()):
            waktu = _utc(waktu)
            if waktu is None:
                continue
            data = hasil.setdefault(id_wo, {"pertama": {}, "masuk": waktu, "terakhir": waktu})
            data["pertama"].setdefault(status, waktu)
            data["terakhir"] = waktu
        return hasil

    def _laporan_pertama(self) -> dict:
        """id_work_order -> earliest citizen report time (fallback start for tickets without history)."""
        return {
            id_wo: _utc(waktu)
            for id_wo, waktu in (self.db.query(Laporan.id_work_order, func.min(Laporan.tanggal_lapor))
                                 .filter(Laporan.id_work_order.isnot(None))
                                 .group_by(Laporan.id_work_order).all())
        }

    def _rating_per_tiket(self) -> dict:
        """id_work_order -> list of star ratings, one per reporting citizen (their first rating)."""
        hasil: dict = {}
        sudah: set = set()
        for id_wo, id_warga, nilai in (self.db.query(Laporan.id_work_order, Laporan.id_warga, Rating.nilai_bintang)
                                       .join(Rating, Rating.id_laporan == Laporan.id_laporan)
                                       .order_by(Rating.tanggal_rating, Rating.id_rating).all()):
            if (id_wo, id_warga) in sudah:
                continue
            sudah.add((id_wo, id_warga))
            hasil.setdefault(id_wo, []).append(nilai)
        return hasil

    def _baris_tiket(self, wo: WorkOrder, riwayat: Optional[dict], laporan_pertama: Optional[datetime],
                     nama_wilayah: str, rating: list, sekarang: datetime) -> dict:
        riwayat = riwayat or {"pertama": {}, "masuk": None, "terakhir": None}
        mulai = riwayat["masuk"] or laporan_pertama
        selesai = wo.status_work_order == SELESAI
        waktu_selesai = (riwayat["pertama"].get(SELESAI) or _utc(wo.tanggal_selesai)) if selesai else None

        waktu_status = {**riwayat["pertama"], MASUK: mulai}
        if waktu_selesai is not None:
            waktu_status.setdefault(SELESAI, waktu_selesai)
        tahap = durasi_tahap(waktu_status)

        umur = None if selesai else _hari(mulai, sekarang)
        lama_di_tahap = None if selesai else _hari(riwayat["terakhir"] or mulai, sekarang)
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
            "tahap_saat_ini": "Selesai" if selesai else (
                # Sprint 3 / CO-3: a temporary repair waiting for its follow-up visit (still Perbaikan,
                # whose duration keeps running until Selesai)
                TAHAP_MENUNGGU_KUNJUNGAN if wo.status_work_order == DALAM_PROSES and wo.jadwal_lanjutan_aktif
                else TAHAP_SAAT_INI.get(wo.status_work_order, wo.status_work_order)),
            "mulai": mulai,
            "selesai": waktu_selesai,
            "mulai_wib": _format_wib(mulai),
            "selesai_wib": _format_wib(waktu_selesai),
            "durasi_hari": _bulat(_hari(mulai, waktu_selesai)),
            "durasi_tahap": {kode: _bulat(nilai) for kode, nilai in tahap.items()},
            "_durasi_tahap_mentah": tahap,
            "umur_hari": _bulat(umur),
            "_umur_mentah": umur,
            "lama_di_tahap_hari": _bulat(lama_di_tahap),
            "rating": rating,
        }

    @staticmethod
    def _ringkas(baris: list) -> dict:
        selesai = [b for b in baris if b["status"] == SELESAI]
        aktif = [b for b in baris if b["status"] != SELESAI]
        durasi_selesai = [_hari(b["mulai"], b["selesai"]) for b in selesai]
        durasi_selesai = [d for d in durasi_selesai if d is not None]
        umur_aktif = [b["_umur_mentah"] for b in aktif if b["_umur_mentah"] is not None]
        skor = [b["risk_score"] for b in baris]
        rating = [r for b in baris for r in b["rating"]]
        rata_tahap, jumlah_tahap = {}, {}
        for kode, _, _, _ in TAHAP:
            nilai = [b["_durasi_tahap_mentah"][kode] for b in baris if b["_durasi_tahap_mentah"][kode] is not None]
            rata_tahap[kode] = _rata(nilai)
            jumlah_tahap[kode] = len(nilai)
        return {
            "total": len(baris),
            "selesai": len(selesai),
            "aktif": len(aktif),
            "tingkat_penyelesaian": _persen(len(selesai), len(baris)),
            "rata_durasi_hari": _rata(durasi_selesai),
            "rata_tahap": rata_tahap,
            "jumlah_tahap": jumlah_tahap,
            "rata_umur_aktif": _rata(umur_aktif),
            "umur_tertua": _bulat(max(umur_aktif)) if umur_aktif else None,
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
                 "tahap": [(kode, label) for kode, label, _, _ in TAHAP],
                 "tiket": [], "tiket_aktif": [], "per_wilayah": [], "per_prioritas": [],
                 "total": self._ringkas([]), "ditutup": self._ringkas_ditutup([]), "grafik": None,
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
        riwayat_per_tiket = self._riwayat_per_tiket()
        laporan_pertama = self._laporan_pertama()
        rating_per_tiket = self._rating_per_tiket()

        baris = []
        ditutup = []  # PRD 5.3 BR-4: closed tickets are reported separately, never in the totals
        for wo in query.all():
            b = self._baris_tiket(wo, riwayat_per_tiket.get(wo.id_work_order),
                                  laporan_pertama.get(wo.id_work_order),
                                  nama_wilayah.get(wo.id_wilayah, "Tanpa Wilayah"),
                                  rating_per_tiket.get(wo.id_work_order, []), sekarang)
            tanggal_wib = b["mulai"].astimezone(WIB).date() if b["mulai"] else None
            if (dari or sampai) and tanggal_wib is None:
                continue  # unknown start date cannot be placed in a period
            if dari and tanggal_wib < dari:
                continue
            if sampai and tanggal_wib > sampai:
                continue
            if wo.status_work_order == DITUTUP:
                ditutup.append({**b, "alasan_tutup": wo.alasan_tutup or "-"})
                continue
            baris.append(b)
        baris.sort(key=lambda b: (-b["risk_score"], b["id_work_order"]))

        if not baris and not ditutup:
            return {**hasil, "message": PESAN_KOSONG}
        hasil["ditutup"] = self._ringkas_ditutup(ditutup)

        per_wilayah = []
        for w in daftar_wilayah:
            if filter_["wilayah"] != "Semua" and w.id_wilayah != filter_["wilayah"]:
                continue
            isi = [b for b in baris if b["id_wilayah"] == w.id_wilayah]
            per_wilayah.append({"id_wilayah": w.id_wilayah, "nama_wilayah": w.nama_wilayah, **self._ringkas(isi),
                                "jumlah_ditutup": sum(1 for b in ditutup if b["id_wilayah"] == w.id_wilayah)})
        tanpa_wilayah = [b for b in baris if b["id_wilayah"] not in nama_wilayah]
        ditutup_tanpa_wilayah = [b for b in ditutup if b["id_wilayah"] not in nama_wilayah]
        if tanpa_wilayah or ditutup_tanpa_wilayah:
            per_wilayah.append({"id_wilayah": None, "nama_wilayah": "Tanpa Wilayah", **self._ringkas(tanpa_wilayah),
                                "jumlah_ditutup": len(ditutup_tanpa_wilayah)})

        per_prioritas = [{"prioritas": p, **self._ringkas([b for b in baris if b["prioritas"] == p])}
                         for p in URUTAN_PRIORITAS]

        # Active tickets, oldest first (unknown age last).
        tiket_aktif = sorted((b for b in baris if b["status"] != SELESAI),
                             key=lambda b: (b["_umur_mentah"] is None, -(b["_umur_mentah"] or 0), b["id_work_order"]))

        total = {**self._ringkas(baris), "jumlah_ditutup": len(ditutup)}
        return {**hasil, "tiket": baris, "tiket_aktif": tiket_aktif, "per_wilayah": per_wilayah,
                "per_prioritas": per_prioritas, "total": total,
                "grafik": data_grafik(baris, per_wilayah, per_prioritas, total) if baris else None}

    @staticmethod
    def _ringkas_ditutup(ditutup: list) -> dict:
        """Closed tickets (PRD 5.3 BR-4), counted per reason in the fixed ALASAN_TUTUP order."""
        return {
            "jumlah": len(ditutup),
            "per_alasan": [{"alasan": a, "jumlah": sum(1 for b in ditutup if b["alasan_tutup"] == a)}
                           for a in ALASAN_TUTUP],
            "tiket": sorted(ditutup, key=lambda b: b["id_work_order"]),
        }

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
        header = (["Wilayah", "Total Tiket", "Selesai", "Aktif", "Tingkat Penyelesaian (%)",
                   "Rata-rata Waktu Penyelesaian (hari)"]
                  + [f"Rata-rata Durasi {label} (hari)" for _, label, _, _ in TAHAP]
                  + ["Rata-rata Umur Tiket Aktif (hari)", "Umur Tiket Aktif Tertua (hari)",
                     "Rata-rata Risk Score", "Risk Score Tertinggi", "Tiket Urgent", "Rata-rata Rating",
                     "Jumlah Rating", "Ditutup (tidak dihitung)"])
        baris = [r for r in data["per_wilayah"]] + [{"nama_wilayah": "TOTAL", **data["total"]}]
        return self._csv(header, (
            [r["nama_wilayah"], r["total"], r["selesai"], r["aktif"], r["tingkat_penyelesaian"], r["rata_durasi_hari"]]
            + [r["rata_tahap"][kode] for kode, _, _, _ in TAHAP]
            + [r["rata_umur_aktif"], r["umur_tertua"], r["rata_risk"], r["risk_tertinggi"], r["jumlah_urgent"],
               r["rata_rating"], r["jumlah_rating"], r.get("jumlah_ditutup", 0)]
            for r in baris
        ))

    def csv_per_tiket(self, data: dict) -> str:
        header = (["ID Tiket", "Wilayah", "Kategori", "Lokasi", "Prioritas", "Risk Score", "Jumlah Pelapor",
                   "Status", "Tahap Saat Ini", "Dilaporkan (WIB)", "Selesai (WIB)",
                   "Waktu Penyelesaian (hari)", "Umur Tiket Aktif (hari)"]
                  + [f"Durasi {label} (hari)" for _, label, _, _ in TAHAP]
                  + ["Rata-rata Rating"])
        return self._csv(header, (
            [b["id_work_order"], b["nama_wilayah"], b["kategori"], b["lokasi"], b["prioritas"], b["risk_score"],
             b["exposure"], b["status"], b["tahap_saat_ini"], b["mulai_wib"], b["selesai_wib"], b["durasi_hari"],
             b["umur_hari"]]
            + [b["durasi_tahap"][kode] for kode, _, _, _ in TAHAP]
            + [_rata(b["rating"])]
            for b in data["tiket"]
        ))
