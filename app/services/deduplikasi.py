"""
Spatial-semantic deduplication (PRD BR-3).

A new report is merged into an existing Work Order only when ALL hold:
  1. the Work Order is still active (status is not "Selesai"),
  2. it has the same damage category,
  3. it is at the same spot:
       - both have coordinates  -> within RADIUS_DUPLIKAT_M metres, or
       - otherwise              -> same normalised street name + house number,
  4. the new description is similar enough to at least one report already in
     that Work Order (threshold depends on the NLP backend).
Among several matches the closest, most similar one wins.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Laporan, WorkOrder
from app.services.ai_service import AIService

RADIUS_DUPLIKAT_M = 50.0
STATUS_TIDAK_AKTIF = ("Selesai",)


@dataclass
class KandidatDuplikat:
    work_order: WorkOrder
    jarak_m: Optional[float]
    kemiripan: float


def jarak_meter(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normalisasi_alamat(alamat: str) -> str:
    """'Jl. Sudirman No. 45, Surabaya' -> 'sudirman 45' (street + number only)."""
    bagian = (alamat or "").split(",")[0].lower()
    bagian = re.sub(r"\b(jl|jln|jalan|no|nomor)\b\.?", " ", bagian)
    bagian = re.sub(r"[^a-z0-9]+", " ", bagian)
    return " ".join(bagian.split())


def _lokasi_sama(wo: WorkOrder, lokasi: str, lat: Optional[float], lng: Optional[float]) -> tuple[bool, Optional[float]]:
    if lat is not None and lng is not None and wo.latitude is not None and wo.longitude is not None:
        jarak = jarak_meter(lat, lng, wo.latitude, wo.longitude)
        return jarak <= RADIUS_DUPLIKAT_M, jarak
    alamat_baru = normalisasi_alamat(lokasi)
    return bool(alamat_baru) and alamat_baru == normalisasi_alamat(wo.lokasi_jalan), None


def cari_duplikat(
    db: Session,
    ai: AIService,
    kategori: str,
    lokasi: str,
    deskripsi: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Optional[KandidatDuplikat]:
    kandidat_aktif = db.query(WorkOrder).filter(
        WorkOrder.kategori_kerusakan == kategori,
        WorkOrder.status_work_order.notin_(STATUS_TIDAK_AKTIF),
    ).all()

    terbaik: Optional[KandidatDuplikat] = None
    for wo in kandidat_aktif:
        cocok, jarak = _lokasi_sama(wo, lokasi, latitude, longitude)
        if not cocok:
            continue
        laporan = db.query(Laporan).filter_by(id_work_order=wo.id_work_order).all()
        kemiripan = max((ai.kemiripan_deskripsi(deskripsi, lap.deskripsi or "") for lap in laporan), default=0.0)
        if kemiripan < ai.ambang_duplikat:
            continue
        kandidat = KandidatDuplikat(wo, jarak, kemiripan)
        if terbaik is None or (kandidat.kemiripan, -(jarak or 0.0)) > (terbaik.kemiripan, -(terbaik.jarak_m or 0.0)):
            terbaik = kandidat
    return terbaik
