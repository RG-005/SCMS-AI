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
    "work_order": {"latitude": "FLOAT", "longitude": "FLOAT"},
    "laporan": {"latitude": "FLOAT", "longitude": "FLOAT"},
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


# Dependency untuk membuka & menutup sesi database otomatis di setiap request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()