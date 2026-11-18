# System Architecture Document (`architecture.md`)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 2.0 (Sprint 1 & Sprint 2 Integrated)  
**Pola Arsitektur:** Layered MVC (Model-View-Controller) + Service-Oriented AI & Atomic Workflow Pipeline  
**Framework Utama:** FastAPI (Python 3.10+), SQLAlchemy ORM, Jinja2 Templates, Pytest-BDD & Selenium WebDriver  

---

## 1. Gambaran Umum Arsitektur (Architectural Overview)

**SCMS-AI** dibangun menggunakan arsitektur **Layered Model-View-Controller (MVC) + Service Layer** di atas *framework* **FastAPI**. Pemisahan tanggung jawab (*Separation of Concerns*) diterapkan secara ketat agar logika bisnis pada setiap *Controller* dan *Service* dapat diuji baik secara langsung (*fast unit/integration tests*) maupun melalui *End-to-End Browser Automation* (**Pytest-BDD + Selenium WebDriver**).

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER (VIEW)                           │
│  • Jinja2 HTML Templates (app/views/templates/*.html + _layout.html)       │
│  • Tailwind CSS (Responsive Government Enterprise UI)                      │
│  • Leaflet.js + OpenStreetMap + Nominatim Geocoding API (Client-Side GIS)  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ HTTP GET / POST + Signed Session Cookie
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                   ROUTING, SESSION & RBAC LAYER                            │
│  • FastAPI Application Router (app/main.py)                                │
│  • Session & Role Guard: app/auth.py (Depends(wajib_peran(...)))           │
│  • Dependency Injection: Database Session (Depends(get_db))                │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ Method Invocation
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                   BUSINESS LOGIC LAYER (11 CONTROLLERS)                    │
│  Sprint 1:                              Sprint 2:                          │
│  • KontrolAutentikasi (UC-K)            • KontrolLacak       (UC-C & UC-J) │
│  • KontrolPelaporan   (UC-A)            • KontrolMasterData  (UC-D)        │
│  • KontrolVerifikasi  (UC-B)            • KontrolInspeksi    (UC-E)        │
│  • KontrolPenugasan   (UC-G)            • KontrolPenanganan  (UC-F)        │
│  • KontrolDashboard   (UC-H)            • KontrolNotifikasi  (UC-I)        │
│                                         • KontrolLaporanKinerja (UC-L)     │
└──────────────────┬──────────────────────────────────┬──────────────────────┘
                   │                                  │
                   ▼                                  ▼
┌──────────────────────────────────────┐   ┌─────────────────────────────────┐
│       DOMAIN SERVICES LAYER          │   │    DATA ACCESS LAYER (MODEL)    │
│  • ai_service.py (Simulasi/YOLOv8/ST)│   │  • SQLAlchemy ORM Entities      │
│  • deduplikasi.py (15m / 50m + NLP)  │   │    (app/models/entities.py)     │
│  • risk_scoring.py (Formula BR-2)    │   │  • Auto-Migration Schema Sync   │
│  • alur_status.py (Atomic CAS + Log) │   │    (pastikan_kolom_terbaru)     │
│  • penyimpanan.py (Retry & File Safe)│   │  • PostgreSQL / SQLite Engine   │
└──────────────────────────────────────┘   └──────────────────┬──────────────┘
                                                              │
                                                              ▼
                                           ┌─────────────────────────────────┐
                                           │  RELATIONAL DATABASE (11 ENT.)  │
                                           │  PostgreSQL / SQLite + seed.py  │
                                           └─────────────────────────────────┘

1. **Presentation Layer (View):** Jinja2 HTML Templates (`app/views/templates/*.html` + `_layout.html`), Tailwind CSS, Leaflet.js + OpenStreetMap + Nominatim Geocoding API.
2. **Routing, Session & RBAC Layer:** FastAPI Application Router (`app/main.py`), Session & Role Guard (`app/auth.py` dengan `Depends(wajib_peran(...))`), Dependency Injection Database Session (`Depends(get_db)`).
3. **Business Logic Layer (11 Controllers):**
   - **Sprint 1:** `KontrolAutentikasi` (UC-K), `KontrolPelaporan` (UC-A), `KontrolVerifikasi` (UC-B), `KontrolPenugasan` (UC-G), `KontrolDashboard` (UC-H).
   - **Sprint 2:** `KontrolLacak` (UC-C & UC-J), `KontrolMasterData` (UC-D), `KontrolInspeksi` (UC-E), `KontrolPenanganan` (UC-F), `KontrolNotifikasi` (UC-I), `KontrolLaporanKinerja` (UC-L).
4. **Domain Services Layer (`app/services/`):**
   - `ai_service.py` (Validasi bytes foto JPEG/PNG <= 10MB, CV Simulasi/YOLOv8 v4 dengan ambang confidence per kelas dari `model_config.json` dan kotak deteksi, NLP Leksikal/Sentence-Transformers).
   - `deduplikasi.py` (Deduplikasi dua tingkat, jarak Haversine terhadap WorkOrder aktif berkategori sama: <= 15 m langsung duplikat tanpa cek deskripsi; > 15–50 m wajib kemiripan deskripsi >= ambang NLP; > 50 m bukan duplikat. Mengembalikan `KandidatDuplikat` dengan `dasar` penggabungan).
   - `risk_scoring.py` (Formula Risk Score BR-2, klasifikasi tingkat prioritas tanpa target waktu (SLA dihapus atas masukan asisten dosen), serta `skor_ambigu()` = Borderline `4.0 <= skor < 6.0` yang dipakai Verifikasi dan Dashboard).
   - `alur_status.py` (Transisi status Compare-and-Set atomik sesuai `TRANSISI_SAH`, pencegahan status mundur, log `RiwayatStatus`, dan `Notifikasi` otomatis — satu per warga pelapor unik per perubahan status. Inspeksi hanya dari `Ditugaskan` / `Menunggu Inspeksi` oleh penilik yang ditugaskan; `Disetujui` wajib ditugaskan dulu).
   - `penyimpanan.py` (Penyimpanan file aman dengan auto-cleanup saat rollback dan auto-retry saat ID bentrok).
5. **Data Access Layer (Model):** SQLAlchemy 2.0 ORM (`app/models/entities.py`) dengan 11 entitas tabel dan auto-migration (`pastikan_kolom_terbaru()` di `app/database.py`).

## 2. Tumpukan Teknologi (Technology Stack)
| Lapisan (Layer) | Teknologi / Pustaka | Peran & Justifikasi Teknis |
| :--- | :--- | :--- |
| **Web Framework & Auth** | FastAPI, Uvicorn, Starlette SessionMiddleware, itsdangerous, passlib[bcrypt] | HTTP routing, form parsing, signed session cookie (`SCMS_SECRET_KEY`), bcrypt password hashing, dan RBAC 4 peran. |
| **Template Engine & UI** | Jinja2 & Tailwind CSS 3.4 (di-build lokal) | Server-Side Rendering dengan shared layout (`_layout.html`) dan badge notifikasi belum dibaca. CSS dibangun dari template oleh `npm run build:css` ke `app/static/css/tailwind.css` (ikut di-commit), tanpa CDN saat aplikasi berjalan. |
| **Geospatial & Mapping** | Leaflet.js 1.9.4, OpenStreetMap, Nominatim API | Visualisasi titik kerusakan jalan, lingkaran heatmap severity, serta Forward & Reverse Geocoding. |
| **ORM & Database** | SQLAlchemy 2.0, PostgreSQL (`psycopg2-binary`), SQLite | Pemetaan 11 tabel ORM, menggunakan SQLite terpisah (`scms_test.db`) saat pengujian otomatis. |
| **AI Pipeline (CV & NLP)** | Pillow, YOLOv8 v4 (`ultralytics` + `model_config.json`), Sentence-Transformers | Validasi foto asli, deteksi kerusakan jalan dengan ambang per kelas & kotak deteksi, dan kemiripan semantik deskripsi. |
| **Automated Testing** | Pytest, Pytest-BDD, Selenium WebDriver, FastAPI TestClient | Menjalankan 592 tes otomatis (63 skenario BDD + 3 E2E Selenium + 526 fast integration tests; 1 uji migrasi PostgreSQL dilewati tanpa `SCMS_TEST_POSTGRES_URL`). |

## 3. Lapisan Model & Entitas (`app/models/entities.py` — 11 Tabel)
1. **`Warga` (`warga`):** `id_warga` (PK), `nik`, `nama_warga`, `email`, `no_hp`, `password_hash`, `alamat_domisili`, `is_active`.
2. **`Admin` (`admin`):** `id_admin` (PK), `nama_admin`, `email_admin`, `password_hash`, `is_kepala_bidang`, `is_active`.
3. **`Wilayah` (`wilayah`):** `id_wilayah` (PK), `nama_wilayah`, `kecamatan`.
4. **`PenilikJalan` (`penilik_jalan`):** `id_penilik` (PK), `id_wilayah` (FK), `nip` (18 digit unik), `nama_penilik`, `email_penilik`, `password_hash`, `status_ketersediaan` (`Tersedia`/`Penuh`/`Cuti`), `is_active`.
5. **`WorkOrder` (`work_order`):** `id_work_order` (PK), `id_admin` (FK), `id_penilik` (FK), `id_wilayah` (FK), `kategori_kerusakan`, `lokasi_jalan`, `latitude`, `longitude`, `severity_score_kasus` (severity yang dipakai formula BR-2: severity AI sampai inspeksi, lalu severity lapangan), `severity_ai` (Sprint 3, FLOAT nullable: severity AI/laporan warga untuk perbandingan; diisi saat laporan pertama masuk, dinaikkan ke nilai tertinggi saat laporan digabung; data lama diisi dari `severity_score_kasus` oleh `pastikan_kolom_terbaru()`), `exposure_count`, `vulnerability_score`, `kelas_jalan` (default `Kolektor`), `risk_score`, `prioritas` (default `Rendah`), `status_work_order`, `sla_rekomendasi` (**usang/deprecated**: SLA dihapus, kolom tidak lagi diisi/dibaca dan dipertahankan hanya agar tidak perlu migrasi), `log_keputusan`, `nomor_spk` (unik), `tim_pelaksana`, `tanggal_ditugaskan`, `tanggal_selesai`, dan Sprint 3: `alasan_tutup`, `ditutup_oleh`, `tanggal_ditutup` (status `Ditutup`); `perlu_tinjauan_manual` (BOOLEAN, Sprint 3 BR-1: diisi dari laporan pembuka tiket; hanya dihapus saat laporan terdeteksi AI digabung selama tiket masih `Dilaporkan`, keputusan tim 5.9 no. 10), dan properti `rekomendasi_tutup_tertunda`.
6. **`Laporan` (`laporan`):** `id_laporan` (PK, format `LAP-YYYY-XXXX`), `id_work_order` (FK), `id_warga` (FK, **nullable sejak Sprint 3**: kosong untuk temuan penilik), `sumber` (`Warga` / `Temuan Penilik`, data lama diisi `Warga`), `id_penilik_pencatat` (penilik pencatat temuan), `id_wilayah` (FK), `deskripsi`, `url_foto`, `lokasi_teks`, `latitude`, `longitude`, `severity_score`, `status`, `tanggal_lapor`. `perlu_tinjauan_manual` (BOOLEAN, Sprint 3 BR-1: foto valid yang tidak dikenali AI). `kotak_deteksi` (TEXT JSON, nullable; kotak deteksi YOLO asli saat laporan dikirim, ditambahkan lewat `pastikan_kolom_terbaru()`; NULL untuk laporan lama & mode simulasi; dibaca lewat properti tervalidasi `daftar_kotak`).
7. **`Inspeksi` (`inspeksi`):** `id_inspeksi` (PK), `id_laporan` (FK), `id_penilik` (FK), `dimensi_kerusakan`, `rekomendasi`, `catatan_teknis`, `hasil_temuan`, `url_foto_temuan`, `tanggal_inspeksi`. Sprint 3 (lewat `pastikan_kolom_terbaru()`): `kategori_terkonfirmasi`, `tingkat_kerusakan` (`Ringan`/`Sedang`/`Berat`/`Sangat Berat`), `severity_lapangan` (3/5/7/9), `rekomendasi_tutup`, `alasan_rekomendasi`, `keputusan_rekomendasi` (`Dikonfirmasi`/`Ditolak`), `diputuskan_oleh`. Properti `WorkOrder.inspeksi_lapangan` / `WorkOrder.severity_lapangan` membaca inspeksi terakhir yang punya tingkat kerusakan.
8. **`Perbaikan` (`perbaikan`):** `id_perbaikan` (PK), `id_work_order` (FK), `status_perbaikan`, `catatan`, `foto_sesudah`, `jadwal_lanjutan` (Sprint 3: tanggal ISO kunjungan lanjutan), `tanggal_selesai`, dan Sprint 3 (lewat `pastikan_kolom_terbaru()`): `perbaikan_sementara`, `status_jadwal` (`Aktif` / `Diganti` / `Tercatat`), `kunjungan_dicatat_pada`, `catatan_kunjungan`, `foto_kunjungan`. Properti `WorkOrder.jadwal_lanjutan_aktif` = satu-satunya jadwal `Aktif`.
9. **`Notifikasi` (`notifikasi`):** `id_notifikasi` (PK), `id_laporan` (FK), `id_warga` (FK), `judul`, `pesan`, `status_baca`, `waktu_kirim`. Kolom `status_kirim`, `jumlah_percobaan` (INTEGER, bawaan 0), dan `waktu_percobaan_terakhir` **usang/deprecated**: fitur Notifikasi Gagal & Kirim Ulang (BR-8) dihapus; kolom tidak lagi ditulis/dibaca aplikasi dan dipertahankan hanya agar database lama tidak perlu migrasi.
10. **`Rating` (`rating`):** `id_rating` (PK), `id_laporan` (FK, Unique), `nilai_bintang` (1-5), `komentar`, `tanggal_rating`. Aturan aplikasi: satu rating per (warga, tiket) — dicek di `KontrolLacak.simpan_rating()` lintas laporan warga yang digabung ke tiket yang sama.
11. **`RiwayatStatus` (`riwayat_status`):** `id_riwayat` (PK), `id_work_order` (FK), `status`, `keterangan`, `waktu`.

## 4. Peta Routing & Endpoint HTTP (`app/main.py`)
| Method | URL Endpoint | Peran Diizinkan | Controller | Use Case |
| :--- | :--- | :--- | :--- | :--- |
| `GET/POST` | `/Login`, `/Register`, `/Logout` | Publik | `KontrolAutentikasi` | `UC-K` |
| `GET` | `/Beranda` | Warga | Query `Laporan` | `UC-A/C` |
| `GET/POST` | `/lapor`, `/api/analisis-foto` | Warga | `KontrolPelaporan`, `AIService` | `UC-A` |
| `GET` | `/lacak` | Warga | `KontrolLacak.cari_laporan_warga()` | `UC-C` |
| `POST` | `/lacak/{id_laporan}/rating` | Warga | `KontrolLacak.simpan_rating()` | `UC-J` |
| `GET/POST` | `/notifikasi`, `/notifikasi/{id}/buka`, `/notifikasi/baca-semua` | Warga | `KontrolNotifikasi` | `UC-I` |
| `GET/POST` | `/Dashboard`, `/Dashboard/{id}/quick-approve` | Staf / Admin (quick-approve hanya tiket `Dilaporkan` berskor jelas) | `KontrolDashboard`, `KontrolVerifikasi` | `UC-H` |
| `GET/POST` | `/verifikasi`, `/verifikasi/{id}/approve\|inspect\|skip-inspection` | Admin, Kabid | `KontrolVerifikasi` | `UC-B` |
| `GET/POST` | `/work-orders`, `/work-orders/{id}/assign` | Staf / Admin | `KontrolPenugasan` | `UC-G` |
| `POST` | `/work-orders/{id}/spk`, `/work-orders/{id}/progres` | Admin | `KontrolPenanganan` | `UC-F` |
| `GET/POST` | `/TugasLapangan`, `/TugasLapangan/{id}`, `/TugasLapangan/{id}/inspeksi\|progres` | Penilik Jalan (hanya tiket yang ditugaskan kepadanya) | `KontrolInspeksi`, `KontrolPenanganan` | `UC-E, UC-F` |
| `POST` | `/TugasLapangan/{id}/kunjungan`, `/work-orders/{id}/kunjungan` | Penilik Jalan (tiket yang ditugaskan kepadanya) / Admin (PPK) | `KontrolPenanganan.catat_kunjungan_lanjutan` | Sprint 3 CO-3: catat kunjungan lanjutan (perbaikan sementara dijadwalkan lewat `.../progres`) |
| `POST` | `/TugasLapangan/{id}/temuan` | Penilik Jalan (tiket aktif yang ditugaskan kepadanya) | `KontrolInspeksi.catat_temuan` → `KontrolPelaporan.kirim_laporan` | Sprint 3 CO-2: temuan baru (tiket baru "Temuan Penilik" atau digabung BR-3) |
| `POST` | `/verifikasi/{id}/reject` | Admin (PPK) | `KontrolVerifikasi.tolak_tiket` | Sprint 3: tolak tiket `Dilaporkan` dengan alasan wajib → `Ditutup` |
| `POST` | `/work-orders/{id}/rekomendasi-tutup/konfirmasi\|tolak` | Admin (PPK) | `KontrolPenanganan.konfirmasi_tutup` / `tolak_rekomendasi` | Sprint 3: keputusan atas rekomendasi tutup penilik |
| `GET/POST` | `/master-data`, `/master-data/wilayah\|penilik` | Admin, Kabid (POST hanya Admin) | `KontrolMasterData` | `UC-D` |
| `POST` | `/master-data/penilik/{id}/ketersediaan` | Admin | `KontrolMasterData.ubah_ketersediaan()` (404 penilik tidak ada, 400 status tidak valid) | `UC-D` |
| `GET` | `/laporan-kinerja`, `/laporan-kinerja/unduh?jenis=wilayah\|tiket` | Admin, Kabid | `KontrolLaporanKinerja` | `UC-L` |

## 5. Integrasi Model AI YOLOv8 v4 (`app/services/ai_service.py` — `VisiYolo`)
1. **Konfigurasi Inferensi:** Bobot `SCMS_YOLO_WEIGHTS` (mis. `models/scms_v4/yolov8_infra_best.pt`) dibaca bersama `model_config.json` di folder yang sama (atau `SCMS_YOLO_CONFIG`) melalui `baca_konfigurasi_model()`. Kunci yang dipakai: `conf_per_class`, `infer_imgsz` (800), `nms_iou` (0,6), `agnostic_nms` (mati), dan `versi`. Tanpa file konfigurasi, dipakai satu ambang `conf_minimum` (0,35).
2. **Ambang Confidence per Kelas:** Nama kelas model dipetakan ke kategori SCMS (`petakan_kelas()`), lalu tiap deteksi disaring dengan `ambang(kategori)`: **Jalan Berlubang 0,26** dan **Retak Permukaan 0,20**. `predict()` dijalankan dengan ambang terendah, sehingga penyaringan per kelas terjadi setelahnya. Model v4 hanya mengenali dua kelas; Jalan Amblas tetap dipilih oleh warga/petugas.
3. **Kotak Deteksi:** Foto diputar tegak sesuai EXIF (`ImageOps.exif_transpose`) sebelum inferensi. Setiap deteksi yang lolos ambang dikembalikan sebagai kotak ternormalisasi (`kategori`, `confidence` %, `x1`, `y1`, `x2`, `y2` dalam 0–1), maksimal 20 kotak terurut confidence, melalui field `kotak` pada respons `/api/analisis-foto`.
4. **Severity AI:** Kategori terpilih adalah deteksi dengan skor `conf × (0,5 + luas)` tertinggi; `severity = min(10, BASE_SEVERITY[kategori] + 2,5 × cakupan × conf)`.
5. **Aturan Severity saat Kategori Diganti (PRD BR-2):** `severity_laporan()` di `KontrolPelaporan` memakai severity AI hanya jika `kategori_pilihan` warga sama dengan rekomendasi AI. Jika berbeda, dipakai nilai dasar `VisiYolo.BASE_SEVERITY` (Jalan Berlubang `7.0`, Jalan Amblas `7.5`, Retak Permukaan `4.5`) yang kemudian ditinjau petugas. Nilai dasar ini juga diekspos ke template sebagai global Jinja2 `severity_dasar`.

## 5a. Hitung Ulang Risk Score Setelah Inspeksi (Sprint 3 / CO-1 — PRD 5.3 BR-2)
1. **Form:** `POST /TugasLapangan/{id}/inspeksi` menerima `kategori_terkonfirmasi` (kosong = kategori tiket; selain `KATEGORI_VALID` ditolak "Pilih kategori kerusakan yang valid") dan `tingkat_kerusakan` (**wajib**; kosong/tidak dikenal ditolak "Pilih tingkat kerusakan hasil inspeksi lapangan" tanpa menyimpan apa pun). Pemetaan ada di `risk_scoring.TINGKAT_KERUSAKAN` (`Ringan 3`, `Sedang 5`, `Berat 7`, `Sangat Berat 9`) beserta `KETERANGAN_TINGKAT` untuk form.
2. **Alur (`KontrolInspeksi.simpan_inspeksi()`, satu transaksi lewat `tulis_dengan_foto`):** simpan `severity_ai` bila masih kosong → ganti `kategori_kerusakan` (bila dikoreksi) → `severity_score_kasus = severity_lapangan` → `risk_scoring.terapkan_ke_work_order()` (formula BR-2 yang sama; E, V, C tidak berubah) → `Inspeksi` dengan tiga kolom baru → `ubah_status(..., Terinspeksi, keterangan)`. Keterangan riwayat memuat "Risk Score diperbarui X → Y berdasarkan inspeksi" (dan "kategori dikoreksi A → B" bila ada) pada **entri transisi `Terinspeksi` yang sudah ada**, sehingga tidak ada transisi atau baris status baru.
3. **Hitung ulang berikutnya:** `KontrolPelaporan` saat menggabungkan laporan (BR-3) menaikkan `severity_ai` ke nilai tertinggi, tetapi hanya mengubah `severity_score_kasus` bila tiket **belum** punya severity lapangan. Setelah inspeksi, penggabungan hanya menaikkan exposure, dan Risk Score tetap dihitung dengan severity lapangan.
4. **Tampilan:** macro `severity_ai_lapangan(wo)` (`#severityAi`, `#severityLapangan`, atribut `data-nilai`) di Verifikasi, panel Work Order, dan Tugas Lapangan detail. Baris tabel Dashboard memiliki atribut `data-tiket` untuk pengujian warna lencana.
5. **Pengujian:** `tests/test_sprint3_risiko.py` (21 uji cepat) dan `tests/step_definitions/test_uc_e_hitung_ulang_risiko.py` (3 skenario `@sprint3`, di-bind satu per satu dengan `@scenario`; Scenario Outline rekomendasi tutup menunggu Bagian 1B).

## 5b. Status Akhir "Ditutup" & Tinjauan Manual (Sprint 3 Bagian 1B — PRD 5.3 BR-1/BR-4/BR-5)
1. **Status (`alur_status.py`):** `DITUTUP = "Ditutup"`, `STATUS_FINAL = (SELESAI, DITUTUP)`, `ALASAN_TUTUP` (satu sumber: Tidak ditemukan kerusakan, Laporan tidak valid, Sudah diperbaiki pihak lain, Di luar kewenangan DPUPR). `TRANSISI_SAH` ditambah `Dilaporkan -> Ditutup` dan `Terinspeksi -> Ditutup`; `Ditutup -> (tidak ada)`. `tutup_tiket(db, wo, alasan, aktor)` memvalidasi alasan (`AlasanTutupTidakSah`), lalu memanggil `ubah_status()` (compare-and-set, riwayat "Ditutup: <alasan>", satu notifikasi per warga unik berjudul "Laporan ditutup" yang memuat alasan) dan mengisi `alasan_tutup`, `ditutup_oleh`, `tanggal_ditutup`.
2. **Pintu (a) Verifikasi:** `POST /verifikasi/{id}/reject` (Admin; Kabid/Penilik/Warga 403) → `KontrolVerifikasi.tolak_tiket()`. `alasan_ditolak()` kini mengenal `AKSI_TOLAK` (boleh untuk semua tiket `Dilaporkan`) dan menolak aksi yang tidak dikenal. Alasan kosong/di luar daftar → "Pilih alasan penutupan tiket" (redirect dengan `jenis=gagal`).
3. **Pintu (b) Inspeksi:** `rekomendasi = "Rekomendasikan Tutup"` + `alasan_rekomendasi` wajib; dimensi tidak wajib; tingkat kerusakan boleh kosong hanya untuk "Tidak ditemukan kerusakan" (Risk Score tidak dihitung ulang). Tiket menjadi `Terinspeksi` dengan rekomendasi tertunda. `POST /work-orders/{id}/rekomendasi-tutup/konfirmasi` (→ `Ditutup`) dan `.../tolak` (tetap `Terinspeksi`, riwayat "Rekomendasi tutup ditolak Admin") di `KontrolPenanganan`. Selama tertunda, `terbitkan_spk()` menolak dengan `PESAN_REKOMENDASI_TERTUNDA` dan form SPK tidak dirender.
4. **Ditutup di mana-mana:** Dashboard (`ringkasan_kpi`: tidak aktif, tidak Selesai, `ditutup` terpisah; persentase selesai dari tiket non-Ditutup; marker `WARNA_DITUTUP`), Work Order (`ringkasan_kpi.ditutup`), Tugas Lapangan (masuk riwayat, bukan tugas aktif), beban penilik Master Data, deduplikasi BR-3 (`STATUS_TIDAK_AKTIF`), rating (`PESAN_RATING_DITUTUP`), Lacak (linimasa berakhir "Ditutup: <alasan>"), Laporan Kinerja (dikeluarkan dari total, tingkat penyelesaian, durasi, rekap prioritas; `ditutup.per_alasan`; kolom CSV "Ditutup (tidak dihitung)").
5. **Tinjauan manual (BR-1):** `HasilVisi.tinjauan_manual`; `VisiSimulasi` (kata kunci bukan-jalan atau `tanpa_deteksi`) dan `VisiYolo` (tidak ada deteksi di atas ambang) mengembalikan `hasil_tinjauan_manual()` alih-alih menolak. `KontrolPelaporan.kirim_laporan()` menerima laporan, mewajibkan kategori pilihan warga (`PESAN_PILIH_KATEGORI`), memakai nilai dasar kategori, dan menyimpan `laporan.perlu_tinjauan_manual` serta `work_order.perlu_tinjauan_manual` untuk tiket baru. Saat penggabungan (BR-3), laporan yang terdeteksi AI menghapus penanda tiket **hanya** bila tiket masih `Dilaporkan`, dengan riwayat "Tinjauan manual tidak lagi diperlukan: laporan <ID> terdeteksi AI"; setelah verifikasi penanda tetap (keputusan tim 5.9 no. 10). `/api/analisis-foto` mengembalikan `tinjauan_manual: true`. `tiket_ambigu()` = skor Borderline **atau** `perlu_tinjauan_manual`, sehingga "Setujui Tiket" dan Aksi Cepat Dashboard ditolak.
6. **Pengujian:** `tests/test_sprint3_tutup.py` (53 uji cepat), `test_uc_b_tutup_tiket.py` (4 skenario), `test_uc_a_tinjauan_manual.py` (4 skenario), Scenario Outline di `test_uc_e_hitung_ulang_risiko.py` (2 contoh), dan skenario UC-A yang direvisi di `test_uc_a.py`.

## 5c. Temuan Baru oleh Penilik Jalan (Sprint 3 Bagian 2A / CO-2 — PRD 5.3, keputusan tim 5.9 no. 3, 11, 12)
1. **Skema (`pastikan_kolom_terbaru()` → `izinkan_id_warga_kosong()`):** kolom baru `laporan.sumber` dan `laporan.id_penilik_pencatat`; `laporan.id_warga` menjadi nullable secara idempoten. PostgreSQL: `ALTER TABLE laporan ALTER COLUMN id_warga DROP NOT NULL`. SQLite (tidak bisa mengubah NOT NULL): tabel dibangun ulang dalam satu transaksi — `CREATE TABLE` asli (hanya "NOT NULL" pada `id_warga` yang dihapus, sehingga kolom lain, default, dan FOREIGN KEY tetap) dibuat sebagai `laporan__baru`, semua baris disalin per kolom, jumlah baris dibandingkan, tabel lama di-drop, tabel baru di-rename, indeks dibuat ulang; galat apa pun me-rollback transaksi. Aman karena SCMS tidak menyalakan `PRAGMA foreign_keys`. Uji PostgreSQL sungguhan: `SCMS_TEST_POSTGRES_URL=postgresql://... pytest tests/test_sprint3_temuan.py -k postgresql` (berjalan di skema sementara `scms_uji_migrasi`, lalu dihapus).
2. **Alur:** `POST /TugasLapangan/{id}/temuan` (Penilik Jalan; selain itu 403; bukan tugasnya 404) → `KontrolInspeksi.catat_temuan()` memeriksa penugasan, status (`STATUS_BOLEH_TEMUAN`: Menunggu Inspeksi, Ditugaskan, Terinspeksi, Dalam Proses), foto wajib, kategori, dan titik, lalu memanggil **`KontrolPelaporan.kirim_laporan()` yang sama dengan laporan warga** (`sumber="Temuan Penilik"`, `id_warga=None`, `id_penilik_pencatat`, `id_wilayah` tiket asal). Jadi validasi BR-1, analisis AI (kotak deteksi / tinjauan manual), Risk Score BR-2, dan deduplikasi BR-3 tidak diduplikasi. Hook `saat_tersimpan(laporan, tiket)` mencatat "Penilik mencatat temuan baru <tiket> / <laporan>" di riwayat tiket asal **dalam transaksi yang sama**, tanpa mengubah statusnya.
3. **Exposure & notifikasi:** temuan yang digabung tidak menaikkan `exposure_count`; tiket temuan murni memakai E = 1 (keputusan 5.9 no. 11). `kirim_notifikasi()` dan `laporan_per_warga()` melewati laporan tanpa warga, sehingga tiket temuan murni tidak pernah mengirim notifikasi; warga yang kemudian digabung ke tiket temuan menerima "Laporan digabungkan" dan notifikasi status berikutnya seperti biasa.
4. **Aman untuk `id_warga` kosong:** Lacak dan rating selalu memfilter laporan milik warga yang login (laporan temuan dianggap "tidak ditemukan"); Laporan Kinerja menghitung rating dari join `Rating` (laporan temuan tidak punya rating); Verifikasi, Dashboard, Work Order, dan CSV tidak membaca data warga. Pelapor ditampilkan lewat `Laporan.label_pelapor` ("Temuan Penilik: <nama penilik>" atau nama warga); `WorkOrder.laporan_pembuka` / `dari_temuan` memberi label sumber tiket.
5. **Peta:** reverse geocoding Nominatim dipindahkan ke `/static/js/peta_lokasi.js` (`SCMS_PETA.cariAlamat`) dan dipakai bersama oleh wizard Buat Laporan dan form temuan.
6. **Pengujian:** `tests/test_sprint3_temuan.py` (31 uji cepat, 1 di antaranya PostgreSQL opsional) dan `tests/step_definitions/test_uc_e_temuan_baru.py` (4 skenario).

## 5d. Perbaikan Sementara & Kunjungan Lanjutan (Sprint 3 Bagian 2B / CO-3 — PRD 5.3, keputusan tim 5.9 no. 7)
Jadwal kunjungan lanjutan adalah **rencana kerja, bukan tenggat** (revisi asisten dosen: tanpa SLA); tidak ada istilah tenggat/terlambat di mana pun.
1. **Menjadwalkan:** `KontrolPenanganan.perbarui_progres(..., perbaikan_sementara, jadwal_lanjutan)` dari `POST /TugasLapangan/{id}/progres` (penilik yang ditugaskan) dan `POST /work-orders/{id}/progres` (Admin). `baca_jadwal_lanjutan()` mewajibkan tanggal ISO **setelah hari ini (WIB)**; perbaikan sementara selalu `Dalam Proses`. Baris `Perbaikan` baru berstatus jadwal `Aktif`; jadwal aktif lama menjadi `Diganti`, sehingga hanya ada satu jadwal aktif. Riwayat: "Perbaikan sementara: <catatan>; Kunjungan lanjutan dijadwalkan <tgl>" atau "... dijadwalkan ulang ke <tgl> (sebelumnya <tgl>)".
2. **Mencatat kunjungan:** `catat_kunjungan_lanjutan()` dari `POST /TugasLapangan/{id}/kunjungan` dan `POST /work-orders/{id}/kunjungan` (Admin): catatan wajib, foto opsional (BR-1), **boleh sebelum tanggal rencananya**; jadwal menjadi `Tercatat` dan tidak aktif lagi. Perbaikan sementara dapat dijadwalkan lagi bila memang perlu.
3. **Blok Selesai:** selama `jadwal_lanjutan_aktif` ada, `perbarui_progres(SELESAI)` menolak dengan "Catat kunjungan lanjutan terlebih dahulu sebelum menyelesaikan tiket" (dicek ulang di dalam transaksi), dan form menonaktifkan opsi Selesai dengan keterangan.
4. **Tanpa transisi baru:** semua entri ditulis lewat `ubah_status(DALAM_PROSES, ..., catat_walau_sama=True)` (riwayat + notifikasi warga), status tetap `Dalam Proses`.
5. **Tampilan:** macro `_macro_lanjutan.html` dipakai form penilik dan Admin; jadwal aktif tampil di daftar & detail Tugas Lapangan, panel Work Order, dan linimasa Lacak (tahap tambahan "Kunjungan lanjutan dijadwalkan <tgl>" setelah "Perbaikan Berjalan"). Laporan Kinerja: tahap saat ini tiket aktif = "Perbaikan (menunggu kunjungan lanjutan)"; durasi tahap Perbaikan tetap `Dalam Proses` → `Selesai`.
6. **Pengujian:** `tests/test_sprint3_kunjungan.py` (32 uji cepat) dan `tests/step_definitions/test_uc_f_kunjungan_lanjutan.py` (5 skenario).

## 5e. Notifikasi Gagal & Kirim Ulang — dihapus (BR-8)
Fitur ini sempat diimplementasikan di Sprint 3 Bagian 3 lalu **dihapus seluruhnya atas keputusan tim**: rute `/notifikasi-gagal` dan `.../kirim-ulang`, `app/services/pengiriman_notifikasi.py` (kanal luar tersimulasi + percobaan ulang), `SCMS_NOTIF_TINGKAT_GAGAL`, tab navigasi staf beserta badge, dan seed notifikasi `Gagal`. `kirim_notifikasi()` di `alur_status.py` kini hanya menyimpan notifikasi in-app; perilaku UC-I lain (daftar, tandai dibaca, polling badge/toast) tidak berubah. Kolom terkait dibiarkan sebagai kolom usang (lihat entitas `Notifikasi`). Penjaga regresi: `tests/test_tanpa_notifikasi_gagal.py` (12 uji cepat).

## 6. Modul Laporan Kinerja Infrastruktur (UC-L — `app/controllers/kontrol_laporan_kinerja.py`)
Revisi asisten dosen: konsep SLA dihapus (perbaikan jalan melewati birokrasi, target 24 jam s.d. 7x24 jam tidak realistis). Laporan ini mengukur durasi nyata tiap tahap, bukan kepatuhan pada target.
1. **Rekap (`rekap()`):** Memfilter tiket berdasarkan tanggal diterima (WIB, inklusif) dan wilayah, lalu menghasilkan KPI total, rekap per wilayah (wilayah tanpa tiket tetap tampil dengan nilai nol), rekap per prioritas (`Urgent`, `Tinggi`, `Borderline`, `Rendah`), daftar tiket aktif terurut umur, dan detail tiket terurut Risk Score tertinggi.
2. **Waktu Mulai & Penyelesaian:** Tiket dimulai pada entri pertama `RiwayatStatus` (cadangan: `tanggal_lapor` laporan warga paling awal) dan selesai pada entri `Selesai` pertama (cadangan: `tanggal_selesai`). Semua durasi dalam hari.
3. **Durasi per Tahap (`durasi_tahap()`, konstanta `TAHAP`):** Verifikasi (masuk → `Disetujui`/`Menunggu Inspeksi`), Penugasan (keputusan verifikasi → `Ditugaskan`), Inspeksi Lapangan (`Ditugaskan` → `Terinspeksi`), Penerbitan SPK (`Terinspeksi` → `Dalam Proses`), Perbaikan (`Dalam Proses` → `Selesai`), memakai waktu pertama kali tiap status dicapai. Tahap dihitung untuk sebuah tiket hanya bila kedua ujungnya tercapai dan urutannya benar; jalur inspeksi tambahan (`Menunggu Inspeksi` → `Terinspeksi`) tidak menghitung Penugasan dan Inspeksi Lapangan. Rata-rata ditampilkan keseluruhan dan per prioritas beserta jumlah tiket yang melewati tahap.
   **Umur Tiket Aktif:** hari sejak tiket diterima; `tahap_saat_ini` dipetakan dari status (`TAHAP_SAAT_INI`), dan `lama_di_tahap_hari` dihitung sejak entri riwayat terakhir. Rata-rata rating dihitung dari satu rating per warga unik per tiket (data lama ganda: rating pertama).
4. **Validasi & Pesan:** Format tanggal salah atau tanggal mulai setelah tanggal akhir ditolak dengan HTTP 400; periode tanpa tiket menampilkan `"Tidak ada data kinerja pada periode yang dipilih"`.
5. **Ekspor CSV:** `csv_per_wilayah()` (rata-rata durasi per tahap, rata-rata umur aktif, umur tertua) dan `csv_per_tiket()` (tahap saat ini, durasi per tahap, umur tiket aktif), tanpa kolom SLA, dengan nama berkas `laporan_kinerja_{jenis}_{periode}.csv`. Setiap sel teks melewati `aman_untuk_spreadsheet()` (teks berawalan `=`, `+`, `-`, `@`, tab, atau CR diberi awalan `'`) agar input warga tidak dieksekusi sebagai formula. Versi PDF dibuat lewat fitur cetak browser.
6. **Pengujian:** `tests/test_laporan_kinerja.py` (33 uji cepat: hak akses, durasi per tahap termasuk jalur inspeksi tambahan dan tahap yang belum dilalui, umur tiket aktif, filter, ekspor CSV, proteksi formula), `tests/test_tanpa_sla.py` (25 uji regresi penghapusan SLA), dan `uc_l_laporan_kinerja.feature` (2 skenario BDD).