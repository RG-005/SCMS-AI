# SCMS-AI Dinas PUPR Kota Surabaya
> **Smart Infrastructure Monitoring & Dispatch System (SCMS-AI)**  
> Sistem Triage, Validasi AI, dan Prioritisasi Laporan Kerusakan Jalan Berbasis Artificial Intelligence — Dinas Sumber Daya Air dan Bina Marga (DSDABM) Kota Surabaya.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-red?logo=sqlite&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-17%20BDD%20%2B%203%20E2E%20%2B%2064%20unit-success?logo=pytest&logoColor=white)
![Leaflet GIS](https://img.shields.io/badge/Leaflet.js-OpenStreetMap-199900?logo=openstreetmap&logoColor=white)

---

## 👥 Tim Pengembang (Kelompok 7 — Kelas I3)

| Nama Lengkap | Peran & Tanggung Jawab Modul (Sprint 1) |
| :--- | :--- |
| **Rizaldi Rizki Saputra** | Arsitektur Basis Data (10 Tabel PDM & Seeder), Autentikasi Multi-Aktor (`UC-K`), Pelaporan Kerusakan 4 Langkah & AI Pipeline (`UC-A`), serta Penugasan Penilik Jalan & SPK (`UC-G`). |
| **Alfarrel Yuri Ramadhani** | Verifikasi Laporan & Evaluasi Skor Risiko Ambigu (`UC-B`), serta Dashboard Prioritas Infrastruktur & Peta Geospasial GIS (`UC-H`). |

---

## 📋 Latar Belakang & Deskripsi Proyek
**SCMS-AI** dirancang untuk mentransformasi proses penanganan pengaduan kerusakan jalan dan infrastruktur di Kota Surabaya dari yang semula bersifat manual-reaktif menjadi terotomatisasi dan berbasis tingkat risiko (*Risk-Based Triage*).

Sistem ini mengintegrasikan tiga pilar kecerdasan utama:
1. **Computer Vision (YOLOv8, opsional):** Memvalidasi bukti foto warga (menolak foto non-infrastruktur) serta mengekstraksi rekomendasi kategori kerusakan dan *Severity Score* awal. Secara bawaan berjalan dalam **mode simulasi** (lihat [Mode AI](#-mode-ai)).
2. **Natural Language Processing (Sentence-Transformers, opsional):** Mendeteksi duplikasi laporan secara spasial-semantik (radius 50 m + kemiripan deskripsi), menggabungkan laporan serupa ke tiket *Work Order* aktif, dan menaikkan nilai *Exposure Count* (+1). Bawaan: kemiripan leksikal tanpa model.
3. **Multi-Factor Risk Scoring Engine & GIS (PRD BR-2):** Menghitung skor prioritas penanganan (skala 0–10) di `app/services/risk_scoring.py`:
   $$\text{Risk Score} = \text{clip}\big(0.50\,S + 0.45\ln(E+1) + 0.15\,V + 0.25\,C,\ 0,\ 10\big)$$
   dengan *S* = severity, *E* = jumlah pelapor, *V* = kerentanan lokasi, *C* = kritikalitas kelas jalan. Hasilnya menentukan prioritas & SLA (≥ 8 Urgent/24 jam, 6–8 Tinggi/3×24 jam, 4–6 Borderline, < 4 Rendah/7×24 jam) dan divisualisasikan pada peta Leaflet.js & OpenStreetMap.

---

## 🚀 Cakupan Fitur Utama (Sprint 1 — 17 Skenario BDD)

1. **UC-K — Login / Autentikasi Pengguna (5 Skenario BDD):**
   * Autentikasi terpadu untuk 4 aktor: **Warga** (via Nomor HP), **Admin**, **Penilik Jalan**, dan **Kepala Bidang** (via Email Instansi).
   * Validasi kredensial salah dan pencegahan pengiriman form kosong.
2. **UC-A — Membuat Laporan Kerusakan 4 Langkah (4 Skenario BDD):**
   * **Step 1 (Capture):** Validasi format berkas (`JPG/PNG`) dan ukuran maksimum ($\le 10\text{ MB}$), serta deteksi objek jalan rusak menggunakan AI Computer Vision.
   * **Step 2 (Location):** Pencarian alamat akurat (*Nominatim Geocoding*), deteksi GPS otomatis, dan penempatan pin peta interaktif.
   * **Step 3 (Detail):** Rekomendasi kategori otomatis dari AI dan validasi deskripsi minimal 10 karakter.
   * **Step 4 (Review & Deduplikasi):** Tinjauan akhir dan penggabungan otomatis (*merge*) jika terdeteksi laporan aktif serupa di titik lokasi yang sama.
3. **UC-B — Memverifikasi Laporan Kerusakan (4 Skenario BDD):**
   * Menampilkan antrean tiket terurut dari *Risk Score* tertinggi ke terendah.
   * Otorisasi persetujuan tiket (`Disetujui`) untuk skor risiko yang jelas.
   * Deteksi otomatis skor risiko *borderline/ambigu* ($4.0 \le \text{Risk Score} \le 6.0$) dengan opsi **Tugaskan Inspeksi Tambahan** (`Menunggu Inspeksi`) atau **Lanjutkan Tanpa Inspeksi** disertai pencatatan log audit keputusan manual.
4. **UC-G — Menugaskan Penilik Jalan (2 Skenario BDD):**
   * Menampilkan rekomendasi SLA penanganan (misal: 24 jam untuk status *Urgent*) dan daftar Penilik Jalan yang tersedia sesuai wilayah rayon.
   * Penanganan otomatis kondisi ketika seluruh Penilik Jalan di wilayah terkait sedang penuh (`Menunggu Penugasan`).
5. **UC-H — Melihat Dashboard Prioritas Infrastruktur (2 Skenario BDD):**
   * Kartu metrik KPI dinamis, ringkasan zona risiko wilayah, dan peta sebaran kerusakan jalan dengan gradasi warna tingkat keparahan (*severity*).
   * Filter multi-parameter berdasarkan Wilayah, Status, dan Kategori dengan penanganan kondisi hasil filter kosong.

---

## 📂 Struktur Direktori Proyek

```text
scms-ai-pupr/
├── app/
│   ├── controllers/                 # Logika bisnis & orkestrasi per Use Case
│   │   ├── kontrol_autentikasi.py   # Controller UC-K (Login Multi-Aktor)
│   │   ├── kontrol_pelaporan.py     # Controller UC-A (Wizard 4-Step & AI CV/NLP)
│   │   ├── kontrol_verifikasi.py    # Controller UC-B (Verifikasi & Skor Ambigu)
│   │   ├── kontrol_penugasan.py     # Controller UC-G (Penugasan Penilik & SLA)
│   │   └── kontrol_dashboard.py     # Controller UC-H (Dashboard Prioritas & GIS)
│   ├── models/
│   │   └── entities.py              # Definisi 10 Tabel Physical Data Model (SQLAlchemy)
│   ├── services/
│   │   ├── ai_service.py            # Validasi foto, Computer Vision & NLP (simulasi / YOLOv8 / ST)
│   │   ├── deduplikasi.py           # Aturan deduplikasi spasial-semantik (BR-3)
│   │   └── risk_scoring.py          # Formula Risk Score, prioritas & SLA (BR-2)
│   ├── auth.py                      # Sesi login & pembatasan akses per peran
│   ├── static/
│   │   └── images/                  # Aset visual dan logo instansi
│   ├── views/templates/             # Antarmuka pengguna (Jinja2, TailwindCSS, Leaflet.js)
│   │   ├── login.html
│   │   ├── buat_laporan.html
│   │   ├── verifikasi_detail.html
│   │   ├── work_order_list.html
│   │   └── dashboard_prioritas.html
│   ├── database.py                  # Konfigurasi engine & session SQLite/SQLAlchemy
│   └── main.py                      # Entrypoint aplikasi & routing FastAPI terintegrasi
├── database/
│   └── seed.py                      # Seeder data awal sesuai skenario BDD & Mockup
├── docs/
│   ├── activity_diagrams/           # File PlantUML (.puml) Activity Diagram 5 Use Case
│   └── sequence_diagrams/           # File PlantUML (.puml) Sequence Diagram 5 Use Case
├── tests/
│   ├── features/                    # Spesifikasi skenario Gherkin (.feature)
│   ├── step_definitions/            # Pengujian otomatis Pytest-BDD (17 Skenario) + 3 E2E Selenium
│   └── test_keamanan_dan_logika.py  # Uji cepat tanpa browser: hak akses, unggah foto, deduplikasi, risk score
├── pytest.ini                       # Konfigurasi pytest runner
├── requirements.txt                 # Daftar dependensi paket Python
├── requirements-ai.txt              # (Opsional) model AI sungguhan: ultralytics, sentence-transformers
└── README.md                        # Dokumentasi utama proyek
```

---

## ⚙️ Cara Menjalankan Proyek (Panduan Instalasi Lokal)

Pastikan perangkat Anda telah terinstal **Python 3.10+**. Ikuti 6 langkah berikut di terminal:

### 1. Buat Virtual Environment (`venv`)
```bash
python -m venv venv
```

### 2. Aktifkan Virtual Environment
* **Windows (PowerShell / CMD):**
  ```powershell
  venv\Scripts\activate
  ```
* **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```

### 3. Instal Seluruh Dependensi Pustaka
```bash
pip install -r requirements.txt
```

### 4. Salin `.env.example` menjadi `.env` lalu sesuaikan
Isi `DATABASE_URL` (tanpa `.env`, aplikasi memakai SQLite `scms_dev.db`) dan `SCMS_SECRET_KEY` (penanda tangan cookie sesi login).

### 5. Inisialisasi & Isi Data Awal (Database Seeder)
> Database lama dari Sprint 1 tetap bisa dipakai: saat aplikasi dijalankan, kolom baru (koordinat laporan, alamat domisili) ditambahkan otomatis. Jalankan seeder hanya untuk mengisi ulang data contoh.
> ⚠️ Seeder **menghapus seluruh tabel** lalu mengisinya ulang. Untuk database selain SQLite (mis. PostgreSQL) seeder menolak berjalan kecuali diberi `--force`.
```bash
python -m database.seed            # SQLite lokal
python -m database.seed --force    # PostgreSQL: hanya jika memang ingin mereset
```

### 6. Jalankan Pengujian Otomatis
Pengujian **selalu** memakai database terpisah `scms_test.db`, sehingga database di `.env` tidak tersentuh.
```bash
pytest -v                                      # semua: 17 BDD + 3 E2E Selenium + 64 uji cepat (butuh Chrome/Edge)
pytest tests/test_keamanan_dan_logika.py -v    # uji cepat saja, tanpa browser
HEADLESS=1 pytest -v                           # browser tanpa jendela
```

### 7. Jalankan Server Aplikasi Web
```bash
uvicorn app.main:app --reload
```
Setelah server aktif, buka browser dan akses tautan berikut:
* **Halaman Login Utama (`UC-K`):** `http://127.0.0.1:8000/Login`
* **Form Pelaporan Warga 4 Langkah (`UC-A`, login Warga):** `http://127.0.0.1:8000/lapor`
* **Dashboard Prioritas & Peta GIS (`UC-H`, login staf):** `http://127.0.0.1:8000/Dashboard`
* **Verifikasi Laporan & Evaluasi AI (`UC-B`, login Admin/Kabid):** `http://127.0.0.1:8000/verifikasi`
* **Penugasan Penilik Jalan & SPK (`UC-G`, login staf):** `http://127.0.0.1:8000/work-orders`

---

## 🤖 Mode AI

Semua fitur AI melewati satu layanan (`app/services/ai_service.py`) dan backend-nya dipilih lewat `.env`:

| Variabel | Bawaan | Pilihan lain |
| :--- | :--- | :--- |
| `SCMS_CV_BACKEND` | `simulasi` — **tidak ada model**; kategori & severity ditentukan dari **nama berkas** (nama berisi `kucing`, `selfie`, `mobil`, dst. ditolak; `retak` → Retak Permukaan; `amblas` → Jalan Amblas) | `yolov8` + `SCMS_YOLO_WEIGHTS=<path .pt>` (model kerusakan jalan, mis. dilatih pada RDD2022: D00/D10/D20 → Retak, D40 → Berlubang) |
| `SCMS_NLP_BACKEND` | `leksikal` — kemiripan kata (tanpa model) | `sentence-transformers` (model `SCMS_ST_MODEL`, bawaan `paraphrase-multilingual-MiniLM-L12-v2`) |

* Foto **benar-benar diunggah** dan diperiksa isinya (harus JPEG/PNG asli, ≤ 10 MB), lalu disimpan di `app/static/uploads/`.
* Dalam mode simulasi, UI menampilkan label **"Mode simulasi AI"** dan tidak menampilkan angka confidence.
* Model sungguhan: `pip install -r requirements-ai.txt`. Jika library/bobot model tidak ditemukan, aplikasi mencatat peringatan dan kembali ke mode simulasi.

## 🛡️ Hak Akses per Peran

| Halaman / Aksi | Warga | Admin (PPK) | Kepala Bidang | Penilik Jalan |
| :--- | :---: | :---: | :---: | :---: |
| `/Beranda`, `/lapor` | ✅ | – | – | – |
| `/Dashboard` | – | ✅ | ✅ | ✅ |
| `/verifikasi` | – | ✅ | 👁️ lihat saja | – |
| `/work-orders` | – | ✅ | 👁️ lihat saja | 👁️ lihat saja |
| Setujui / inspeksi / tugaskan | – | ✅ | – | – |

Halaman tanpa login dialihkan ke `/Login`; peran yang tidak berhak mendapat `403`. Sesi berakhir otomatis jika akun dinonaktifkan. *Exposure* tiket dihitung dari jumlah **warga berbeda** yang melapor, sehingga satu warga yang mengirim ulang laporan tidak menaikkan prioritas.

---

## 🔐 Akun Kredensial Pengujian (Demo Login)

Seluruh akun pengujian di bawah ini menggunakan kata sandi: **`password123`**

| Peran Aktor | Identifier (No. HP / Email) | Halaman Tujuan Setelah Login |
| :--- | :--- | :--- |
| **Warga** | `0812xxxxxxx` (atau NIK `3578010101900001`) | `/Beranda` (Form Pelaporan Warga) |
| **Admin (PPK)** | `admin@dpupr.surabaya.go.id` | `/Dashboard` (Dashboard Prioritas & Verifikasi) |
| **Penilik Jalan** | `budi.santoso@dpupr.surabaya.go.id` | `/Dashboard` (halaman `/TugasLapangan` direncanakan Sprint 2) |
| **Kepala Bidang** | `kabid@dpupr.surabaya.go.id` | `/Dashboard` (Monitoring Eksekutif & Analitik) |

---
*&copy; 2026 Kelompok 7 — Kelas I3. Pengembangan Perangkat Lunak Praktik (Agile Pemdigi).*