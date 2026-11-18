import json
from datetime import datetime, date, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Warga(Base):
    __tablename__ = "warga"
    id_warga = Column(String(20), primary_key=True, index=True)
    nik = Column(String(16), unique=True, nullable=True, index=True)
    nama_warga = Column(String(50), nullable=False)
    email = Column(String(50), unique=True, index=True)
    no_hp = Column(String(15), unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    alamat_domisili = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    laporan_list = relationship("Laporan", back_populates="warga")
    notifikasi_list = relationship("Notifikasi", back_populates="warga")

class Admin(Base):
    __tablename__ = "admin"
    id_admin = Column(String(20), primary_key=True, index=True)
    nama_admin = Column(String(50), nullable=False)
    email_admin = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_kepala_bidang = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    work_orders = relationship("WorkOrder", back_populates="admin")

class Wilayah(Base):
    __tablename__ = "wilayah"
    id_wilayah = Column(String(20), primary_key=True, index=True)
    nama_wilayah = Column(String(50), nullable=False, unique=True)
    kecamatan = Column(String(100), nullable=True)

    penilik_list = relationship("PenilikJalan", back_populates="wilayah")
    laporan_list = relationship("Laporan", back_populates="wilayah")

class PenilikJalan(Base):
    __tablename__ = "penilik_jalan"
    id_penilik = Column(String(20), primary_key=True, index=True)
    id_wilayah = Column(String(20), ForeignKey("wilayah.id_wilayah"), nullable=False)
    nama_penilik = Column(String(50), nullable=False)
    nip = Column(String(20), unique=True, index=True, nullable=True)
    email_penilik = Column(String(50), unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    status_ketersediaan = Column(String(20), default="Tersedia")
    is_active = Column(Boolean, default=True)

    wilayah = relationship("Wilayah", back_populates="penilik_list")
    work_orders = relationship("WorkOrder", back_populates="penilik")
    inspeksi_list = relationship("Inspeksi", back_populates="penilik")

class WorkOrder(Base):
    __tablename__ = "work_order"
    id_work_order = Column(String(20), primary_key=True, index=True)
    id_admin = Column(String(20), ForeignKey("admin.id_admin"), nullable=True)
    id_penilik = Column(String(20), ForeignKey("penilik_jalan.id_penilik"), nullable=True)
    id_wilayah = Column(String(20), ForeignKey("wilayah.id_wilayah"), nullable=True)
    
    kategori_kerusakan = Column(String(50), nullable=False)
    lokasi_jalan = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # Severity used by the BR-2 formula: the AI (report) severity until a field inspection
    # sets the field severity (PRD 5.3 BR-2), which is then used for every later recompute.
    severity_score_kasus = Column(Float, default=0.0)
    # Severity from the citizen reports (AI analysis / category base value), kept for comparison
    # after the field inspection replaced it in severity_score_kasus.
    severity_ai = Column(Float, nullable=True)
    exposure_count = Column(Integer, default=1)
    vulnerability_score = Column(Float, default=1.0)
    # Defaults match risk_scoring: KELAS_JALAN_DEFAULT, and the BR-2 class of risk_score 0.0 (Rendah).
    kelas_jalan = Column(String(15), default="Kolektor")
    risk_score = Column(Float, default=0.0)
    prioritas = Column(String(20), default="Rendah")
    status_work_order = Column(String(30), default="Dilaporkan")
    # DEPRECATED: the SLA concept was removed (teaching assistant's review). The app no longer
    # writes or reads this column; it is kept only so existing databases need no risky migration.
    sla_rekomendasi = Column(String(30), nullable=True)
    log_keputusan = Column(Text, nullable=True)
    tanggal_ditugaskan = Column(Date, nullable=True)
    nomor_spk = Column(String(50), unique=True, nullable=True)
    tim_pelaksana = Column(String(100), nullable=True)
    tanggal_selesai = Column(DateTime, nullable=True)
    # Sprint 3 (PRD 5.3 BR-4): why, by whom and when the ticket was closed (status "Ditutup").
    alasan_tutup = Column(String(50), nullable=True)
    ditutup_oleh = Column(String(100), nullable=True)
    tanggal_ditutup = Column(DateTime, nullable=True)
    # Sprint 3 (PRD 5.3 BR-1): the AI recognised no damage on the photo that opened the ticket, so
    # it is treated like an ambiguous score at verification. Cleared only while still "Dilaporkan",
    # when a report the AI does recognise is merged in (team decision 5.9 no. 10); never afterwards.
    perlu_tinjauan_manual = Column(Boolean, default=False)

    admin = relationship("Admin", back_populates="work_orders")
    penilik = relationship("PenilikJalan", back_populates="work_orders")
    laporan_list = relationship("Laporan", back_populates="work_order")
    perbaikan_list = relationship("Perbaikan", back_populates="work_order")
    riwayat_list = relationship("RiwayatStatus", back_populates="work_order", order_by="RiwayatStatus.waktu")
    inspeksi_list = relationship("Inspeksi", order_by="Inspeksi.id_inspeksi", viewonly=True)

    @property
    def severity_ai_awal(self):
        """AI severity for display; old rows without severity_ai fall back to the case severity."""
        return self.severity_ai if self.severity_ai is not None else self.severity_score_kasus

    @property
    def inspeksi_lapangan(self):
        """Latest inspection that recorded a field damage level, or None (PRD 5.3 BR-2)."""
        dengan_tingkat = [i for i in self.inspeksi_list if i.severity_lapangan is not None]
        return dengan_tingkat[-1] if dengan_tingkat else None

    @property
    def severity_lapangan(self):
        ins = self.inspeksi_lapangan
        return ins.severity_lapangan if ins else None

    @property
    def jadwal_lanjutan_aktif(self):
        """The single active follow-up visit of a temporary repair (PRD 5.3, decision 5.9 no. 7), or None."""
        aktif = [p for p in self.perbaikan_list if p.status_jadwal == JADWAL_AKTIF]
        return max(aktif, key=lambda p: (p.waktu is None, p.waktu, p.id_perbaikan), default=None) if aktif else None

    @property
    def laporan_pembuka(self):
        """The report that opened the ticket (earliest), or None."""
        return min(self.laporan_list, key=lambda l: (l.tanggal_lapor is None, l.tanggal_lapor, l.id_laporan),
                   default=None)

    @property
    def dari_temuan(self) -> bool:
        """Opened by a Penilik Jalan's finding (PRD 5.3), not by a citizen."""
        pembuka = self.laporan_pembuka
        return bool(pembuka and pembuka.dari_temuan)

    @property
    def rekomendasi_tutup_tertunda(self):
        """The latest inspection when it recommends closing and the Admin has not decided yet
        (PRD 5.3 BR-4 door b). While pending, no SPK can be issued."""
        terakhir = self.inspeksi_list[-1] if self.inspeksi_list else None
        if terakhir and terakhir.rekomendasi_tutup and not terakhir.keputusan_rekomendasi:
            return terakhir
        return None


# Follow-up visit schedule states (Sprint 3, PRD 5.3 "Kunjungan lanjutan")
JADWAL_AKTIF = "Aktif"
JADWAL_DIGANTI = "Diganti"
JADWAL_TERCATAT = "Tercatat"

# Source of a report (Sprint 3, PRD 5.3 "Temuan baru")
SUMBER_WARGA = "Warga"
SUMBER_TEMUAN = "Temuan Penilik"


class Laporan(Base):
    __tablename__ = "laporan"
    id_laporan = Column(String(20), primary_key=True, index=True)
    id_work_order = Column(String(20), ForeignKey("work_order.id_work_order"), nullable=True)
    # Sprint 3 (team decision 5.9 no. 3): NULL for a finding recorded by a Penilik Jalan.
    id_warga = Column(String(20), ForeignKey("warga.id_warga"), nullable=True)
    id_wilayah = Column(String(20), ForeignKey("wilayah.id_wilayah"), nullable=True)
    # "Warga" (citizen report) or "Temuan Penilik" (found by an inspector during field work)
    sumber = Column(String(20), default=SUMBER_WARGA)
    id_penilik_pencatat = Column(String(20), ForeignKey("penilik_jalan.id_penilik"), nullable=True)

    deskripsi = Column(Text, nullable=False)
    url_foto = Column(String(255), nullable=False)
    lokasi_teks = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    severity_score = Column(Float, default=0.0)
    status = Column(String(30), default="Dilaporkan")
    tanggal_lapor = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Real detection boxes from the AI analysis when the report was sent (JSON list of
    # {kategori, confidence, x1, y1, x2, y2}, normalised 0-1). NULL for old reports and for
    # the simulation backend, which has no boxes.
    kotak_deteksi = Column(Text, nullable=True)
    # Sprint 3 (PRD 5.3 BR-1): valid photo on which the AI found no damage (or a non-road
    # object). The report is accepted; an officer reviews it manually at verification.
    perlu_tinjauan_manual = Column(Boolean, default=False)

    work_order = relationship("WorkOrder", back_populates="laporan_list")
    warga = relationship("Warga", back_populates="laporan_list")
    wilayah = relationship("Wilayah", back_populates="laporan_list")
    inspeksi_list = relationship("Inspeksi", back_populates="laporan")
    notifikasi_list = relationship("Notifikasi", back_populates="laporan")
    rating = relationship("Rating", back_populates="laporan", uselist=False)
    penilik_pencatat = relationship("PenilikJalan", viewonly=True)

    @property
    def dari_temuan(self) -> bool:
        return self.sumber == SUMBER_TEMUAN

    @property
    def label_pelapor(self) -> str:
        """Who reported it, for staff pages: the citizen's name, or "Temuan Penilik: <name>"."""
        if self.dari_temuan:
            return f"{SUMBER_TEMUAN}: {self.penilik_pencatat.nama_penilik if self.penilik_pencatat else '-'}"
        return self.warga.nama_warga if self.warga else "-"

    @property
    def daftar_kotak(self) -> list[dict]:
        """Saved detection boxes, validated; [] when there are none or the data is unreadable."""
        try:
            data = json.loads(self.kotak_deteksi) if self.kotak_deteksi else []
        except (TypeError, ValueError):
            return []
        hasil = []
        for k in data if isinstance(data, list) else []:
            try:
                kotak = {"kategori": str(k["kategori"]), "confidence": float(k["confidence"]),
                         **{s: min(1.0, max(0.0, float(k[s]))) for s in ("x1", "y1", "x2", "y2")}}
            except (KeyError, TypeError, ValueError):
                continue
            if kotak["x2"] > kotak["x1"] and kotak["y2"] > kotak["y1"]:
                hasil.append(kotak)
        return hasil

class Inspeksi(Base):
    __tablename__ = "inspeksi"
    id_inspeksi = Column(String(20), primary_key=True, index=True)
    id_laporan = Column(String(20), ForeignKey("laporan.id_laporan"), nullable=False)
    id_penilik = Column(String(20), ForeignKey("penilik_jalan.id_penilik"), nullable=False)
    id_work_order = Column(String(20), ForeignKey("work_order.id_work_order"), nullable=True)
    dimensi_kerusakan = Column(String(50), nullable=True)
    rekomendasi_penanganan = Column(String(50), nullable=True)
    hasil_temuan = Column(Text, nullable=False)  # catatan teknis penilik
    url_foto_temuan = Column(String(255), nullable=True)
    # Sprint 3 (PRD 5.3 BR-2): category confirmed on site and field damage level
    # (Ringan/Sedang/Berat/Sangat Berat = severity 3/5/7/9) that replaces the AI severity.
    kategori_terkonfirmasi = Column(String(50), nullable=True)
    tingkat_kerusakan = Column(String(20), nullable=True)
    severity_lapangan = Column(Float, nullable=True)
    # Sprint 3 (PRD 5.3 BR-4 door b): the inspector recommends closing the ticket, with a reason;
    # the Admin then confirms ("Dikonfirmasi" -> Ditutup) or rejects it ("Ditolak" -> SPK).
    rekomendasi_tutup = Column(Boolean, default=False)
    alasan_rekomendasi = Column(String(50), nullable=True)
    keputusan_rekomendasi = Column(String(20), nullable=True)
    diputuskan_oleh = Column(String(100), nullable=True)
    tanggal_inspeksi = Column(Date, default=date.today)

    laporan = relationship("Laporan", back_populates="inspeksi_list")
    penilik = relationship("PenilikJalan", back_populates="inspeksi_list")

class Perbaikan(Base):
    __tablename__ = "perbaikan"
    id_perbaikan = Column(String(20), primary_key=True, index=True)
    id_work_order = Column(String(20), ForeignKey("work_order.id_work_order"), nullable=False)
    status_perbaikan = Column(String(30), nullable=False)
    catatan = Column(Text, nullable=True)
    foto_sesudah = Column(String(255), nullable=True)
    # Sprint 3 (PRD 5.3 "Kunjungan lanjutan", CO-3): planned follow-up visit date (ISO YYYY-MM-DD)
    # of a temporary repair. A work plan, NOT a deadline (no completion-time target).
    jadwal_lanjutan = Column(String(50), nullable=True)
    tanggal_selesai = Column(DateTime, nullable=True)
    dicatat_oleh = Column(String(50), nullable=True)
    waktu = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    perbaikan_sementara = Column(Boolean, default=False)
    # Schedule state: "Aktif" (one per ticket at most), "Diganti" (rescheduled), "Tercatat" (visit recorded)
    status_jadwal = Column(String(20), nullable=True)
    kunjungan_dicatat_pada = Column(DateTime, nullable=True)
    catatan_kunjungan = Column(Text, nullable=True)
    foto_kunjungan = Column(String(255), nullable=True)

    work_order = relationship("WorkOrder", back_populates="perbaikan_list")

    @property
    def tanggal_lanjutan(self):
        """The follow-up visit date as a date, or None (empty or unreadable)."""
        try:
            return date.fromisoformat((self.jadwal_lanjutan or "").strip()[:10])
        except ValueError:
            return None

    @property
    def jadwal_tampil(self) -> str:
        tanggal = self.tanggal_lanjutan
        return tanggal.strftime("%d/%m/%Y") if tanggal else (self.jadwal_lanjutan or "-")

class Notifikasi(Base):
    __tablename__ = "notifikasi"
    id_notifikasi = Column(String(20), primary_key=True, index=True)
    id_laporan = Column(String(20), ForeignKey("laporan.id_laporan"), nullable=False)
    id_warga = Column(String(20), ForeignKey("warga.id_warga"), nullable=False)
    judul = Column(String(100), nullable=True)
    pesan = Column(Text, nullable=False)
    status_baca = Column(Boolean, default=False)
    waktu_kirim = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # DEPRECATED: the "Notifikasi Gagal" / "Kirim Ulang" feature (old BR-8) was removed by the team.
    # The app no longer writes or reads these columns; they are kept only so existing databases
    # need no risky migration (jumlah_percobaan is NOT NULL, so its default stays).
    status_kirim = Column(String(20), default="Terkirim")
    jumlah_percobaan = Column(Integer, default=0, nullable=False)
    waktu_percobaan_terakhir = Column(DateTime, nullable=True)

    laporan = relationship("Laporan", back_populates="notifikasi_list")
    warga = relationship("Warga", back_populates="notifikasi_list")

class Rating(Base):
    __tablename__ = "rating"
    id_rating = Column(String(20), primary_key=True, index=True)
    id_laporan = Column(String(20), ForeignKey("laporan.id_laporan"), unique=True, nullable=False)
    nilai_bintang = Column(Integer, nullable=False)
    komentar = Column(Text, nullable=True)
    tanggal_rating = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    laporan = relationship("Laporan", back_populates="rating")


class RiwayatStatus(Base):
    """Status history of a Work Order: the timeline shown to citizens (UC-C)."""
    __tablename__ = "riwayat_status"
    id_riwayat = Column(Integer, primary_key=True, autoincrement=True)
    id_work_order = Column(String(20), ForeignKey("work_order.id_work_order"), nullable=False, index=True)
    status = Column(String(30), nullable=False)
    keterangan = Column(Text, nullable=True)
    aktor = Column(String(50), nullable=True)
    waktu = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    work_order = relationship("WorkOrder", back_populates="riwayat_list")
