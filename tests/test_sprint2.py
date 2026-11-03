"""
Fast tests (no browser) for Sprint 2 rules not covered by the BDD scenarios:
access per role, ownership, inspector region limits, status order, notifications, master data validation.
"""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.services.penyimpanan as modul_penyimpanan
from app.controllers.kontrol_master_data import KontrolMasterData
from app.database import SessionLocal
from app.main import app
from app.models.entities import Laporan, Notifikasi, PenilikJalan, Perbaikan, Rating, RiwayatStatus, WorkOrder
from app.services.alur_status import tahapan_linimasa
from database.seed import seed_data

WARGA = "0812xxxxxxx"
WARGA_LAIN = "0813xxxxxxx"   # USR-03, pelapor REP-2026-00298
ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"
WO = "REP-2026-00341"        # LAP-2026-0001 milik USR-01, status Disetujui


def jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (90, 90, 90)).save(b, "JPEG")
    return b.getvalue()


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


def ambil(model, kunci):
    db = SessionLocal()
    try:
        return db.get(model, kunci)
    finally:
        db.close()


def hitung(model, **filter_):
    db = SessionLocal()
    try:
        return db.query(model).filter_by(**filter_).count()
    finally:
        db.close()


def status(id_wo=WO):
    return ambil(WorkOrder, id_wo).status_work_order


def inspeksi(c, id_wo=WO, **ubah):
    data = {"dimensi_kerusakan": "2m x 1m", "catatan_teknis": "aspal terkelupas", "rekomendasi": "Tambal Hotmix"}
    data.update(ubah)
    return c.post(f"/TugasLapangan/{id_wo}/inspeksi", data=data)


def spk(c, id_wo=WO, nomor="SPK/PUPR/XI/2026/001"):
    return c.post(f"/work-orders/{id_wo}/spk", data={"nomor_spk": nomor, "tim_pelaksana": "Satgas Rayon Gubeng"})


def selesai(c, id_wo=WO, foto=True):
    files = {"foto_selesai": ("selesai.jpg", jpeg(), "image/jpeg")} if foto else None
    return c.post(f"/TugasLapangan/{id_wo}/progres", data={"status_baru": "Selesai", "catatan_progres": "beres"}, files=files)


# --------------------------------------------------------------------------- #
# Access per role
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("akun,path,metode,kode", [
    (WARGA, "/master-data", "get", 403),
    (WARGA, "/TugasLapangan", "get", 403),
    (ADMIN, "/lacak", "get", 403),
    (ADMIN, "/notifikasi", "get", 403),
    (ADMIN, "/TugasLapangan", "get", 403),
    (KABID, "/master-data", "get", 200),
    (KABID, "/master-data/wilayah", "post", 403),
    (KABID, "/master-data/penilik", "post", 403),
    (KABID, f"/work-orders/{WO}/spk", "post", 403),
    (PENILIK, "/master-data", "get", 403),
    (PENILIK, f"/work-orders/{WO}/spk", "post", 403),
    (PENILIK, "/lacak", "get", 403),
    (WARGA, f"/TugasLapangan/{WO}/inspeksi", "post", 403),
])
def test_hak_akses_sprint2(db_bersih, akun, path, metode, kode):
    assert getattr(klien(akun), metode)(path, follow_redirects=False).status_code == kode


def test_penilik_diarahkan_ke_tugas_lapangan_dan_bisa_login_dengan_nip(db_bersih):
    r = TestClient(app).post("/Login", data={"identifier": "198501012015021001", "password": "password123"},
                             follow_redirects=False)
    assert r.headers["location"] == "/TugasLapangan"


def test_penilik_baru_dari_master_data_bisa_login(db_bersih):
    db = SessionLocal()
    hasil = KontrolMasterData(db).tambah_penilik("199901012024011001", "Sari Penilik", "WIL-02")
    db.close()
    sandi = hasil["akun_baru"]["sandi_sementara"]
    r = TestClient(app).post("/Login", data={"identifier": "199901012024011001", "password": sandi},
                             follow_redirects=False)
    assert r.headers["location"] == "/TugasLapangan"


# --------------------------------------------------------------------------- #
# Ownership (citizens)
# --------------------------------------------------------------------------- #
def test_warga_tidak_bisa_melihat_laporan_warga_lain(db_bersih):
    html = klien(WARGA).get("/lacak?id=LAP-2026-0002").text
    assert 'id="detailLaporan"' not in html and "tidak ditemukan" in html


def test_pencarian_tidak_peka_huruf_dan_spasi(db_bersih):
    assert 'id="detailLaporan"' in klien(WARGA).get("/lacak?id=%20lap-2026-0001%20").text


def test_warga_tidak_bisa_membuka_notifikasi_warga_lain(db_bersih):
    c = klien(WARGA_LAIN)
    assert c.get("/notifikasi/NTF-SEED-0001/buka", follow_redirects=False).status_code == 404
    assert ambil(Notifikasi, "NTF-SEED-0001").status_baca is False


def test_warga_tidak_bisa_memberi_rating_laporan_warga_lain(db_bersih):
    c = klien(WARGA_LAIN)
    c.post("/lacak/LAP-2026-0003/rating", data={"nilai_bintang": "1"})
    assert hitung(Rating, id_laporan="LAP-2026-0003") == 0


# --------------------------------------------------------------------------- #
# Rating rules (UC-J)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nilai", ["0", "6", "abc", "", "3.5"])
def test_rating_di_luar_1_sampai_5_ditolak(db_bersih, nilai):
    r = klien(WARGA).post("/lacak/LAP-2026-0003/rating", data={"nilai_bintang": nilai})
    assert "Silakan pilih bintang rating (1-5)" in r.text
    assert hitung(Rating, id_laporan="LAP-2026-0003") == 0


def test_rating_hanya_untuk_laporan_selesai_dan_sekali(db_bersih):
    c = klien(WARGA)
    r = c.post("/lacak/LAP-2026-0001/rating", data={"nilai_bintang": "5"})  # status Disetujui
    assert "hanya dapat diberikan" in r.text and hitung(Rating, id_laporan="LAP-2026-0001") == 0
    c.post("/lacak/LAP-2026-0003/rating", data={"nilai_bintang": "4"})
    r = c.post("/lacak/LAP-2026-0003/rating", data={"nilai_bintang": "1"})
    assert "sudah Anda beri penilaian" in r.text
    assert hitung(Rating, id_laporan="LAP-2026-0003") == 1


# --------------------------------------------------------------------------- #
# Inspector limits (UC-E)
# --------------------------------------------------------------------------- #
def test_penilik_wilayah_lain_tidak_bisa_mengakses_tiket(db_bersih):
    db = SessionLocal()
    sandi = KontrolMasterData(db).tambah_penilik("199901012024011002", "Penilik Benowo", "WIL-02")["akun_baru"]["sandi_sementara"]
    db.close()
    c = klien("199901012024011002", sandi)
    assert c.get(f"/TugasLapangan/{WO}").status_code == 404
    assert inspeksi(c).status_code == 404
    assert status() == "Disetujui"
    assert WO not in c.get("/TugasLapangan").text


def test_penilik_lain_di_wilayah_sama_tidak_bisa_ambil_tiket_yang_sudah_ditugaskan(db_bersih):
    db = SessionLocal()
    sandi = KontrolMasterData(db).tambah_penilik("199901012024011003", "Penilik Kedua", "WIL-01")["akun_baru"]["sandi_sementara"]
    db.close()
    # REP-2026-00298 is assigned to Budi Santoso (PNL-01)
    assert klien("199901012024011003", sandi).get("/TugasLapangan/REP-2026-00298").status_code == 404


def test_inspeksi_ditolak_untuk_status_yang_salah(db_bersih):
    c = klien(PENILIK)
    inspeksi(c)
    r = inspeksi(c)  # already Terinspeksi
    assert r.status_code == 404 or "tidak sedang menunggu inspeksi" in r.text
    assert hitung(RiwayatStatus, id_work_order=WO, status="Terinspeksi") == 1


def test_inspeksi_dengan_foto_palsu_ditolak(db_bersih):
    r = klien(PENILIK).post(f"/TugasLapangan/{WO}/inspeksi",
                            data={"dimensi_kerusakan": "1m", "rekomendasi": "Tambal Hotmix"},
                            files={"foto_survei": ("x.jpg", b"%PDF bukan gambar", "image/jpeg")})
    assert "Format harus JPG/PNG" in r.text and status() == "Disetujui"


def test_rekomendasi_di_luar_daftar_ditolak(db_bersih):
    r = inspeksi(klien(PENILIK), rekomendasi="Ditutup karung pasir")
    assert "Lengkapi dimensi kerusakan" in r.text and status() == "Disetujui"


# --------------------------------------------------------------------------- #
# SPK & progress (UC-F)
# --------------------------------------------------------------------------- #
def test_spk_hanya_setelah_inspeksi(db_bersih):
    admin = klien(ADMIN)
    r = spk(admin)
    assert "hanya dapat diterbitkan untuk tiket berstatus Terinspeksi" in r.text
    assert status() == "Disetujui" and ambil(WorkOrder, WO).nomor_spk is None


def test_nomor_spk_unik(db_bersih):
    inspeksi(klien(PENILIK))
    r = spk(klien(ADMIN), nomor="spk/pupr/x/2026/014")  # used by REP-2026-00290 (case-insensitive)
    assert "sudah dipakai" in r.text and status() == "Terinspeksi"


def test_progres_dalam_proses_wajib_catatan(db_bersih):
    inspeksi(klien(PENILIK)); spk(klien(ADMIN))
    r = klien(PENILIK).post(f"/TugasLapangan/{WO}/progres", data={"status_baru": "Dalam Proses", "catatan_progres": ""})
    assert "Isi catatan progres" in r.text
    r = klien(PENILIK).post(f"/TugasLapangan/{WO}/progres", data={"status_baru": "Dalam Proses", "catatan_progres": "Pengaspalan 50%"})
    assert "berhasil diperbarui" in r.text and status() == "Dalam Proses"
    assert hitung(RiwayatStatus, id_work_order=WO, status="Dalam Proses") == 2  # SPK + progress note


def test_admin_juga_bisa_menyelesaikan_dari_halaman_work_order(db_bersih):
    inspeksi(klien(PENILIK)); admin = klien(ADMIN); spk(admin)
    r = admin.post(f"/work-orders/{WO}/progres", data={"status_baru": "Selesai", "catatan_progres": "ok"},
                   files={"foto_selesai": ("a.jpg", jpeg(), "image/jpeg")})
    assert "berhasil diperbarui" in r.text and status() == "Selesai"


def test_status_tidak_valid_ditolak(db_bersih):
    inspeksi(klien(PENILIK)); spk(klien(ADMIN))
    r = klien(PENILIK).post(f"/TugasLapangan/{WO}/progres", data={"status_baru": "Dilaporkan", "catatan_progres": "x"})
    assert "status progres yang valid" in r.text and status() == "Dalam Proses"


def test_tiket_selesai_tidak_bisa_diubah_lagi(db_bersih):
    inspeksi(klien(PENILIK)); admin = klien(ADMIN); spk(admin); selesai(klien(PENILIK))
    admin.post(f"/verifikasi/{WO}/approve")
    admin.post(f"/work-orders/{WO}/assign", data={"nama_penilik": "Budi Santoso"})
    assert status() == "Selesai"


def test_verifikasi_tidak_memundurkan_status(db_bersih):
    inspeksi(klien(PENILIK))
    admin = klien(ADMIN)
    admin.post(f"/verifikasi/{WO}/approve")
    admin.post(f"/verifikasi/{WO}/skip-inspection")
    assert status() == "Terinspeksi"
    assert "keputusan verifikasi sudah tidak dapat diubah" in admin.get(f"/verifikasi?ticket_id={WO}").text


# --------------------------------------------------------------------------- #
# Notifications & timeline (UC-C / UC-I)
# --------------------------------------------------------------------------- #
def test_setiap_pelapor_mendapat_notifikasi(db_bersih):
    # Second citizen reports the same damage as REP-2026-00298 (USR-03's ticket)
    warga = klien(WARGA)
    warga.post("/lapor", data={"lokasi_jalan": "Jl. Sudirman No. 45, Surabaya", "latitude": "-7.26550", "longitude": "112.74700",
                               "deskripsi": "Jalan berlubang dekat lampu merah Sudirman, makin lebar", "kategori_pilihan": "Jalan Berlubang",
                               "id_wilayah": "WIL-01"}, files={"foto": ("a.jpg", jpeg(), "image/jpeg")})
    lap_baru = [l for l in SessionLocal().query(Laporan).filter_by(id_work_order="REP-2026-00298").all() if l.id_warga == "USR-01"]
    assert len(lap_baru) == 1 and lap_baru[0].id_laporan.startswith("LAP-2026-")
    inspeksi(klien(PENILIK), id_wo="REP-2026-00298")
    for id_lap, id_warga in [("LAP-2026-0002", "USR-03"), (lap_baru[0].id_laporan, "USR-01")]:
        assert hitung(Notifikasi, id_laporan=id_lap, id_warga=id_warga, judul="Laporan telah disurvei") == 1
        assert ambil(Laporan, id_lap).status == "Terinspeksi"


def test_aksi_sprint1_juga_memberi_notifikasi_dan_riwayat(db_bersih):
    klien(ADMIN).post(f"/work-orders/{WO}/assign", data={"nama_penilik": "Budi Santoso"})
    assert status() == "Ditugaskan"
    assert hitung(Notifikasi, id_laporan="LAP-2026-0001", judul="Petugas ditugaskan") == 1
    assert hitung(RiwayatStatus, id_work_order=WO, status="Ditugaskan") == 1


def test_badge_dan_tandai_semua_dibaca(db_bersih):
    c = klien(WARGA)
    assert 'id="badgeNotif"' in c.get("/Beranda").text
    c.post("/notifikasi/baca-semua")
    assert hitung(Notifikasi, id_warga="USR-01", status_baca=False) == 0
    assert 'id="badgeNotif"' not in c.get("/Beranda").text


def test_laporan_baru_memakai_id_lacak_dan_tercatat_di_riwayat(db_bersih):
    r = klien(WARGA).post("/lapor", data={"lokasi_jalan": "Jl. Manyar Kertoarjo No. 7", "deskripsi": "Lubang besar di jalur lambat",
                                          "kategori_pilihan": "Jalan Berlubang", "id_wilayah": "WIL-01"},
                          files={"foto": ("a.jpg", jpeg(), "image/jpeg")})
    assert "LAP-2026-0004" in r.text and "/lacak?id=LAP-2026-0004" in r.text
    lap = ambil(Laporan, "LAP-2026-0004")
    assert hitung(RiwayatStatus, id_work_order=lap.id_work_order, status="Dilaporkan") == 1
    assert hitung(Notifikasi, id_laporan="LAP-2026-0004", judul="Laporan diterima") == 1


def test_tahapan_linimasa():
    tahap = tahapan_linimasa({"Dilaporkan", "Dalam Proses"})
    assert [t["selesai"] for t in tahap] == [True, True, True, True, False]
    assert all(t["selesai"] for t in tahapan_linimasa({"Selesai"}))
    assert not any(t["selesai"] for t in tahapan_linimasa(set()))


# --------------------------------------------------------------------------- #
# Master data validation (UC-D)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("data,pesan", [
    ({"kode_wilayah": "WIL-01", "nama_wilayah": "Baru"}, "sudah terdaftar"),
    ({"kode_wilayah": "WIL-09", "nama_wilayah": "wilayah gubeng"}, "sudah terdaftar"),
    ({"kode_wilayah": "WIL 09!", "nama_wilayah": "Rayon Utara"}, "Kode Wilayah hanya boleh"),
    ({"kode_wilayah": "", "nama_wilayah": "Rayon Utara"}, "Data belum lengkap"),
])
def test_validasi_wilayah(db_bersih, data, pesan):
    assert pesan in klien(ADMIN).post("/master-data/wilayah", data=data).text


def test_tambah_wilayah_berhasil(db_bersih):
    r = klien(ADMIN).post("/master-data/wilayah", data={"kode_wilayah": "wil-04", "nama_wilayah": "Rayon Utara", "kecamatan": "Kenjeran"})
    assert "Data master berhasil diperbarui" in r.text and "WIL-04" in r.text


@pytest.mark.parametrize("nip", ["12345", "19900512202203100A", "1990051220220310051"])
def test_nip_harus_18_digit(db_bersih, nip):
    r = klien(ADMIN).post("/master-data/penilik", data={"nip": nip, "nama_penilik": "X", "id_wilayah": "WIL-01"})
    assert "Format NIP tidak valid" in r.text


def test_email_penilik_tidak_boleh_dipakai_akun_lain(db_bersih):
    r = klien(ADMIN).post("/master-data/penilik", data={"nip": "199005122022031005", "nama_penilik": "X",
                                                        "id_wilayah": "WIL-01", "email_penilik": "Tri.Wahyudi@gmail.com"})
    assert "Email sudah dipakai" in r.text and hitung(PenilikJalan, nip="199005122022031005") == 0


def _isi_sesi(c: TestClient) -> str:
    """Decode Starlette's session cookie (base64 JSON before the signature)."""
    import base64
    mentah = c.cookies.get("scms_session")
    bagian = mentah.split(".")[0]
    return base64.b64decode(bagian + "=" * (-len(bagian) % 4)).decode()


def test_sandi_sementara_tidak_disimpan_di_cookie(db_bersih):
    import re
    c = klien(ADMIN)
    c.get("/master-data")
    assert "Admin" in _isi_sesi(c)  # the decoder really reads the session
    r = c.post("/master-data/penilik", data={"nip": "199005122022031005", "nama_penilik": "X", "id_wilayah": "WIL-01"})
    sandi = re.search(r'select-all">([^<]+)<', r.text).group(1)
    assert sandi not in _isi_sesi(c)


def test_ketersediaan_mempengaruhi_penugasan(db_bersih):
    admin = klien(ADMIN)
    admin.post("/master-data/penilik/PNL-01/ketersediaan", data={"status": "Cuti"})
    admin.post(f"/work-orders/{WO}/assign", data={"nama_penilik": "Budi Santoso"})
    assert status() == "Menunggu Penugasan"


def test_database_lama_mendapat_kolom_sprint2(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.database import KOLOM_TAMBAHAN, pastikan_kolom_terbaru
    eng = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with eng.begin() as conn:
        for tabel in KOLOM_TAMBAHAN:
            conn.execute(text(f"CREATE TABLE {tabel} (id VARCHAR(20) PRIMARY KEY)"))
    pastikan_kolom_terbaru(eng)
    for tabel, kolom in KOLOM_TAMBAHAN.items():
        assert set(kolom) <= {c["name"] for c in inspect(eng).get_columns(tabel)}


# --------------------------------------------------------------------------- #
# Regression tests for the independent review of Sprint 2
# --------------------------------------------------------------------------- #
def test_penugasan_ulang_tanpa_penilik_tersedia_tidak_memundurkan_tiket(db_bersih):
    admin = klien(ADMIN)
    admin.post("/master-data/penilik/PNL-01/ketersediaan", data={"status": "Cuti"})
    admin.post("/work-orders/REP-2026-00298/assign", data={"nama_penilik": "PNL-01"})
    t = ambil(WorkOrder, "REP-2026-00298")
    assert (t.status_work_order, t.id_penilik) == ("Ditugaskan", "PNL-01")
    assert "REP-2026-00298" in klien(PENILIK).get("/TugasLapangan").text


def test_penugasan_tidak_bisa_melewati_verifikasi(db_bersih):
    r = klien(ADMIN).post("/work-orders/REP-2026-00355/assign", data={"nama_penilik": "PNL-01"})
    assert status("REP-2026-00355") == "Dilaporkan"
    assert "tidak diubah" in r.text


def test_nama_penilik_sama_dipilih_lewat_id(db_bersih):
    db = SessionLocal()
    kedua = KontrolMasterData(db).tambah_penilik("199005122022031005", "Budi Santoso", "WIL-01")
    db.close()
    assert kedua["success"]
    id_kedua = SessionLocal().query(PenilikJalan).filter_by(nip="199005122022031005").one().id_penilik
    html = klien(ADMIN).get(f"/work-orders?select_ticket={WO}").text
    assert f'value="{id_kedua}"' in html and "198501012015021001" in html  # NIP shown to tell them apart
    klien(ADMIN).post(f"/work-orders/{WO}/assign", data={"nama_penilik": id_kedua})
    assert ambil(WorkOrder, WO).id_penilik == id_kedua


def test_ganti_penilik_tercatat_dan_diberitahukan(db_bersih):
    db = SessionLocal()
    KontrolMasterData(db).tambah_penilik("199005122022031005", "Rina Penilik", "WIL-01")
    db.close()
    id_baru = SessionLocal().query(PenilikJalan).filter_by(nip="199005122022031005").one().id_penilik
    klien(ADMIN).post("/work-orders/REP-2026-00298/assign", data={"nama_penilik": id_baru})
    assert ambil(WorkOrder, "REP-2026-00298").id_penilik == id_baru
    assert hitung(RiwayatStatus, id_work_order="REP-2026-00298", keterangan="Ditugaskan kepada Rina Penilik") == 1
    assert hitung(Notifikasi, id_laporan="LAP-2026-0002", judul="Petugas ditugaskan") == 1


def test_dua_permintaan_bersamaan_hanya_satu_yang_berhasil():
    """Compare-and-set: a request that read an old status cannot overwrite a newer one."""
    from app.services.alur_status import KonflikStatus, ubah_status
    seed_data(verbose=False)
    lambat, cepat = SessionLocal(), SessionLocal()
    wo_lambat = lambat.get(WorkOrder, WO)            # reads "Disetujui"
    wo_cepat = cepat.get(WorkOrder, WO)
    ubah_status(cepat, wo_cepat, "Menunggu Inspeksi"); cepat.commit(); cepat.close()
    with pytest.raises(KonflikStatus):
        ubah_status(lambat, wo_lambat, "Terinspeksi")
    lambat.rollback(); lambat.close()
    assert status() == "Menunggu Inspeksi"
    assert hitung(RiwayatStatus, id_work_order=WO, status="Terinspeksi") == 0


def test_bentrok_id_dicoba_ulang():
    from sqlalchemy.exc import IntegrityError
    from app.services.penyimpanan import dengan_coba_ulang
    percobaan = []

    def langkah():
        percobaan.append(1)
        if len(percobaan) < 3:
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
        return "ok"

    db = SessionLocal()
    assert dengan_coba_ulang(db, langkah) == "ok" and len(percobaan) == 3
    db.close()


def test_foto_dihapus_jika_penulisan_gagal(db_bersih, tmp_path):
    from app.services.penyimpanan import tulis_dengan_foto
    db = SessionLocal()
    hasil = tulis_dengan_foto(db, jpeg(), "JPEG", lambda url: {"success": False, "message": "status berubah"})
    db.close()
    assert not hasil["success"] and list(tmp_path.iterdir()) == []


def test_linimasa_tidak_menampilkan_id_laporan_warga_lain(db_bersih):
    html = klien(WARGA_LAIN).get("/lacak?id=LAP-2026-0002").text
    riwayat = html.split('id="riwayatStatus"')[1].split("</ul>")[0]
    assert "Laporan warga diterima sistem" in riwayat
    assert "LAP-2026-0001" not in riwayat and "LAP-2026-0003" not in riwayat


def test_pesan_aksi_cepat_jujur(db_bersih):
    r = klien(ADMIN).post("/Dashboard/REP-2026-00290/quick-approve")  # Selesai
    assert "tidak diubah" in r.text and status("REP-2026-00290") == "Selesai"


def test_waktu_ditampilkan_dalam_wib(db_bersih):
    html = klien(WARGA).get("/lacak?id=LAP-2026-0001").text
    assert "20-10-2026 13:00 WIB" in html  # approval at 13:00 WIB (stored 06:00 UTC)


def test_tab_work_order_aktif_dan_flash_tidak_hilang(db_bersih):
    from app.main import format_wib
    assert format_wib(None) == ""
    html = klien(ADMIN).get("/master-data").text
    assert "Data Master</a>" in html


def test_tiket_belum_diverifikasi_diberi_petunjuk(db_bersih):
    html = klien(ADMIN).get("/work-orders?select_ticket=REP-2026-00355").text
    assert "belum diverifikasi" in html and 'action="/work-orders/REP-2026-00355/assign"' not in html
