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
    severity_score_kasus = Column(Float, default=0.0)
    exposure_count = Column(Integer, default=1)
    vulnerability_score = Column(Float, default=1.0)
    kelas_jalan = Column(String(15), default="Utama")
    risk_score = Column(Float, default=0.0)
    prioritas = Column(String(20), default="Sedang")
    status_work_order = Column(String(30), default="Dilaporkan")
    sla_rekomendasi = Column(String(30), default="24 jam")
    log_keputusan = Column(Text, nullable=True)
    tanggal_ditugaskan = Column(Date, nullable=True)
    nomor_spk = Column(String(50), unique=True, nullable=True)
    tim_pelaksana = Column(String(100), nullable=True)
    tanggal_selesai = Column(DateTime, nullable=True)

    admin = relationship("Admin", back_populates="work_orders")
    penilik = relationship("PenilikJalan", back_populates="work_orders")
    laporan_list = relationship("Laporan", back_populates="work_order")
    perbaikan_list = relationship("Perbaikan", back_populates="work_order")
    riwayat_list = relationship("RiwayatStatus", back_populates="work_order", order_by="RiwayatStatus.waktu")

class Laporan(Base):
    __tablename__ = "laporan"
    id_laporan = Column(String(20), primary_key=True, index=True)
    id_work_order = Column(String(20), ForeignKey("work_order.id_work_order"), nullable=True)
    id_warga = Column(String(20), ForeignKey("warga.id_warga"), nullable=False)
    id_wilayah = Column(String(20), ForeignKey("wilayah.id_wilayah"), nullable=True)
    
    deskripsi = Column(Text, nullable=False)
    url_foto = Column(String(255), nullable=False)
    lokasi_teks = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    severity_score = Column(Float, default=0.0)
    status = Column(String(30), default="Dilaporkan")
    tanggal_lapor = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    work_order = relationship("WorkOrder", back_populates="laporan_list")
    warga = relationship("Warga", back_populates="laporan_list")
    wilayah = relationship("Wilayah", back_populates="laporan_list")
    inspeksi_list = relationship("Inspeksi", back_populates="laporan")
    notifikasi_list = relationship("Notifikasi", back_populates="laporan")
    rating = relationship("Rating", back_populates="laporan", uselist=False)

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
    jadwal_lanjutan = Column(String(50), nullable=True)
    tanggal_selesai = Column(DateTime, nullable=True)
    dicatat_oleh = Column(String(50), nullable=True)
    waktu = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    work_order = relationship("WorkOrder", back_populates="perbaikan_list")

class Notifikasi(Base):
    __tablename__ = "notifikasi"
    id_notifikasi = Column(String(20), primary_key=True, index=True)
    id_laporan = Column(String(20), ForeignKey("laporan.id_laporan"), nullable=False)
    id_warga = Column(String(20), ForeignKey("warga.id_warga"), nullable=False)
    judul = Column(String(100), nullable=True)
    pesan = Column(Text, nullable=False)
    status_baca = Column(Boolean, default=False)
    status_kirim = Column(String(20), default="Terkirim")
    waktu_kirim = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
