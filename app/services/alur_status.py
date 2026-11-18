"""
Status flow of a Work Order, shared by all use cases.

Every status change goes through `ubah_status()`, which:
  * updates the Work Order and the status of every citizen report linked to it,
  * appends an entry to `riwayat_status` (the citizen timeline, UC-C), and
  * creates one notification per reporting citizen of the ticket (UC-I): a citizen who
    reported the same damage twice (merged by BR-3) still gets one notification.

Flow:  Dilaporkan -> Disetujui (clear score) / Menunggu Inspeksi (ambiguous score, inspector chosen)
       Disetujui -> Ditugaskan, or Menunggu Penugasan when no inspector is free (-> Ditugaskan later)
       Ditugaskan / Menunggu Inspeksi -> Terinspeksi -> Dalam Proses -> Selesai
       Dilaporkan / Terinspeksi -> Ditutup (Sprint 3, PRD 5.3 BR-4: final, reason required)
An inspector only inspects a ticket assigned to them (Ditugaskan, or Menunggu Inspeksi with
their id_penilik); an approved but unassigned ticket must be assigned first (UC-G).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Laporan, Notifikasi, RiwayatStatus, WorkOrder
from app.services.penyimpanan import id_acak

DILAPORKAN = "Dilaporkan"
DISETUJUI = "Disetujui"
MENUNGGU_INSPEKSI = "Menunggu Inspeksi"
MENUNGGU_PENUGASAN = "Menunggu Penugasan"
DITUGASKAN = "Ditugaskan"
TERINSPEKSI = "Terinspeksi"
DALAM_PROSES = "Dalam Proses"
SELESAI = "Selesai"
# Sprint 3 (PRD 5.3 BR-4): final status for a ticket that needs no repair. Not "Selesai",
# not active, cannot be rated, and reported separately in Laporan Kinerja.
DITUTUP = "Ditutup"

# Final statuses: no transition out, not active anywhere (Dashboard, Work Order, Tugas Lapangan, BR-3).
STATUS_FINAL = (SELESAI, DITUTUP)

# The only accepted reasons to close a ticket (single source for forms, backend and reports).
ALASAN_TIDAK_ADA_KERUSAKAN = "Tidak ditemukan kerusakan"
ALASAN_TUTUP = (
    ALASAN_TIDAK_ADA_KERUSAKAN,
    "Laporan tidak valid",
    "Sudah diperbaiki pihak lain",
    "Di luar kewenangan DPUPR",
)

# Inspector may inspect tickets in these states, and only when assigned to them (UC-E)
SIAP_INSPEKSI = (MENUNGGU_INSPEKSI, DITUGASKAN)
# Admin may (re)assign an inspector only after verification and before field work started (UC-G)
SIAP_PENUGASAN = (DISETUJUI, MENUNGGU_INSPEKSI, MENUNGGU_PENUGASAN, DITUGASKAN)
# "No inspector free" may only park tickets that have no inspector working on them yet
BOLEH_MENUNGGU_PENUGASAN = (DISETUJUI, MENUNGGU_PENUGASAN)

# Stages shown on the citizen timeline (UC-C): (label, statuses that complete this stage)
TAHAPAN_LINIMASA = [
    ("Laporan Diterima", {DILAPORKAN}),
    ("Diverifikasi Admin", {DISETUJUI, MENUNGGU_INSPEKSI, MENUNGGU_PENUGASAN, DITUGASKAN}),
    ("Survei Lapangan", {TERINSPEKSI}),
    ("Perbaikan Berjalan", {DALAM_PROSES}),
    ("Selesai Diperbaiki", {SELESAI}),
]

PESAN_NOTIFIKASI = {
    DISETUJUI: ("Laporan diverifikasi", "Laporan Anda telah diverifikasi dan disetujui oleh Dinas PUPR."),
    MENUNGGU_INSPEKSI: ("Menunggu inspeksi", "Laporan Anda dijadwalkan untuk pengecekan fisik oleh Penilik Jalan."),
    MENUNGGU_PENUGASAN: ("Menunggu petugas", "Laporan Anda menunggu ketersediaan Penilik Jalan di wilayah Anda."),
    DITUGASKAN: ("Petugas ditugaskan", "Penilik Jalan telah ditugaskan untuk menangani laporan Anda."),
    TERINSPEKSI: ("Laporan telah disurvei", "Laporan telah disurvei petugas lapangan."),
    DALAM_PROSES: ("Perbaikan dimulai", "Perbaikan jalan pada laporan Anda sedang dikerjakan."),
    SELESAI: ("Perbaikan selesai", "Perbaikan jalan pada laporan Anda telah selesai. Beri penilaian atas hasilnya."),
    DITUTUP: ("Laporan ditutup", "Laporan Anda ditutup oleh Dinas PUPR tanpa perbaikan."),
}


# Legal transitions (PRD status flow). Anything not listed here is rejected by ubah_status(),
# so no caller can skip a stage, move a ticket backwards, or bypass a running inspection
# (e.g. "Menunggu Inspeksi" -> "Disetujui").
TRANSISI_SAH = {
    DILAPORKAN: {DISETUJUI, MENUNGGU_INSPEKSI, DITUTUP},  # Ditutup: Admin "Tolak" at verification
    # an approved ticket must be assigned (UC-G) before it can be inspected (UC-E)
    DISETUJUI: {MENUNGGU_PENUGASAN, DITUGASKAN},
    MENUNGGU_INSPEKSI: {DITUGASKAN, TERINSPEKSI},
    MENUNGGU_PENUGASAN: {DITUGASKAN},
    DITUGASKAN: {TERINSPEKSI},
    TERINSPEKSI: {DALAM_PROSES, DITUTUP},  # Ditutup: Admin confirms the inspector's closing recommendation
    DALAM_PROSES: {SELESAI},
    SELESAI: set(),
    DITUTUP: set(),
}
# A same-status entry is only meaningful here: changing the inspector, or a progress note.
BOLEH_CATAT_ULANG = {DITUGASKAN, DALAM_PROSES}


class KonflikStatus(Exception):
    """The ticket changed in another request between reading and writing it."""


class TransisiTidakSah(Exception):
    """The requested status change is not allowed by the status flow."""

    def __init__(self, id_work_order: str, dari: str, ke: str):
        super().__init__(f"{id_work_order}: {dari} -> {ke}")
        self.id_work_order, self.dari, self.ke = id_work_order, dari, ke


def boleh_transisi(dari: Optional[str], ke: str, catat_walau_sama: bool = False) -> bool:
    """True when `dari` -> `ke` is allowed. Same status counts as allowed (a no-op),
    except a forced re-record, which is limited to BOLEH_CATAT_ULANG."""
    if dari == ke:
        return not catat_walau_sama or ke in BOLEH_CATAT_ULANG
    return ke in TRANSISI_SAH.get(dari, set())


def tahapan_linimasa(status_tercapai: set[str]) -> list[dict]:
    """Stage list for the vertical stepper: each stage is done when one of its statuses was reached."""
    hasil = []
    for label, status_set in TAHAPAN_LINIMASA:
        selesai = bool(status_set & status_tercapai)
        hasil.append({"label": label, "selesai": selesai})
    # a later stage implies the earlier ones (e.g. a ticket approved without inspection)
    for i in range(len(hasil) - 2, -1, -1):
        if hasil[i + 1]["selesai"]:
            hasil[i]["selesai"] = True
    return hasil


def catat_riwayat(db: Session, wo: WorkOrder, status: str, keterangan: str = "", aktor: Optional[str] = None):
    db.add(RiwayatStatus(id_work_order=wo.id_work_order, status=status, keterangan=keterangan or None, aktor=aktor))


def kirim_notifikasi(db: Session, laporan: Laporan, judul: str, pesan: str) -> Optional[Notifikasi]:
    """In-app notification to the citizen who sent `laporan`. An inspector's finding has no
    citizen (team decision 5.9 no. 3), so nobody is notified for it."""
    if laporan.id_warga is None:
        return None
    notif = Notifikasi(
        id_notifikasi=id_acak("NTF"),
        id_laporan=laporan.id_laporan,
        id_warga=laporan.id_warga,
        judul=judul,
        pesan=f"{pesan} (Laporan {laporan.id_laporan}, tiket {laporan.id_work_order})",
        status_baca=False,
    )
    db.add(notif)
    return notif


def ubah_status(
    db: Session,
    wo: WorkOrder,
    status_baru: str,
    keterangan: str = "",
    aktor: Optional[str] = None,
    catat_walau_sama: bool = False,
) -> bool:
    """Change the Work Order status. Returns False (and does nothing) when it is unchanged,
    unless `catat_walau_sama` is set (e.g. a progress note while still "Dalam Proses")."""
    status_lama = wo.status_work_order
    if status_lama == status_baru and not catat_walau_sama:
        return False
    if not boleh_transisi(status_lama, status_baru, catat_walau_sama):
        raise TransisiTidakSah(wo.id_work_order, status_lama, status_baru)
    # Atomic compare-and-set: only one of several simultaneous requests can make
    # this transition; the others get KonflikStatus (shown to the user as 409).
    berubah = (db.query(WorkOrder)
               .filter(WorkOrder.id_work_order == wo.id_work_order, WorkOrder.status_work_order == status_lama)
               .update({WorkOrder.status_work_order: status_baru}, synchronize_session=False))
    if berubah != 1:
        raise KonflikStatus(wo.id_work_order)
    wo.status_work_order = status_baru
    laporan_list = db.query(Laporan).filter_by(id_work_order=wo.id_work_order).all()
    for lap in laporan_list:
        lap.status = status_baru
    catat_riwayat(db, wo, status_baru, keterangan, aktor)
    judul, pesan = PESAN_NOTIFIKASI.get(status_baru, ("Status laporan diperbarui", f"Status laporan diperbarui menjadi: {status_baru}."))
    if keterangan:
        pesan = f"{pesan} Catatan: {keterangan}"
    for lap in laporan_per_warga(laporan_list):
        kirim_notifikasi(db, lap, judul, pesan)
    return True


def laporan_per_warga(laporan_list: list[Laporan]) -> list[Laporan]:
    """One report per reporting citizen (their latest one, by its sequential ID), so a citizen
    whose two reports were merged into the same ticket is notified once per status change (BR-4)."""
    terbaru: dict[str, Laporan] = {}
    for lap in laporan_list:
        if lap.id_warga is None:
            continue  # an inspector's finding (PRD 5.3): no citizen to notify
        lama = terbaru.get(lap.id_warga)
        if lama is None or lap.id_laporan > lama.id_laporan:
            terbaru[lap.id_warga] = lap
    return list(terbaru.values())


class AlasanTutupTidakSah(ValueError):
    """The closing reason is empty or not one of ALASAN_TUTUP."""


def status_final(status: Optional[str]) -> bool:
    return status in STATUS_FINAL


def tutup_tiket(db: Session, wo: WorkOrder, alasan: str, aktor: Optional[str] = None) -> bool:
    """Close a ticket (PRD 5.3 BR-4) through ubah_status(): compare-and-set, history entry
    "Ditutup: <alasan>" and one notification per reporting citizen that carries the reason."""
    alasan = (alasan or "").strip()
    if alasan not in ALASAN_TUTUP:
        raise AlasanTutupTidakSah(alasan)
    berubah = ubah_status(db, wo, DITUTUP, f"Ditutup: {alasan}", aktor)
    if berubah:
        wo.alasan_tutup = alasan
        wo.ditutup_oleh = (aktor or "")[:100] or None
        wo.tanggal_ditutup = datetime.now(timezone.utc)
    return berubah
