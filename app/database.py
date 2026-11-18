# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Mengambil URL PostgreSQL dari file .env
# Format PostgreSQL: postgresql://username:password@localhost:5432/scms_db
# (Fallback ke SQLite lokal jika .env belum disetting agar tim langsung bisa ngoding)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./scms_dev.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Kolom yang ditambahkan setelah Sprint 1. create_all() tidak mengubah tabel yang
# sudah ada, jadi kolom ini ditambahkan di sini agar database lama tetap bisa dipakai.
KOLOM_TAMBAHAN = {
    "warga": {"alamat_domisili": "VARCHAR(255)"},
    "wilayah": {"kecamatan": "VARCHAR(100)"},
    "penilik_jalan": {"nip": "VARCHAR(20)"},
    "work_order": {"latitude": "FLOAT", "longitude": "FLOAT", "nomor_spk": "VARCHAR(50)",
                   "tim_pelaksana": "VARCHAR(100)", "tanggal_selesai": "TIMESTAMP",
                   "severity_ai": "FLOAT", "alasan_tutup": "VARCHAR(50)", "ditutup_oleh": "VARCHAR(100)",
                   "tanggal_ditutup": "TIMESTAMP", "perlu_tinjauan_manual": "BOOLEAN"},
    "laporan": {"latitude": "FLOAT", "longitude": "FLOAT", "kotak_deteksi": "TEXT",
                "perlu_tinjauan_manual": "BOOLEAN", "sumber": "VARCHAR(20)",
                "id_penilik_pencatat": "VARCHAR(20)"},
    "inspeksi": {"id_work_order": "VARCHAR(20)", "dimensi_kerusakan": "VARCHAR(50)",
                 "rekomendasi_penanganan": "VARCHAR(50)", "kategori_terkonfirmasi": "VARCHAR(50)",
                 "tingkat_kerusakan": "VARCHAR(20)", "severity_lapangan": "FLOAT",
                 "rekomendasi_tutup": "BOOLEAN", "alasan_rekomendasi": "VARCHAR(50)",
                 "keputusan_rekomendasi": "VARCHAR(20)", "diputuskan_oleh": "VARCHAR(100)"},
    "perbaikan": {"catatan": "TEXT", "dicatat_oleh": "VARCHAR(50)", "waktu": "TIMESTAMP",
                  "jadwal_lanjutan": "VARCHAR(50)", "perbaikan_sementara": "BOOLEAN",
                  "status_jadwal": "VARCHAR(20)", "kunjungan_dicatat_pada": "TIMESTAMP",
                  "catatan_kunjungan": "TEXT", "foto_kunjungan": "VARCHAR(255)"},
    "notifikasi": {"judul": "VARCHAR(100)", "waktu_kirim": "TIMESTAMP",
                   "jumlah_percobaan": "INTEGER DEFAULT 0", "waktu_percobaan_terakhir": "TIMESTAMP"},
    "rating": {"tanggal_rating": "TIMESTAMP"},
}


def pastikan_kolom_terbaru(eng=None):
    from sqlalchemy import inspect, text

    eng = eng or engine
    insp = inspect(eng)
    with eng.begin() as conn:
        for tabel, kolom in KOLOM_TAMBAHAN.items():
            if not insp.has_table(tabel):
                continue
            ada = {c["name"] for c in insp.get_columns(tabel)}
            for nama, tipe in kolom.items():
                if nama not in ada:
                    conn.execute(text(f"ALTER TABLE {tabel} ADD COLUMN {nama} {tipe}"))
        # Sprint 3: old tickets have no separate AI severity yet. Before any field inspection
        # the case severity is the AI severity, so copy it once (idempotent, NULL rows only).
        if insp.has_table("work_order"):
            kolom_wo = {c["name"] for c in inspect(conn).get_columns("work_order")}
            if {"severity_ai", "severity_score_kasus"} <= kolom_wo:
                conn.execute(text("UPDATE work_order SET severity_ai = severity_score_kasus "
                                  "WHERE severity_ai IS NULL"))
        if insp.has_table("notifikasi"):
            # Deprecated column (old BR-8), still NOT NULL in the model: old rows get 0
            conn.execute(text("UPDATE notifikasi SET jumlah_percobaan = 0 WHERE jumlah_percobaan IS NULL"))
        if insp.has_table("laporan"):
            # Sprint 3: every report written before inspector findings existed came from a citizen
            conn.execute(text("UPDATE laporan SET sumber = 'Warga' WHERE sumber IS NULL"))
            izinkan_id_warga_kosong(conn)


def izinkan_id_warga_kosong(conn):
    """Sprint 3 (team decision 5.9 no. 3): laporan.id_warga becomes nullable for inspector findings.
    Idempotent: does nothing when the column already allows NULL.

    * PostgreSQL (and other databases with ALTER COLUMN): ALTER COLUMN ... DROP NOT NULL.
    * SQLite cannot drop NOT NULL, so the table is rebuilt inside the caller's transaction: its
      original CREATE TABLE (with only "NOT NULL" removed from id_warga, so every other column,
      default and FOREIGN KEY stays) is created under a temporary name, every row is copied
      column by column, the row count is compared, the old table is dropped, the new one renamed
      and its indexes recreated. Any error rolls the whole transaction back: no data is lost.
      SCMS does not enable PRAGMA foreign_keys, so dropping the old table does not cascade.
    """
    import re

    from sqlalchemy import inspect, text

    kolom = {c["name"]: c for c in inspect(conn).get_columns("laporan")}
    if "id_warga" not in kolom or kolom["id_warga"]["nullable"]:
        return
    if conn.dialect.name != "sqlite":
        conn.execute(text("ALTER TABLE laporan ALTER COLUMN id_warga DROP NOT NULL"))
        return

    sql_tabel = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='laporan'")).scalar()
    sql_baru, diganti = re.subn(r"(\bid_warga\b[^,]*?)\s+NOT NULL", r"\1", sql_tabel, count=1, flags=re.I)
    if not diganti:
        raise RuntimeError("Definisi NOT NULL laporan.id_warga tidak ditemukan; migrasi dibatalkan")
    sql_baru = re.sub(r'^\s*CREATE TABLE\s+"?laporan"?', "CREATE TABLE laporan__baru", sql_baru, count=1, flags=re.I)
    indeks = [r[0] for r in conn.execute(text(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='laporan' AND sql IS NOT NULL"))]
    daftar_kolom = ", ".join(f'"{n}"' for n in kolom)
    jumlah_awal = conn.execute(text("SELECT COUNT(*) FROM laporan")).scalar()

    conn.execute(text("DROP TABLE IF EXISTS laporan__baru"))
    conn.execute(text(sql_baru))
    conn.execute(text(f"INSERT INTO laporan__baru ({daftar_kolom}) SELECT {daftar_kolom} FROM laporan"))
    if conn.execute(text("SELECT COUNT(*) FROM laporan__baru")).scalar() != jumlah_awal:
        raise RuntimeError("Jumlah baris laporan berbeda setelah disalin; migrasi dibatalkan")
    conn.execute(text("DROP TABLE laporan"))
    conn.execute(text("ALTER TABLE laporan__baru RENAME TO laporan"))
    for sql_indeks in indeks:
        conn.execute(text(sql_indeks))


# Dependency untuk membuka & menutup sesi database otomatis di setiap request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()