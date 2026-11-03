"""
Status flow of a Work Order, shared by all use cases.

Every status change goes through `ubah_status()`, which:
  * updates the Work Order and the status of every citizen report linked to it,
  * appends an entry to `riwayat_status` (the citizen timeline, UC-C), and
  * creates one notification per linked citizen report (UC-I).

Flow:  Dilaporkan -> Disetujui / Menunggu Inspeksi -> Ditugaskan -> Terinspeksi
       -> Dalam Proses -> Selesai   (Menunggu Penugasan when no inspector is free)
"""
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

# Inspector may inspect tickets in these states (UC-E)
SIAP_INSPEKSI = (DISETUJUI, MENUNGGU_INSPEKSI, DITUGASKAN)
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
}


class KonflikStatus(Exception):
    """The ticket changed in another request between reading and writing it."""


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


def kirim_notifikasi(db: Session, laporan: Laporan, judul: str, pesan: str):
    db.add(Notifikasi(
        id_notifikasi=id_acak("NTF"),
        id_laporan=laporan.id_laporan,
        id_warga=laporan.id_warga,
        judul=judul,
        pesan=f"{pesan} (Laporan {laporan.id_laporan}, tiket {laporan.id_work_order})",
        status_baca=False,
    ))


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
    for lap in laporan_list:
        kirim_notifikasi(db, lap, judul, pesan)
    return True
