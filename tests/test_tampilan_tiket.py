"""
Ticket detail layout (fast tests, no browser):

1. The "Prioritas Penanganan" block sits in a fixed place: header = left column
   (flex-1 min-w-0, long addresses wrap inside it) + right block (shrink-0, right aligned
   from sm up). Below sm the header is stacked on purpose (flex-col).
2. Priority colours come from one source, warna_prioritas() (same as the map), through
   the lencana_prioritas macro in _macro_tiket.html.
3. The report photo is shown whole with a small label; no fake detection box and no
   file path. Real boxes from the AI analysis are saved when the report is sent
   (laporan.kotak_deteksi) and drawn on a canvas; reports without boxes get none.
"""
import json
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

import app.controllers.kontrol_pelaporan as modul_pelaporan
import app.services.penyimpanan as modul_penyimpanan
from app.controllers.kontrol_dashboard import WARNA_PRIORITAS, warna_prioritas
from app.database import SessionLocal
from app.main import app, templates
from app.models.entities import Laporan, WorkOrder
from app.services.ai_service import AIService, VisiYolo
from database.seed import seed_data
from tests.test_keamanan_dan_logika import KONFIG_V4, NAMA_V4, _FakeYoloV4, gambar

WARGA = "0812xxxxxxx"          # USR-01: LAP-2026-0001 (REP-2026-00341), LAP-2026-0003 (REP-2026-00290)
ADMIN = "admin@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"  # assigned to REP-2026-00298
ALAMAT_PANJANG = ("Jl. Raya Prof. Dr. Ir. Soekarno No. 123 Blok C-17, depan pertokoan dan halte bus, "
                  "Kelurahan Kalirungkut, Kecamatan Rungkut")


@pytest.fixture
def db_bersih(tmp_path, monkeypatch):
    seed_data(verbose=False)
    monkeypatch.setattr(modul_penyimpanan, "DIREKTORI_UNGGAHAN", tmp_path)


def klien(identifier=None, password="password123") -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


def ubah_wo(id_wo, **kolom):
    db = SessionLocal()
    try:
        wo = db.get(WorkOrder, id_wo)
        for k, v in kolom.items():
            setattr(wo, k, v)
        db.commit()
    finally:
        db.close()


# ----------------------------------------------------------- tiny DOM parser
class _Elemen:
    def __init__(self, tag, attrs, induk=None):
        self.tag, self.attrs, self.induk, self.anak = tag, dict(attrs), induk, []

    @property
    def kelas(self):
        return set((self.attrs.get("class") or "").split())

    def semua(self):
        for a in self.anak:
            yield a
            yield from a.semua()


class _Pohon(HTMLParser):
    KOSONG = {"img", "br", "hr", "input", "meta", "link", "source", "area", "col", "wbr"}

    def __init__(self, html):
        super().__init__()
        self.akar = _Elemen("root", [])
        self.kini = self.akar
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        el = _Elemen(tag, attrs, self.kini)
        self.kini.anak.append(el)
        if tag not in self.KOSONG:
            self.kini = el

    def handle_endtag(self, tag):
        el = self.kini
        while el is not self.akar and el.tag != tag:
            el = el.induk
        if el is not self.akar:
            self.kini = el.induk


def dom(html):
    return _Pohon(html).akar


def cari(akar, **syarat):
    hasil = []
    for el in akar.semua():
        if all((k == "kelas" and v in el.kelas) or el.attrs.get(k) == v for k, v in syarat.items()):
            hasil.append(el)
    return hasil


def teks_terlihat(html):
    """Page text without tags, src/href/data-* attribute values or script bodies."""
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


# ------------------------------------------------------------- 1. header
HALAMAN_DETAIL = [
    (ADMIN, "/verifikasi?ticket_id=REP-2026-00290"),
    (ADMIN, "/verifikasi?ticket_id=REP-2026-00355"),
    (ADMIN, "/work-orders?select_ticket=REP-2026-00341"),
    (WARGA, "/lacak?id=LAP-2026-0003"),
    (PENILIK, "/TugasLapangan/REP-2026-00298"),
]


@pytest.mark.parametrize("akun, halaman", HALAMAN_DETAIL)
def test_kepala_tiket_kiri_fleksibel_dan_prioritas_tetap_di_kanan(db_bersih, akun, halaman):
    akar = dom(klien(akun).get(halaman).text)
    kepala = cari(akar, id="kepalaTiket")
    assert len(kepala) == 1, halaman
    kepala = kepala[0]
    # stacked below sm on purpose, side by side from sm up; never an accidental wrap
    assert {"flex", "flex-col", "sm:flex-row", "sm:justify-between", "sm:items-start"} <= kepala.kelas
    assert "flex-wrap" not in kepala.kelas
    kolom = [a for a in kepala.anak if a.tag == "div"]
    assert len(kolom) == 2
    kiri, kanan = kolom
    assert {"flex-1", "min-w-0"} <= kiri.kelas
    assert {"shrink-0", "sm:text-right"} <= kanan.kelas
    lencana = [el for el in kanan.semua() if "lencana-prioritas" in el.kelas]
    assert lencana and lencana[0].attrs.get("data-prioritas"), "priority badge must be in the right block"
    # the address may wrap, but only inside the left column
    assert any("break-words" in el.kelas for el in kiri.semua())


def test_alamat_panjang_tidak_mengubah_struktur_kepala(db_bersih):
    def struktur(id_wo):
        akar = dom(klien(ADMIN).get(f"/verifikasi?ticket_id={id_wo}").text)
        kepala = cari(akar, id="kepalaTiket")[0]
        return [(a.tag, sorted(a.kelas)) for a in kepala.anak]

    pendek = struktur("REP-2026-00290")
    ubah_wo("REP-2026-00290", lokasi_jalan=ALAMAT_PANJANG[:100])
    assert struktur("REP-2026-00290") == pendek


# -------------------------------------------------------------- 2. colours
@pytest.mark.parametrize("prioritas, warna", [
    ("Urgent", "#DC2626"), ("Tinggi", "#EA580C"), ("Borderline", "#D97706"), ("Rendah", "#16A34A"),
])
def test_macro_lencana_memakai_warna_peta(prioritas, warna):
    makro = templates.env.get_template("_macro_tiket.html").module
    assert warna_prioritas(prioritas) == warna
    for html in (str(makro.lencana_prioritas(prioritas)), str(makro.lencana_prioritas(prioritas, besar=True))):
        assert f'style="background-color: {warna}"' in html
        assert f'data-prioritas="{prioritas}"' in html
    assert f"Prioritas Penanganan: {prioritas}" in str(makro.lencana_prioritas(prioritas, besar=True))


@pytest.mark.parametrize("akun, halaman", HALAMAN_DETAIL + [
    (ADMIN, "/Dashboard"), (ADMIN, "/work-orders"), (ADMIN, "/verifikasi"),
    (PENILIK, "/TugasLapangan"), (WARGA, "/Beranda"),
])
def test_semua_lencana_prioritas_berwarna_dari_satu_sumber(db_bersih, akun, halaman):
    akar = dom(klien(akun).get(halaman).text)
    lencana = [el for el in akar.semua() if "lencana-prioritas" in el.kelas]
    assert lencana, halaman
    for el in lencana:
        prioritas = el.attrs["data-prioritas"]
        assert el.attrs["style"] == f"background-color: {WARNA_PRIORITAS[prioritas]}", (halaman, prioritas)


def test_lencana_verifikasi_sesuai_prioritas_tiket(db_bersih):
    # REP-2026-00290 is Tinggi: it used to be shown in red (text-red-600, the Urgent colour)
    akar = dom(klien(ADMIN).get("/verifikasi?ticket_id=REP-2026-00290").text)
    lencana = cari(akar, id="prioritasTiket")[0]
    assert lencana.attrs["data-prioritas"] == "Tinggi"
    assert lencana.attrs["style"] == "background-color: #EA580C"


def test_tidak_ada_warna_prioritas_yang_ditulis_langsung():
    from pathlib import Path
    folder = Path(__file__).resolve().parents[1] / "app" / "views" / "templates"
    for p in folder.glob("*.html"):
        isi = p.read_text(encoding="utf-8")
        assert not re.search(r"prioritas\s*(==|in)\s*[\['\"]", isi), f"{p.name}: priority colour chosen in the template"
        assert not re.search(r"risk_score\s*>=\s*\d.*?(bg|text)-(red|orange|amber)-", isi), \
            f"{p.name}: priority colour derived from risk_score in the template"


# ------------------------------------------------------------- 3. photo
@pytest.mark.parametrize("akun, halaman", [h for h in HALAMAN_DETAIL if "work-orders" not in h[1]])
def test_foto_laporan_utuh_tanpa_kotak_palsu_dan_tanpa_path(db_bersih, akun, halaman):
    html = klien(akun).get(halaman).text
    akar = dom(html)
    foto = [el for el in akar.semua() if el.tag == "figure" and "foto-laporan" in el.kelas]
    assert foto, halaman
    for fig in foto:
        img = [el for el in fig.semua() if el.tag == "img"]
        placeholder = [el for el in fig.semua() if "foto-placeholder" in el.kelas]
        if not img:
            # REP-2026-00355 has no citizen report in the seed: placeholder, never a fake box
            assert "hidden" not in placeholder[0].kelas and fig.attrs["data-jumlah-kotak"] == "0"
            continue
        assert "object-contain" in img[0].kelas and "object-cover" not in img[0].kelas
        assert img[0].attrs.get("onerror") == "fotoGagal(this)"
        # seed reports have no saved boxes: photo only, no canvas
        assert fig.attrs["data-jumlah-kotak"] == "0"
        assert not [el for el in fig.semua() if el.tag == "canvas"]
        placeholder = [el for el in fig.semua() if "foto-placeholder" in el.kelas]
        assert placeholder and "hidden" in placeholder[0].kelas  # shown only when loading fails
    teks = teks_terlihat(html)
    assert "static/uploads" not in teks and ".jpg" not in teks
    assert "Bukti Foto Laporan Warga" not in teks


def test_laporan_tanpa_foto_menampilkan_placeholder():
    makro = templates.env.get_template("_macro_tiket.html").module
    html = str(makro.foto_laporan(Laporan(url_foto="", severity_score=5.0), "Jalan Berlubang"))
    akar = dom(html)
    assert not [el for el in akar.semua() if el.tag in ("img", "canvas")]
    placeholder = [el for el in akar.semua() if "foto-placeholder" in el.kelas][0]
    assert "flex" in placeholder.kelas and "hidden" not in placeholder.kelas
    assert "Foto tidak tersedia" in html


@pytest.mark.parametrize("data, hasil", [
    (None, []),
    ("", []),
    ("bukan json", []),
    ('{"kategori": "x"}', []),
    ('[{"kategori": "Jalan Berlubang", "confidence": 90, "x1": 0.3, "y1": 0.4, "x2": 0.7, "y2": 0.6}]',
     [{"kategori": "Jalan Berlubang", "confidence": 90.0, "x1": 0.3, "y1": 0.4, "x2": 0.7, "y2": 0.6}]),
    # missing fields, reversed or empty boxes are dropped; values are clipped to 0-1
    ('[{"kategori": "A", "confidence": 50, "x1": 0.5, "y1": 0.1, "x2": 0.2, "y2": 0.3},'
     ' {"kategori": "B", "confidence": 50, "x1": -1, "y1": 0, "x2": 2, "y2": 0.5}, {"kategori": "C"}]',
     [{"kategori": "B", "confidence": 50.0, "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 0.5}]),
])
def test_daftar_kotak_divalidasi(data, hasil):
    assert Laporan(kotak_deteksi=data).daftar_kotak == hasil


def _ai_yolo():
    model = _FakeYoloV4([(0, 0.9, [0.5, 0.5, 0.4, 0.2]), (1, 0.6, [0.2, 0.3, 0.2, 0.2])], NAMA_V4)
    return AIService(visi=VisiYolo(model=model, config=KONFIG_V4))


def _lapor(c, **form):
    isian = {"lokasi_jalan": "Jl. Manyar Kertoarjo No. 5, Surabaya", "latitude": "-7.28100",
             "longitude": "112.76900", "deskripsi": "Lubang besar di tengah jalan dekat sekolah",
             "kategori_pilihan": "Jalan Berlubang", "id_wilayah": "WIL-01"}
    isian.update(form)
    return c.post("/lapor", data=isian, files={"foto": ("jalan.jpg", gambar(), "image/jpeg")}, follow_redirects=False)


def _laporan_terbaru():
    db = SessionLocal()
    try:
        return db.query(Laporan).order_by(Laporan.id_laporan.desc()).first()
    finally:
        db.close()


def test_kotak_yolo_tersimpan_saat_lapor_dan_digambar_di_detail(db_bersih, monkeypatch):
    ai = _ai_yolo()
    monkeypatch.setattr(modul_pelaporan, "get_ai_service", lambda: ai)
    r = _lapor(klien(WARGA))
    assert r.status_code == 303, r.text[:300]
    lap = _laporan_terbaru()
    assert lap.daftar_kotak == [
        {"kategori": "Jalan Berlubang", "confidence": 90.0, "x1": 0.3, "y1": 0.4, "x2": 0.7, "y2": 0.6},
        {"kategori": "Retak Permukaan", "confidence": 60.0, "x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.4},
    ]
    assert json.loads(lap.kotak_deteksi) == lap.daftar_kotak

    akar = dom(klien(ADMIN).get(f"/verifikasi?ticket_id={lap.id_work_order}").text)
    fig = cari(akar, id="fotoLaporan")[0]
    assert fig.attrs["data-jumlah-kotak"] == "2"
    img = [el for el in fig.semua() if el.tag == "img"][0]
    assert json.loads(img.attrs["data-kotak"]) == lap.daftar_kotak
    assert [el for el in fig.semua() if el.tag == "canvas" and "kanvas-kotak" in el.kelas]
    # the corner label shows the AI category of the strongest box
    label = [el for el in fig.semua() if "foto-label" in el.kelas]
    assert label
    assert "/static/js/kotak_deteksi.js" in klien(ADMIN).get(f"/verifikasi?ticket_id={lap.id_work_order}").text


def test_laporan_mode_simulasi_tidak_punya_kotak(db_bersih):
    r = _lapor(klien(WARGA))
    assert r.status_code == 303
    lap = _laporan_terbaru()
    assert lap.kotak_deteksi is None and lap.daftar_kotak == []
    akar = dom(klien(ADMIN).get(f"/verifikasi?ticket_id={lap.id_work_order}").text)
    fig = cari(akar, id="fotoLaporan")[0]
    assert fig.attrs["data-jumlah-kotak"] == "0"
    assert not [el for el in fig.semua() if el.tag == "canvas"]
    assert "data-kotak" not in [el for el in fig.semua() if el.tag == "img"][0].attrs


def test_kolom_kotak_deteksi_ditambahkan_ke_database_lama(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.database import pastikan_kolom_terbaru

    lama = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with lama.begin() as conn:
        conn.execute(text("CREATE TABLE laporan (id_laporan VARCHAR(20) PRIMARY KEY, url_foto VARCHAR(255))"))
        conn.execute(text("INSERT INTO laporan VALUES ('LAP-LAMA-1', 'static/uploads/a.jpg')"))
    pastikan_kolom_terbaru(lama)
    kolom = {c["name"]: c for c in inspect(lama).get_columns("laporan")}
    assert "kotak_deteksi" in kolom and kolom["kotak_deteksi"]["nullable"]
    with lama.connect() as conn:
        assert conn.execute(text("SELECT kotak_deteksi FROM laporan")).scalar() is None
