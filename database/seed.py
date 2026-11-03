# database/seed.py
"""
Reset the database and fill it with the demo / BDD scenario data.

WARNING: this DROPS ALL TABLES. For anything other than a local SQLite file it
refuses to run unless you pass --force (CLI) or set SCMS_ALLOW_DB_RESET=1.
"""
import os
import sys

from passlib.context import CryptContext
from app.database import SessionLocal, engine, Base
from app.models.entities import (
    Warga, Admin, Wilayah, PenilikJalan, WorkOrder, Laporan
)

from app.services.risk_scoring import terapkan_ke_work_order

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _boleh_reset(force: bool) -> bool:
    return force or engine.url.get_backend_name() == "sqlite" or os.getenv("SCMS_ALLOW_DB_RESET") == "1"


def seed_data(force: bool = False, verbose: bool = True):
    if not _boleh_reset(force):
        raise RuntimeError(
            f"Refusing to drop all tables on {engine.url.render_as_string(hide_password=True)}. "
            "Run `python -m database.seed --force` or set SCMS_ALLOW_DB_RESET=1 if you really want to reset it."
        )
    # 1. Buat ulang semua tabel
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    hashed_pw = pwd_context.hash("password123")

    # 2. Seed Wilayah (Sesuai Skenario UC-G & UC-H)
    wilayah_list = [
        Wilayah(id_wilayah="WIL-01", nama_wilayah="Wilayah Gubeng"),
        Wilayah(id_wilayah="WIL-02", nama_wilayah="Wilayah Benowo"),
        Wilayah(id_wilayah="WIL-03", nama_wilayah="Wonokromo"),
    ]
    db.add_all(wilayah_list)

    # 3. Seed Akun Warga (Sesuai Mockup Citizen Home & Skenario UC-K)
    warga_list = [
        Warga(
            id_warga="USR-01",
            nik="3578010101900001",  # <-- Tambahkan NIK Warga 1
            nama_warga="Bpk. Tri Wahyudi",
            email="tri.wahyudi@gmail.com",
            no_hp="0812xxxxxxx", # Persis skenario BDD UC-K
            password_hash=hashed_pw,
            is_active=True
        ),
        Warga(
            id_warga="USR-02",
            nik="3578010101900002",  # <-- Tambahkan NIK Warga 2
            nama_warga="Warga Nonaktif",
            email="nonaktif@gmail.com",
            no_hp="0899xxxxxxx",
            password_hash=hashed_pw,
            is_active=False # Untuk test skenario akun tidak aktif UC-K
        ),
        Warga(
            id_warga="USR-03",
            nik="3578010101900003",
            nama_warga="Ibu Sari Rahayu",
            email="sari.rahayu@gmail.com",
            no_hp="0813xxxxxxx",
            password_hash=hashed_pw,
            is_active=True  # Pelapor pertama tiket REP-2026-00298 (skenario Duplikat UC-A)
        )
    ]
    db.add_all(warga_list)

    # 4. Seed Akun Admin & Kepala Bidang (Sesuai Mockup & Skenario UC-B, UC-K)
    admin_list = [
        Admin(
            id_admin="ADM-01",
            nama_admin="Ir. Hendra Kusuma, S.T., M.Eng.",
            email_admin="admin@dpupr.surabaya.go.id", # Persis skenario BDD UC-B & UC-K
            password_hash=hashed_pw,
            is_kepala_bidang=False,
            is_active=True
        ),
        Admin(
            id_admin="ADM-02",
            nama_admin="Ir. H. Bambang Soeprapto, M.T.",
            email_admin="kabid@dpupr.surabaya.go.id",
            password_hash=hashed_pw,
            is_kepala_bidang=True,
            is_active=True
        )
    ]
    db.add_all(admin_list)

    # 5. Seed Penilik Jalan (Sesuai Skenario UC-G & UC-B: Budi Santoso di Wilayah Gubeng)
    # Catatan: Wilayah Benowo (WIL-02) sengaja TIDAK diberi petugas tersedia untuk test skenario "No Penilik Jalan Available"
    penilik_list = [
        PenilikJalan(
            id_penilik="PNL-01",
            id_wilayah="WIL-01", # Wilayah Gubeng
            nama_penilik="Budi Santoso",
            email_penilik="budi.santoso@dpupr.surabaya.go.id",
            password_hash=hashed_pw,
            status_ketersediaan="Tersedia"
        )
    ]
    db.add_all(penilik_list)

    # 6. Seed Work Order / Tiket (Sesuai Skenario UC-A, UC-B, UC-C, UC-G, UC-H)
    # Risk Score, prioritas and SLA are NOT typed in: they are computed below with the
    # same BR-2 formula the app uses, from severity, exposure, vulnerability and road class.
    wo_list = [
        # Tiket utama untuk test Verifikasi (UC-B), Penugasan (UC-G), dan Dashboard (UC-H) -> 8.4 Urgent
        WorkOrder(
            id_work_order="REP-2026-00341",
            id_wilayah="WIL-01",  # Wilayah Gubeng
            kategori_kerusakan="Jalan Berlubang",
            lokasi_jalan="Jl. Raya Kertajaya No. 50, Gubeng, Surabaya",
            latitude=-7.27970, longitude=112.76180,
            kelas_jalan="Arteri Primer",
            severity_score_kasus=8.4, exposure_count=1, vulnerability_score=9.3,
            status_work_order="Disetujui",  # Siap ditugaskan di UC-G
        ),
        # Tiket skor ambigu/borderline untuk test UC-B -> 5.1 Borderline
        WorkOrder(
            id_work_order="REP-2026-00355",
            id_wilayah="WIL-01",
            kategori_kerusakan="Jalan Berlubang",
            lokasi_jalan="Jl. Raya Gubeng No. 45",
            latitude=-7.27350, longitude=112.75200,
            kelas_jalan="Lokal",
            severity_score_kasus=5.1, exposure_count=1, vulnerability_score=6.6,
            status_work_order="Dilaporkan",
        ),
        # Tiket di Wilayah Benowo (tanpa penilik jalan tersedia) untuk test UC-G Scenario 2 -> 7.5 Tinggi
        WorkOrder(
            id_work_order="REP-2026-00360",
            id_wilayah="WIL-02",  # Wilayah Benowo
            kategori_kerusakan="Jalan Amblas",
            lokasi_jalan="Jl. Raya Benowo No. 10",
            latitude=-7.22450, longitude=112.63200,
            kelas_jalan="Arteri Sekunder",
            severity_score_kasus=7.5, exposure_count=1, vulnerability_score=8.8,
            status_work_order="Disetujui",
        ),
        # Tiket AKTIF di Jl. Sudirman No. 45 untuk test Duplikat (UC-A Skenario 4) -> 8.0 Urgent.
        # Harus aktif: aturan BR-3 hanya menggabungkan laporan ke tiket yang belum Selesai.
        WorkOrder(
            id_work_order="REP-2026-00298",
            id_wilayah="WIL-01",
            id_penilik="PNL-01",
            kategori_kerusakan="Jalan Berlubang",
            lokasi_jalan="Jl. Sudirman No. 45, Surabaya",
            latitude=-7.26550, longitude=112.74700,
            kelas_jalan="Arteri Primer",
            severity_score_kasus=8.0, exposure_count=1, vulnerability_score=8.0,
            status_work_order="Ditugaskan",
        ),
        # Tiket selesai untuk skenario Lacak Status & Rating (UC-C / UC-J) -> 6.5 Tinggi
        WorkOrder(
            id_work_order="REP-2026-00290",
            id_wilayah="WIL-01",
            kategori_kerusakan="Retak Permukaan",
            lokasi_jalan="Jl. Dharmahusada No. 8, Surabaya",
            latitude=-7.26610, longitude=112.77900,
            kelas_jalan="Kolektor",
            severity_score_kasus=6.0, exposure_count=1, vulnerability_score=9.6,
            status_work_order="Selesai",
        ),
    ]
    for wo in wo_list:
        terapkan_ke_work_order(wo)
    db.add_all(wo_list)

    # 7. Seed Laporan Warga terkait tiket di atas
    laporan_list = [
        Laporan(
            id_laporan="LAP-001",
            id_work_order="REP-2026-00341",
            id_warga="USR-01",
            id_wilayah="WIL-01",
            deskripsi="Lubang besar di jalur kiri, dalam ±15cm",
            url_foto="static/uploads/jalan_berlubang_kertajaya.jpg",
            lokasi_teks="Jl. Raya Kertajaya No. 50, Gubeng, Surabaya",
            latitude=-7.27970,
            longitude=112.76180,
            severity_score=8.4,
            status="Disetujui"
        ),
        Laporan(
            id_laporan="LAP-002",
            id_work_order="REP-2026-00298",
            id_warga="USR-03",
            id_wilayah="WIL-01",
            deskripsi="Jalan berlubang dekat lampu merah Sudirman",
            url_foto="static/uploads/jalan_berlubang_sudirman_lama.jpg",
            lokasi_teks="Jl. Sudirman No. 45, Surabaya",
            latitude=-7.26550,
            longitude=112.74700,
            severity_score=8.0,
            status="Ditugaskan"
        ),
        Laporan(
            id_laporan="LAP-003",
            id_work_order="REP-2026-00290",
            id_warga="USR-01",
            id_wilayah="WIL-01",
            deskripsi="Retakan memanjang di aspal depan sekolah",
            url_foto="static/uploads/retak_dharmahusada.jpg",
            lokasi_teks="Jl. Dharmahusada No. 8, Surabaya",
            latitude=-7.26610,
            longitude=112.77900,
            severity_score=6.0,
            status="Selesai"
        )
    ]
    db.add_all(laporan_list)

    db.commit()
    db.close()
    if verbose:
        print("✅ Database berhasil dibuat dan diisi dengan Data Mockup & Skenario BDD!")

if __name__ == "__main__":
    seed_data(force="--force" in sys.argv[1:])