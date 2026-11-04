# Product Requirements Document (PRD)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 1.0 (Full Product Scope — Sprint 1, Sprint 2 & Release)  
**Organisasi / Tim:** Kelompok 7 (Kelas I3) — `AgilePemdigi-2026/SCMS-AI-PPL-PRAK`  
**Pengembang Inti:** Rizaldi Rizki Saputra & Alfarrel Yuri Ramadhani  
**Target Instansi:** Dinas Sumber Daya Air dan Bina Marga (DSDABM / PUPR) Pemerintah Kota Surabaya  

---

## 1. Visi Produk & Ringkasan Eksekutif (Executive Summary)

### 1.1 Pernyataan Masalah (Problem Statement)
Penanganan pengaduan kerusakan jalan dan infrastruktur perkotaan di Kota Surabaya secara konvensional menghadapi empat kendala utama:
1. **Banjir Laporan Duplikat:** Satu titik jalan berlubang yang berada di jalan protokol dapat dilaporkan puluhan kali oleh warga berbeda, menyebabkan antrean tiket membengkak dan tumpang tindih.
2. **Validasi Manual yang Lambat:** Petugas harus memeriksa satu per satu foto laporan warga untuk menyaring laporan palsu, foto tidak relevan (*spam*), atau deskripsi yang tidak jelas.
3. **Prioritisasi Subjektif (FIFO vs Risk-Based):** Penanganan yang hanya mengandalkan urutan waktu masuk (*First-In, First-Out*) berisiko menunda perbaikan kerusakan kritis di jalan arteri berkecepatan tinggi.
4. **Kurangnya Transparansi & Keterlacakan Lapangan:** Warga sulit melacak progres tindak lanjut laporan, sementara Pejabat Pembuat Komitmen (PPK) dan Kepala Bidang kesulitan memantau kepatuhan *Service Level Agreement* (SLA) Penilik Jalan secara geospasial.

### 1.2 Solusi yang Diusulkan (Proposed Solution)
**SCMS-AI** adalah platform web terintegrasi berbasis kecerdasan buatan (*Artificial Intelligence*) dan Sistem Informasi Geografis (*GIS*) yang mengotomatiskan siklus hidup pengaduan infrastruktur jalan dari pelaporan warga hingga penyelesaian fisik di lapangan:
* **Automated Visual Triage (Computer Vision — YOLOv8-Infra):** Memvalidasi keberadaan objek kerusakan jalan pada foto unggahan warga, mengklasifikasikan kategori kerusakan secara otomatis, dan mengekstraksi skor keparahan visual (*Severity Score* skala $0.0 - 10.0$).
* **Spatial-Semantic Deduplication (NLP — Sentence-Transformers):** Mendeteksi laporan baru yang berada di lokasi berdekatan dan memiliki kemiripan makna deskripsi dengan tiket *Work Order* yang masih aktif, menggabungkannya secara otomatis, serta menaikkan metrik *Exposure Count* (+1) sebagai indikator urgensi publik.
* **Multi-Factor Risk Scoring Engine:** Menghitung skor prioritas penanganan (*Risk Score*) secara objektif berdasarkan tingkat keparahan visual, jumlah pelapor, kerentanan lokasi, dan kelas jalan untuk menentukan rekomendasi SLA.
* **End-to-End Dispatch & Field Monitoring:** Mengelola verifikasi Admin/PPK (termasuk penanganan skor ambigu/*borderline*), penugasan Penilik Jalan per wilayah rayon, pembaruan status progres lapangan, pengunggahan foto bukti perbaikan (*before-after*), notifikasi warga, hingga evaluasi kepuasan publik (*rating*) dan ekspor laporan eksekutif.

---

## 2. Profil Pengguna & Hak Akses (User Personas & RBAC)

Sistem menerapkan kontrol akses berbasis peran (*Role-Based Access Control*) untuk **4 aktor utama**:

| Aktor | Identifier Login | Peran & Tanggung Jawab Utama | Halaman Utama (Redirect) |
| :--- | :--- | :--- | :--- |
| **1. Warga (Pelapor)** | Nomor HP (`0812...`) | Mengajukan laporan kerusakan 4 langkah, memantau progres tiket, menerima notifikasi perubahan status, dan memberikan *rating* serta ulasan hasil perbaikan. | `/Beranda` (`/lapor`) |
| **2. Admin (PPK / Verifikator)** | Email Instansi (`admin@dpupr...`) | Memantau *Dashboard Prioritas & Peta GIS*, memverifikasi laporan masuk, mengevaluasi tiket dengan skor risiko ambigu (*borderline*), serta menerbitkan penugasan (*Work Order* / SPK) ke Penilik Jalan. | `/Dashboard` |
| **3. Penilik Jalan (Petugas Lapangan)** | Email Instansi (`budi.santoso@dpupr...`) | Menerima penugasan SPK atau tugas inspeksi tambahan di wilayah rayonnya, melakukan survei fisik lapangan, memperbarui status pengerjaan, dan mengunggah foto bukti penyelesaian pekerjaan. | `/TugasLapangan` |
| **4. Kepala Bidang (Eksekutif)** | Email Instansi (`kabid@dpupr...`) | Memantau kinerja penanganan infrastruktur lintas wilayah rayon, mengevaluasi pencapaian SLA, melihat analitik tren kerusakan, dan mengekspor laporan berkala (PDF/Excel/CSV). | `/Dashboard` |

---

## 3. Aturan Bisnis Inti & Formula AI (Core Business Rules)

Seluruh logika *backend* wajib mematuhi aturan bisnis (*Business Rules*) berikut:

### BR-1: Validasi Bukti Visual & Deskripsi Laporan
1. Berkas foto wajib berformat **`.jpg`, `.jpeg`, atau `.png`** dengan ukuran maksimal **$\le 10.0\text{ MB}$**.
2. Model *Computer Vision* memeriksa keberadaan objek infrastruktur jalan. Jika foto terdeteksi sebagai objek non-jalan (misal: swafoto, hewan, makanan, dokumen), laporan **ditolak** pada tahap *Capture* dan tidak disimpan ke basis data.
3. Deskripsi teks laporan wajib memiliki panjang minimal **$\ge 10\text{ karakter}$**.

### BR-2: Formula Perhitungan *Risk Score* & Klasifikasi Prioritas
Setiap *Work Order* memiliki *Risk Score* (skala $0.0 - 10.0$) yang dihitung dari 4 parameter:
$$\text{Risk Score} = \text{clip}\left( \text{ round}\left( w_s \cdot \text{Severity} + w_e \cdot \ln(\text{Exposure} + 1) + w_v \cdot \text{Vulnerability} + w_c \cdot \text{Criticality} \right), 0.0, 10.0 \right)$$
*(Atau dalam representasi faktor perkalian ternormalisasi: $\text{Severity} \times \text{Exposure} \times \text{Vulnerability} \times \text{Criticality}$).*

**Aturan Ambang Batas Prioritas & Rekomendasi SLA:**
* **$\text{Risk Score} \ge 8.0$ $\rightarrow$ Prioritas `Urgent` / `Darurat`:** Rekomendasi SLA **24 jam** (Warna Indikator GIS: **Merah `#DC2626`**).
* **$6.0 \le \text{Risk Score} < 8.0$ $\rightarrow$ Prioritas `Tinggi`:** Rekomendasi SLA **3 x 24 jam** (Warna Indikator GIS: **Oranye `#EA580C`**).
* **$4.0 \le \text{Risk Score} < 6.0$ $\rightarrow$ Prioritas `Borderline` / `Sedang` (Rentang Ambigu):** Memicu opsi **`Butuh Verifikasi Lapangan`** pada modul Verifikasi Admin (Warna Indikator GIS: **Kuning/Amber `#D97706`**).
* **$\text{Risk Score} < 4.0$ $\rightarrow$ Prioritas `Rendah`:** Rekomendasi SLA **7 x 24 jam** (Pemeliharaan Rutin).

### BR-3: Aturan Deduplikasi Spasial-Semantik
Apabila warga mengirimkan laporan baru pada ruas jalan/koordinat yang berdekatan dengan *Work Order* aktif (`status_work_order != "Selesai"`) serta memiliki kategori yang sama dan kemiripan semantik deskripsi yang tinggi:
1. Sistem **tidak membuat *Work Order* baru**.
2. Entitas `Laporan` baru tetap disimpan dan ditautkan (`id_work_order`) ke *Work Order* aktif tersebut dengan status laporan `"Digabungkan"`.
3. Nilai `exposure_count` pada *Work Order* induk ditambah **+1**, dan `risk_score` dihitung ulang.
4. Warga menerima notifikasi berisi nomor tiket aktif tempat laporannya digabungkan.

### BR-4: Aturan Penanganan Skor Risiko Ambigu (*Borderline*)
Saat Admin memverifikasi tiket yang berada pada rentang ambigu ($4.0 \le \text{Risk Score} \le 6.0$ atau `prioritas == "Borderline"`):
* Sistem wajib menampilkan label peringatan **`"Butuh Verifikasi Lapangan"`** beserta dua opsi tindakan:
  1. **`Tugaskan Inspeksi Tambahan`:** Mengubah status tiket menjadi **`"Menunggu Inspeksi"`** dan menugaskan Penilik Jalan di wilayah terkait untuk pengecekan fisik.
  2. **`Lanjutkan Tanpa Inspeksi`:** Mengubah status tiket menjadi **`"Disetujui"`** namun wajib mencatat jejak audit pada kolom `log_keputusan` dengan format: `"Disetujui tanpa inspeksi oleh [email_admin]"`.

### BR-5: Aturan Ketersediaan Penilik Jalan per Wilayah Rayon
Saat Admin menugaskan *Work Order* yang telah disetujui:
* Sistem hanya menampilkan daftar Penilik Jalan yang bertugas di `id_wilayah` yang sama dengan lokasi tiket dan berstatus **`ketersediaan == True`**.
* Jika terdapat Penilik Jalan yang tersedia, penugasan mengubah status tiket menjadi **`"Ditugaskan"`**.
* Jika seluruh Penilik Jalan di wilayah tersebut sedang penuh (`ketersediaan == False`), sistem memberikan peringatan dan mengizinkan Admin menyimpan tiket dengan status **`"Menunggu Penugasan"`**.

---

## 4. Siklus Hidup Status Tiket (Work Order State Machine)

Transisi nilai kolom `status_work_order` pada tabel `work_order` mengikuti alur ketat berikut:

```text
[Warga Submit Laporan Baru (UC-A)]
          │
          ▼
    "Dilaporkan"
          │
          ├──► (Jika Skor Ambigu 4.0-6.0 & Admin Pilih Inspeksi - UC-B) ──► "Menunggu Inspeksi"
          │                                                                          │
          │                                                    (Penilik Input Hasil Inspeksi - UC-E)
          │                                                                          │
          ▼                                                                          ▼
  [Admin Setujui Tiket / Lanjutkan Tanpa Inspeksi (UC-B)] ◄──────────────────────────┘
          │
          ▼
     "Disetujui"
          │
          ├──► (Jika Penilik Wilayah Penuh - UC-G) ──► "Menunggu Penugasan"
          │                                                    │
          ▼                                                    ▼
  [Admin Tugaskan Penilik Jalan Tersedia (UC-G)] ◄─────────────┘
          │
          ▼
     "Ditugaskan"
          │
          ▼
  [Penilik Jalan Mulai Pengerjaan Fisik (UC-F)]
          │
          ▼
    "Dalam Proses"
          │
          ▼
  [Penilik Unggah Foto Bukti Perbaikan & Selesaikan SPK (UC-F)]
          │
          ▼
      "Selesai" ──► [Kirim Notifikasi ke Warga (UC-I) & Buka Form Rating (UC-J)]
```

---

## 5. Spesifikasi Fungsional Lengkap (Seluruh Use Case Produk)

Produk SCMS-AI terdiri atas **12 Use Case terintegrasi** yang dibagi ke dalam tahapan rilis Sprint:

### 5.1 Kelompok Fitur Sprint 1 (Core Triage, Verification & Dispatch — 17 Skenario BDD)

#### **UC-K: Login / Autentikasi Pengguna (`kontrol_autentikasi.py`)**
* **`REQ-AUTH-1`:** Mendukung autentikasi multi-aktor menggunakan satu pintu form login (`/Login`).
* **`REQ-AUTH-2`:** Warga menggunakan `no_hp`, sedangkan Admin, Penilik Jalan, dan Kepala Bidang menggunakan `email` instansi.
* **`REQ-AUTH-3`:** Menampilkan pesan `"Kredensial tidak valid, silakan periksa kembali nomor HP/email dan password Anda"` jika akun tidak ditemukan atau kata sandi salah.
* **`REQ-AUTH-4`:** Menampilkan pesan `"Nomor HP/email dan password wajib diisi"` jika pengguna mengirim form kosong.

#### **UC-A: Membuat Laporan Kerusakan 4 Langkah (`kontrol_pelaporan.py`)**
* **`REQ-RPT-1` (Step 1 - Capture):** Validasi ekstensi file (`JPG/PNG`) dan ukuran ($\le 10\text{ MB}$). Jika gagal, tampilkan `"Format harus JPG/PNG dan ukuran maksimal 10MB"`.
* **`REQ-RPT-2` & `REQ-RPT-3` (AI CV Detection):** Deteksi objek jalan rusak. Jika foto tidak relevan (misal `kucing.jpg`), tampilkan `"Objek jalan rusak tidak terdeteksi, silakan ambil ulang foto"`.
* **`REQ-RPT-4` (Step 2 - Location):** Pencarian alamat jalan di Surabaya menggunakan *Nominatim Geocoding API*, tombol deteksi GPS perangkat, serta pin peta interaktif yang memperbarui koordinat `(latitude, longitude)` dan wilayah rayon secara otomatis.
* **`REQ-RPT-5` & `REQ-RPT-6` (Step 3 - Detail):** Menampilkan rekomendasi kategori AI (misal `"Jalan Berlubang"`) yang dapat diubah warga, serta input deskripsi minimal 10 karakter.
* **`REQ-RPT-7` s/d `REQ-RPT-9` (Step 4 - Review & Submit):** Peninjauan ringkasan data dan eksekusi deduplikasi otomatis. Menerbitkan tiket baru (`REP-2026-00341`, status `"Dilaporkan"`) atau menggabungkan ke tiket aktif (`REP-2026-00298`).

#### **UC-B: Memverifikasi Laporan Kerusakan (`kontrol_verifikasi.py`)**
* **`REQ-VER-1`:** Menampilkan tabel antrean *Work Order* terurut dari `risk_score` tertinggi ke terendah.
* **`REQ-VER-2`:** Menampilkan detail tiket mencakup foto bukti, *Severity Score*, *Risk Score*, jumlah pelapor (*Exposure*), lokasi jalan, dan rekomendasi SLA.
* **`REQ-VER-3`:** Tombol `"Setujui Tiket"` mengubah status menjadi `"Disetujui"`.
* **`REQ-VER-4` s/d `REQ-VER-6`:** Untuk tiket dengan skor risiko ambigu (`REP-2026-00355`, skor `5.1`), menampilkan opsi `"Butuh Verifikasi Lapangan"` dengan pilihan `"Tugaskan Inspeksi Tambahan"` (status menjadi `"Menunggu Inspeksi"`) atau `"Lanjutkan Tanpa Inspeksi"` (status menjadi `"Disetujui"` + catat `log_keputusan`).

#### **UC-G: Menugaskan Penilik Jalan (`kontrol_penugasan.py`)**
* **`REQ-ASG-1`:** Menampilkan daftar *Work Order* beserta filter Wilayah dan Status.
* **`REQ-ASG-2`:** Menampilkan rekomendasi SLA penanganan (misal `"24 jam"` untuk tiket *Urgent* `REP-2026-00341`) dan daftar Penilik Jalan yang tersedia di wilayah tiket tersebut (`Wilayah Gubeng`).
* **`REQ-ASG-3`:** Mengubah status menjadi `"Ditugaskan"` dan menyimpan nama Penilik Jalan pada tiket saat penugasan dikonfirmasi.
* **`REQ-ASG-4`:** Menampilkan peringatan `"Semua Penilik Jalan di wilayah ini sedang dalam penugasan aktif"` jika seluruh petugas di wilayah tersebut tidak tersedia (contoh: `REP-2026-00360` di `Wilayah Benowo`) serta mengubah status menjadi `"Menunggu Penugasan"`.

#### **UC-H: Melihat Dashboard Prioritas Infrastruktur (`kontrol_dashboard.py`)**
* **`REQ-DSH-1`:** Menampilkan peta geospasial interaktif Kota Surabaya (Leaflet.js) dengan titik lokasi spesifik dan lingkaran radius dampak berwarna sesuai *severity/risk score*.
* **`REQ-DSH-2`:** Menampilkan daftar tiket pada tabel *Priority Queue* terurut dari *Risk Score* tertinggi (`"REP-2026-00341 (8.4)"`).
* **`REQ-DSH-3`:** Menampilkan 4 kartu metrik KPI dinamis (Total Pengaduan, Prioritas Darurat, Kasus Dalam Penanganan, Tingkat Penyelesaian) dan Ringkasan Zona Risiko per wilayah rayon.
* **`REQ-DSH-4`:** Menyediakan filter kombinasi Wilayah, Status, dan Kategori. Jika hasil filter kosong, menampilkan pesan `"Tidak ada laporan sesuai filter"`.
* **`REQ-DSH-5`:** Menyediakan tombol aksi cepat (`Lihat Detail`, `Setujui`, `Tugaskan`) pada setiap baris tiket.

---

### 5.2 Kelompok Fitur Sprint 2 & Full Release (Field Execution, Tracking & Analytics)

Untuk pengembangan tahap selanjutnya (Sprint 2), sistem telah menyiapkan skema tabel dan arsitektur untuk modul-modul berikut:

1. **UC-C — Melacak Status Laporan Warga:**
   * Warga dapat mencari dan melihat linimasa (*timeline*) progres tiket yang dilaporkannya (`Dilaporkan` $\rightarrow$ `Disetujui` $\rightarrow$ `Ditugaskan` $\rightarrow$ `Dalam Proses` $\rightarrow$ `Selesai`) beserta foto bukti penanganan.
2. **UC-D — Mengelola Data Master Wilayah & Penilik Jalan:**
   * Admin dapat memperbarui daftar wilayah rayon, kuota beban kerja Penilik Jalan, dan status ketersediaan petugas.
3. **UC-E — Mencatat Hasil Inspeksi Lapangan (Penilik Jalan):**
   * Penilik Jalan membuka daftar tiket berstatus `"Menunggu Inspeksi"`, mengisi `catatan_inspeksi`, mengunggah `foto_inspeksi`, dan memperbarui kejelasan tingkat kerusakan pada tabel `inspeksi`.
4. **UC-F — Memperbarui Status Perbaikan Lapangan (Penilik Jalan):**
   * Penilik Jalan memperbarui status SPK dari `"Ditugaskan"` menjadi `"Dalam Proses"`, lalu mengunggah foto dokumentasi perbaikan selesai untuk mengubah status menjadi `"Selesai"`.
5. **UC-I — Mengirim & Melihat Notifikasi Status Laporan:**
   * Setiap perubahan status *Work Order* secara otomatis mencatat pesan pemberitahuan baru pada tabel `notifikasi` untuk Warga pelapor.
6. **UC-J — Memberikan Rating & Ulasan Penanganan (Warga):**
   * Setelah tiket berstatus `"Selesai"`, Warga dapat memberikan penilaian bintang (`nilai_rating` skala $1 - 5$) dan `komentar` pada tabel `rating`.
7. **UC-L — Mengekspor Laporan Kinerja Infrastruktur (Kepala Bidang / Admin):**
   * Kepala Bidang dapat mengunduh rekapitulasi kinerja penanganan, kepatuhan SLA, dan statistik risiko per wilayah rayon.
   * **`REQ-KIN-1`:** Halaman `/laporan-kinerja` (Kepala Bidang & Admin) dengan filter periode (tanggal tiket diterima, WIB) dan wilayah; tanggal tidak valid ditolak dengan pesan `"Format tanggal tidak valid (gunakan YYYY-MM-DD)"` atau `"Tanggal mulai tidak boleh setelah tanggal akhir"`.
   * **`REQ-KIN-2`:** Status SLA tiap tiket dihitung dari entri pertama `riwayat_status` hingga `tanggal_selesai` terhadap `sla_rekomendasi`: `Tepat Waktu`/`Terlambat` (selesai) atau `Dalam SLA`/`Melewati SLA` (aktif). Kepatuhan SLA = selesai tepat waktu ÷ seluruh tiket selesai.
   * **`REQ-KIN-3`:** Rekap per wilayah dan per prioritas: total, selesai, aktif, tingkat penyelesaian, kepatuhan SLA, tiket aktif melewati SLA, rata-rata waktu penyelesaian, rata-rata & tertinggi risk score, jumlah Urgent, rata-rata rating warga.
   * **`REQ-KIN-4`:** Unduhan CSV (rekap wilayah / detail tiket, UTF-8 BOM, teks diamankan dari formula spreadsheet) dan cetak/simpan PDF lewat browser. Jika periode kosong, tampilkan `"Tidak ada data kinerja pada periode yang dipilih"` tanpa tombol unduh.

---

## 6. Skema Basis Data Relasional (10 Tabel Physical Data Model)

Basis data didefinisikan menggunakan SQLAlchemy ORM di dalam `app/models/entities.py` dengan **10 entitas tabel**:

1. **`wilayah`**: `id_wilayah` (PK), `nama_wilayah`, `kecamatan`, `kota`, `kode_pos`.
2. **`warga`**: `id_warga` (PK), `nama_lengkap`, `no_hp` (Unique), `email`, `password`, `alamat_domisili`, `tanggal_registrasi`.
3. **`admin`**: `id_admin` (PK), `nama_admin`, `email` (Unique), `password`, `nip`, `jabatan`, `no_telepon`.
4. **`kepala_bidang`**: `id_kabid` (PK), `nama_lengkap`, `email` (Unique), `password`, `nip`, `bidang`, `no_telepon`.
5. **`penilik_jalan`**: `id_penilik` (PK), `id_wilayah` (FK), `nama_lengkap`, `email` (Unique), `password`, `nip`, `no_telepon`, `ketersediaan` (Boolean).
6. **`work_order`**: `id_work_order` (PK, contoh: `REP-2026-00341`), `id_wilayah` (FK), `id_admin_verifikator` (FK), `id_penilik` (FK), `kategori_kerusakan`, `lokasi_jalan`, `kelas_jalan`, `severity_score_kasus`, `exposure_count`, `vulnerability_score`, `risk_score`, `prioritas`, `status_work_order`, `sla_rekomendasi`, `penilik_ditugaskan`, `log_keputusan`, `tanggal_dibuat`, `tanggal_selesai`.
7. **`laporan`**: `id_laporan` (PK), `id_work_order` (FK), `id_warga` (FK), `id_wilayah` (FK), `deskripsi`, `url_foto`, `lokasi_teks`, `severity_score`, `status`, `tanggal_lapor`.
8. **`inspeksi`**: `id_inspeksi` (PK), `id_work_order` (FK), `id_laporan` (FK), `id_penilik` (FK), `tanggal_inspeksi`, `catatan_inspeksi`, `foto_inspeksi`, `status_inspeksi`.
9. **`notifikasi`**: `id_notifikasi` (PK), `id_warga` (FK), `id_laporan` (FK), `judul`, `pesan`, `status_baca` (Boolean), `waktu_kirim`.
10. **`rating`**: `id_rating` (PK), `id_warga` (FK), `id_laporan` (FK), `nilai_rating` (Integer 1-5), `komentar`, `tanggal_rating`.

---

## 7. Kebutuhan Non-Fungsional (Non-Functional Requirements)

1. **Kinerja (Performance):** Waktu muat halaman *Dashboard GIS* dan respons pemfilteran tiket harus selesai dalam waktu $< 2\text{ detik}$ untuk ratusan titik aktif.
2. **Keandalan Pengujian (Testability):** Seluruh fitur wajib memiliki cakupan pengujian penerimaan otomatis berbasis Gherkin (`pytest-bdd`) yang terisolasi dan deterministik melalui fungsi `seed_data()`.
3. **Konsistensi Antarmuka (UI/UX):** Menggunakan skema warna resmi pemerintahan Dinas PUPR (Biru Utama `#0B5ED7`, Slate Gelap `#0F2942`, latar `#F8FAFC`), tipografi `Inter`, responsif di perangkat *mobile* maupun *desktop*, serta bebas dari elemen dekoratif yang tidak perlu.
4. **Standar Kode & Dokumentasi:** Mengikuti pola arsitektur **MVC (Model-View-Controller)** dengan pemisahan tegas antara *routing* (`app/main.py`), logika bisnis (`app/controllers/`), entitas data (`app/models/entities.py`), dan tampilan (`app/views/templates/`).