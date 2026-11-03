"""
Multi-Factor Risk Scoring Engine (PRD BR-2).

    Risk Score = clip(round(w_s*Severity + w_e*ln(Exposure + 1) + w_v*Vulnerability + w_c*Criticality, 1), 0.0, 10.0)

All inputs except Exposure are on a 0-10 scale. Exposure is the number of
citizen reports merged into the Work Order (>= 1). The log keeps exposure
from dominating: going from 1 to 10 reporters adds about 0.8 points.

The weights below are a starting point for the team to calibrate with the
Dinas; change them here and every new or merged ticket uses the new values.
"""
import math
from dataclasses import dataclass

BOBOT_SEVERITY = 0.50
BOBOT_EXPOSURE = 0.45
BOBOT_VULNERABILITY = 0.15
BOBOT_CRITICALITY = 0.25

# Criticality is derived from road class (kelas jalan): busier roads matter more.
CRITICALITY_KELAS_JALAN = {
    "Arteri Primer": 10.0,
    "Arteri Sekunder": 8.5,
    "Kolektor": 7.0,
    "Lokal": 5.0,
    "Lingkungan": 3.0,
}
KELAS_JALAN_DEFAULT = "Kolektor"

# Vulnerability (location: schools, hospitals, flood-prone, etc.) has no data
# source yet, so new reports get this neutral default until a field
# inspection or master data provides a real value.
VULNERABILITY_DEFAULT = 6.0


@dataclass(frozen=True)
class HasilRisiko:
    risk_score: float
    prioritas: str
    sla_rekomendasi: str


def criticality_dari_kelas(kelas_jalan: str) -> float:
    return CRITICALITY_KELAS_JALAN.get(kelas_jalan, CRITICALITY_KELAS_JALAN[KELAS_JALAN_DEFAULT])


def hitung_risk_score(severity: float, exposure: int, vulnerability: float, criticality: float) -> float:
    exposure = max(1, int(exposure or 1))
    nilai = (
        BOBOT_SEVERITY * float(severity or 0.0)
        + BOBOT_EXPOSURE * math.log(exposure + 1)
        + BOBOT_VULNERABILITY * float(vulnerability or 0.0)
        + BOBOT_CRITICALITY * float(criticality or 0.0)
    )
    return min(10.0, max(0.0, round(nilai, 1)))


def klasifikasi_prioritas(risk_score: float) -> tuple[str, str]:
    """Priority label and SLA thresholds from PRD BR-2 / design.md."""
    if risk_score >= 8.0:
        return "Urgent", "24 jam"
    if risk_score >= 6.0:
        return "Tinggi", "3x24 jam"
    if risk_score >= 4.0:
        return "Borderline", "48 jam"
    return "Rendah", "7x24 jam"


def nilai_risiko(severity: float, exposure: int, vulnerability: float, kelas_jalan: str) -> HasilRisiko:
    skor = hitung_risk_score(severity, exposure, vulnerability, criticality_dari_kelas(kelas_jalan))
    prioritas, sla = klasifikasi_prioritas(skor)
    return HasilRisiko(risk_score=skor, prioritas=prioritas, sla_rekomendasi=sla)


def terapkan_ke_work_order(wo) -> HasilRisiko:
    """Recompute and store risk score, priority and SLA on a WorkOrder."""
    hasil = nilai_risiko(wo.severity_score_kasus, wo.exposure_count, wo.vulnerability_score, wo.kelas_jalan)
    wo.risk_score = hasil.risk_score
    wo.prioritas = hasil.prioritas
    wo.sla_rekomendasi = hasil.sla_rekomendasi
    return hasil
