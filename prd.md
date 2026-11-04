# Product Requirements Document (prd.md)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 2.0 (Full Product Scope — Sprint 1 & Sprint 2 Implemented)  
**Organisasi / Tim:** Kelompok 7 (Kelas I3) — Rizaldi Rizki Saputra (187241005) & Alfarrel Yuri Ramadhani (187241109)  
**Target Instansi:** Dinas Sumber Daya Air dan Bina Marga (DSDABM / PUPR) Pemerintah Kota Surabaya  

## 1. Ringkasan Produk
SCMS-AI adalah platform web terintegrasi berbasis Artificial Intelligence (Computer Vision & NLP) dan Sistem Informasi Geografis (GIS) yang mengotomatiskan siklus hidup pengaduan kerusakan jalan di Kota Surabaya mulai dari pelaporan warga, deduplikasi spasial-semantik, prioritisasi berbasis risiko, verifikasi admin, penugasan penilik jalan, survei inspeksi lapangan, penerbitan SPK & perbaikan fisik, notifikasi warga, hingga evaluasi rating kepuasan publik.

## 2. Profil Pengguna & Hak Akses (RBAC)
| Aktor | Identifier Login | Hak Akses & Tanggung Jawab Utama | Halaman Tujuan |
| :--- | :--- | :--- | :--- |
| **Warga** | No. HP, Email, atau NIK | Membuat laporan 4 langkah (`/lapor`), melacak progres (`/lacak`), membuka notifikasi (`/notifikasi`), dan memberi rating 1-5 bintang (`/lacak/{id}/rating`). | `/Beranda` |
| **Admin (PPK)** | Email Instansi | Mengakses `/Dashboard`, memverifikasi laporan (`/verifikasi`), mengelola data master (`/master-data`), menugaskan penilik & menerbitkan SPK (`/work-orders`). | `/Dashboard` |
| **Penilik Jalan** | Email atau NIP 18 Digit | Mengakses tugas lapangan di wilayah rayonnya (`/TugasLapangan`), menyimpan survei inspeksi (`Terinspeksi`), dan memperbarui progres SPK hingga `Selesai`. | `/TugasLapangan` |
| **Kepala Bidang** | Email Instansi | Memantau `/Dashboard`, `/verifikasi`, `/work-orders`, dan `/master-data` dalam mode baca (read-only). | `/Dashboard` |

## 3. Aturan Bisnis Inti (Core Business Rules)
* **BR-1 (Validasi Foto & Deskripsi):** Foto wajib berupa berkas gambar asli `JPEG/PNG` (diperiksa dari bytes header via Pillow) dengan ukuran <= 10.0 MB dan terdeteksi sebagai objek jalan rusak. Deskripsi minimal 10 karakter.
* **BR-2 (Formula Risk Score & SLA — `app/services/risk_scoring.py`):**
  `Risk Score = clip(0.50*S + 0.45*ln(E+1) + 0.15*V + 0.25*C, 0.0, 10.0)`
  - `>= 8.0`: Prioritas `Urgent` (SLA `24 jam`)
  - `6.0 - 7.9`: Prioritas `Tinggi` (SLA `3 x 24 jam`)
  - `4.0 - 5.9`: Prioritas `Borderline` / `Sedang` (SLA `5 x 24 jam`, `Butuh Verifikasi Lapangan`)
  - `< 4.0`: Prioritas `Rendah` (SLA `7 x 24 jam`)
* **BR-3 (Deduplikasi Spasial-Semantik — `app/services/deduplikasi.py`):** Laporan baru dengan kategori sama yang berjarak <= 50 meter (atau lokasi jalan sama) dan memiliki kemiripan deskripsi dengan WorkOrder aktif akan digabungkan (`status = "Digabungkan"`). `exposure_count` bertambah +1 hanya jika pelapor adalah warga yang berbeda.
* **BR-4 (Alur Status Atomik — `app/services/alur_status.py`):**
  Urutan status: `Dilaporkan -> Disetujui / Menunggu Inspeksi / Menunggu Penugasan / Ditugaskan -> Terinspeksi -> Dalam Proses -> Selesai`.
  Setiap perubahan status wajib menggunakan pemeriksaan Compare-and-Set atomik, tidak boleh memundurkan status, wajib mencatat log ke tabel `riwayat_status`, dan wajib mengirim `notifikasi` ke seluruh warga pelapor pada tiket tersebut.

## 4. Cakupan Skenario BDD (29 Skenario di `tests/features/`)
### Sprint 1 (17 Skenario)
* **UC-K (`uc_k_login.feature` — 5 skenario):** Login Warga, Admin, Penilik Jalan, kredensial salah, dan form kosong.
* **UC-A (`uc_a_buat_laporan.feature` — 4 skenario):** Laporan baru terbit tiket, deduplikasi otomatis, penolakan format/ukuran foto, dan penolakan objek bukan jalan.
* **UC-B (`uc_b_verifikasi.feature` — 4 skenario):** Tabel urut Risk Score, setujui tiket jelas, tugaskan inspeksi tambahan skor ambigu, dan lanjutkan tanpa inspeksi dengan log keputusan.
* **UC-G (`uc_g_penugasan.feature` — 2 skenario):** Tugaskan Penilik Jalan tersedia (`Ditugaskan`) dan penanganan saat semua penilik penuh (`Menunggu Penugasan`).
* **UC-H (`uc_h_dashboard.feature` — 2 skenario):** Peta GIS & KPI prioritas serta filter multi-parameter dengan pesan kosong.

### Sprint 2 (14 Skenario)
* **UC-C (`uc_c_lacak_status.feature` — 2 skenario):** Warga melacak detail & timeline laporan (`LAP-2026-0001`) serta penanganan nomor tiket tidak ditemukan (`LAP-9999-XXXX`).
* **UC-D (`uc_d_kelola_master_data.feature` — 2 skenario):** Admin menambah Penilik Jalan baru dengan NIP 18 digit serta penolakan duplikasi NIP/Kode Wilayah.
* **UC-E (`uc_e_inspeksi_lapangan.feature` — 2 skenario):** Penilik Jalan menyimpan dimensi kerusakan, catatan teknis, rekomendasi, dan foto survei (`Terinspeksi`), serta penolakan form inspeksi belum lengkap.
* **UC-F (`uc_f_update_perbaikan.feature` — 3 skenario):** Admin menerbitkan SPK (`Dalam Proses`), petugas menyelesaikan perbaikan dengan unggah foto bukti (`Selesai`), serta penolakan status `Selesai` tanpa foto bukti perbaikan.
* **UC-I (`uc_i_notifikasi_status.feature` — 1 skenario):** Warga mengklik notifikasi belum dibaca, status berubah menjadi dibaca, dan diarahkan ke halaman `/lacak` laporan terkait.
* **UC-J (`uc_j_rating_ulasan.feature` — 2 skenario):** Warga mengirim rating bintang 1-5 dan ulasan pada laporan `Selesai`, serta penolakan jika bintang belum dipilih.
* **UC-L (`uc_l_laporan_kinerja.feature` — 2 skenario):** Kepala Bidang melihat rekap kinerja per wilayah (kepatuhan SLA, status SLA tiap tiket, statistik risiko) dan mengunduh CSV rekap wilayah, serta pesan `"Tidak ada data kinerja pada periode yang dipilih"` tanpa tombol unduh jika periode kosong. Jam SLA dihitung sejak tiket diterima (entri pertama `riwayat_status`) hingga `tanggal_selesai`.
