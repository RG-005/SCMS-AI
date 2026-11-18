"""
Deploy (Sprint 3 point 7): every photo the seed points at exists and is served, so a fresh
deployment shows the demo photos instead of "Foto tidak tersedia". The demo photos are
labelled illustrations (database/foto_demo.py), kept in app/static/demo/ (part of the image),
not in app/static/uploads/ (the uploads volume, empty on a new server).
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.database import SessionLocal
from app.main import app
from app.models.entities import Laporan, Perbaikan
from database.foto_demo import FOTO, buat_foto_demo
from database.seed import seed_data

ROOT = Path(__file__).resolve().parent.parent


def _foto_seed() -> list:
    seed_data(verbose=False)
    db = SessionLocal()
    try:
        return ([lap.url_foto for lap in db.query(Laporan) if lap.url_foto]
                + [p.foto_sesudah for p in db.query(Perbaikan) if p.foto_sesudah])
    finally:
        db.close()


def test_setiap_foto_seed_ada_dan_disajikan():
    foto = _foto_seed()
    assert len(foto) == 4
    klien = TestClient(app)
    for path in foto:
        assert path.startswith("static/demo/"), path
        assert (ROOT / "app" / path).is_file(), path
        r = klien.get("/" + path)
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg", path


def test_foto_demo_tidak_disimpan_di_folder_unggahan():
    assert not any(path.startswith("static/uploads/") for path in _foto_seed())


@pytest.mark.parametrize("nama", sorted(FOTO))
def test_foto_demo_jpeg_asli_dan_ringan(nama):
    path = ROOT / "app" / "static" / "demo" / nama
    with Image.open(path) as img:
        assert img.format == "JPEG" and img.size == (1280, 960)
    assert path.stat().st_size < 400 * 1024


def test_generator_foto_demo_berjalan(tmp_path):
    hasil = buat_foto_demo(tmp_path)
    assert sorted(p.name for p in hasil) == sorted(FOTO)
    assert all(p.stat().st_size > 10_000 for p in hasil)
