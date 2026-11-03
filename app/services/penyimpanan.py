"""Shared helpers: storing uploaded photos and generating readable IDs."""
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

DIREKTORI_UNGGAHAN = Path(__file__).resolve().parents[1] / "static" / "uploads"


def simpan_foto(data: bytes, format_gambar: str) -> str:
    """Write validated image bytes under a random name; return the public path."""
    ekstensi = {"JPEG": "jpg", "PNG": "png", "jpeg": "jpg", "jpg": "jpg", "png": "png"}.get(format_gambar, "jpg")
    DIREKTORI_UNGGAHAN.mkdir(parents=True, exist_ok=True)
    nama = f"{uuid.uuid4().hex}.{ekstensi}"
    (DIREKTORI_UNGGAHAN / nama).write_bytes(data)
    return f"static/uploads/{nama}"


def id_berurutan(db, kolom, awalan: str, digit: int = 4, per_tahun: bool = True) -> str:
    """Next ID like 'LAP-2026-0001' (per_tahun) or 'INS-0001', based on the highest existing number."""
    if per_tahun:
        tahun = datetime.now(timezone.utc).year
        prefix = f"{awalan}-{tahun}-"
    else:
        prefix = f"{awalan}-"
    pola = re.compile(re.escape(prefix) + r"(\d+)$")
    angka = [int(m.group(1)) for (v,) in db.query(kolom).filter(kolom.like(prefix + "%")).all() if (m := pola.match(v or ""))]
    return f"{prefix}{max(angka, default=0) + 1:0{digit}d}"


def id_acak(awalan: str) -> str:
    return f"{awalan}-{uuid.uuid4().hex[:12]}"



def dengan_coba_ulang(db, langkah, percobaan: int = 5):
    """Run `langkah()` (which adds rows and commits); on an ID collision with a
    simultaneous request, roll back and run it again with fresh IDs."""
    from sqlalchemy.exc import IntegrityError

    for ke in range(percobaan):
        try:
            return langkah()
        except IntegrityError:
            db.rollback()
            if ke == percobaan - 1:
                raise


def hapus_foto(url: str):
    """Remove a photo written by simpan_foto (used when the database write is abandoned)."""
    if url and url.startswith("static/uploads/"):
        (DIREKTORI_UNGGAHAN / url.rsplit("/", 1)[-1]).unlink(missing_ok=True)


def tulis_dengan_foto(db, data, format_gambar, langkah):
    """Save the photo (if any), then run `langkah(url_foto)` with retries; if it raises or
    returns a failure, the saved photo is deleted so no orphan files are left."""
    url = simpan_foto(data, format_gambar) if data else None
    try:
        hasil = dengan_coba_ulang(db, lambda: langkah(url))
    except Exception:
        hapus_foto(url)
        raise
    if not hasil.get("success"):
        hapus_foto(url)
    return hasil
