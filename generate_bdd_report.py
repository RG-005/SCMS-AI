"""Membuat reports/cucumber_bdd_report.html dari reports/cucumber.json.

cucumber.json dihasilkan pytest-bdd:
    python -m pytest tests/step_definitions --cucumberjson=reports/cucumber.json ...
Fitur dikelompokkan per sprint: fitur bertag `@sprint3` masuk Sprint 3 (fitur Sprint 3 memakai
kode use case yang sama dengan sprint sebelumnya, mis. uc_a_tinjauan_manual), fitur lain menurut
kode use case di nama berkas `tests/features/uc_<kode>_*.feature`.
"""
import json
import os
import re
from datetime import datetime

os.makedirs("reports", exist_ok=True)

# Kode use case per sprint (urutan = urutan tampil di laporan).
SPRINT_UC = {
    "Sprint 1": ["K", "A", "B", "G", "H"],
    "Sprint 2": ["C", "D", "E", "F", "I", "J", "L"],
    # Sprint 3 is chosen by the @sprint3 tag; this list is only the order and the header text.
    "Sprint 3": ["A", "B", "E", "F", "I", "L", "Integrasi"],
}
TAG_SPRINT = {"sprint3": "Sprint 3"}


def kode_uc(feat):
    """'features/uc_k_login.feature' -> 'K'; 'features/integrasi_*.feature' -> 'Integrasi'; else None."""
    uri = feat.get("uri", "").replace("\\", "/").lower()
    m = re.search(r"uc_([a-z])_", uri)
    if m:
        return m.group(1).upper()
    return "Integrasi" if "/integrasi_" in uri or uri.startswith("integrasi_") else None


def tag_fitur(feat):
    return {str(t.get("name", "")).lstrip("@").lower() for t in feat.get("tags", []) or []}


def sprint_dari(feat):
    for tag, sprint in TAG_SPRINT.items():
        if tag in tag_fitur(feat):
            return sprint
    kode = kode_uc(feat)
    for sprint, daftar in SPRINT_UC.items():
        if sprint not in TAG_SPRINT.values() and kode in daftar:
            return sprint
    return "Lainnya"


def urutan_fitur(feat):
    kode = kode_uc(feat)
    sprint = sprint_dari(feat)
    daftar_sprint = list(SPRINT_UC) + ["Lainnya"]
    kode_sprint = SPRINT_UC.get(sprint, [])
    posisi = kode_sprint.index(kode) if kode in kode_sprint else 99
    return (daftar_sprint.index(sprint), posisi, feat.get("uri", ""))


def status_step(st):
    return st.get("result", {}).get("status", "passed").lower()


def skenario_lulus(sc):
    return all(status_step(st) == "passed" for st in sc.get("steps", []))


def ringkas(features):
    """Jumlah fitur, skenario, step (total & passed) untuk sekumpulan fitur."""
    r = {"fitur": len(features), "skenario": 0, "skenario_lulus": 0, "step": 0, "step_lulus": 0}
    for feat in features:
        for el in feat.get("elements", []):
            if el.get("type") != "scenario":
                continue
            r["skenario"] += 1
            r["skenario_lulus"] += skenario_lulus(el)
            for st in el.get("steps", []):
                r["step"] += 1
                r["step_lulus"] += status_step(st) == "passed"
    return r


def build_cucumber_html(json_path="reports/cucumber.json", out_path="reports/cucumber_bdd_report.html"):
    if not os.path.exists(json_path):
        print(f"File {json_path} belum ditemukan. Jalankan pytest terlebih dahulu.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        features = json.load(f)

    features = sorted(features, key=urutan_fitur)
    total = ringkas(features)
    total_scenarios = total["skenario"]
    passed_scenarios = total["skenario_lulus"]
    total_steps = total["step"]
    passed_steps = total["step_lulus"]
    persen = round(100 * passed_scenarios / total_scenarios) if total_scenarios else 0
    warna_bar = "bg-emerald-500" if passed_scenarios == total_scenarios else "bg-red-500"

    per_sprint = {}
    for feat in features:
        per_sprint.setdefault(sprint_dari(feat), []).append(feat)

    now_str = datetime.now().strftime("%d %B %Y, %H:%M:%S WIB")

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BDD Cucumber Test Report - SCMS-AI Dinas PUPR Surabaya</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; }}</style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen pb-16">
    <!-- BAR PERSENTASE HIJAU ALA CUCUMBER -->
    <div class="w-full {warna_bar} text-slate-950 font-extrabold text-xs py-2 px-6 text-center uppercase tracking-wider shadow">
        {persen}% PASSED &bull; {passed_scenarios} / {total_scenarios} Scenarios ({passed_steps} / {total_steps} Steps) Executed via Selenium WebDriver &amp; SQLite (scms_test.db)
    </div>

    <div class="max-w-5xl mx-auto px-6 pt-8">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6 mb-8">
            <div>
                <span class="text-[11px] font-bold uppercase tracking-widest text-blue-400">Dokumentasi Pengujian Otomatis (BDD &amp; E2E Selenium)</span>
                <h1 class="text-2xl font-extrabold text-white mt-1">SCMS-AI Dinas PUPR Kota Surabaya — Sprint 1 &amp; Sprint 2</h1>
                <p class="text-xs text-slate-400 mt-1">Kelompok 7 &bull; Runtime: Python FastAPI + SQLAlchemy + SQLite (DB uji terpisah) + pytest-bdd + Selenium</p>
            </div>
            <div class="bg-slate-800/90 border border-slate-700 rounded-xl px-4 py-3 text-right">
                <p class="text-[11px] text-slate-400">Waktu Eksekusi</p>
                <p class="text-xs font-bold text-emerald-400">{now_str}</p>
            </div>
        </div>

        <!-- RINGKASAN METRIK -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Total Fitur (Use Case)</p>
                <p class="text-2xl font-extrabold text-white mt-1">{len(features)} Fitur</p>
            </div>
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Skenario Gherkin</p>
                <p class="text-2xl font-extrabold text-emerald-400 mt-1">{passed_scenarios} Passed</p>
            </div>
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Total Langkah (Steps)</p>
                <p class="text-2xl font-extrabold text-blue-400 mt-1">{passed_steps} Steps</p>
            </div>
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Status Kegagalan</p>
                <p class="text-2xl font-extrabold text-slate-300 mt-1">{total_scenarios - passed_scenarios} Failed</p>
            </div>
        </div>

        <!-- RINGKASAN PER SPRINT -->
        <div id="ringkasanSprint" class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
"""
    for sprint, daftar in per_sprint.items():
        r = ringkas(daftar)
        kode = ", ".join(("UC-" + k if len(k) == 1 else k) for k in (SPRINT_UC.get(sprint) or []))
        warna = "text-emerald-400" if r["skenario_lulus"] == r["skenario"] else "text-red-400"
        html += f"""
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4" data-sprint="{sprint}">
                <div class="flex items-center justify-between">
                    <p class="text-sm font-extrabold text-white">{sprint}</p>
                    <span class="text-[11px] font-bold {warna}">{r["skenario_lulus"]} / {r["skenario"]} Passed</span>
                </div>
                <p class="text-[11px] text-slate-400 mt-1">{kode}</p>
                <p class="text-xs text-slate-300 mt-2">{r["fitur"]} Fitur &bull; {r["skenario"]} Skenario &bull; {r["step_lulus"]} / {r["step"]} Steps</p>
            </div>
"""
    html += """
        </div>

        <!-- DAFTAR FITUR & SKENARIO -->
        <div class="space-y-4">
"""

    sprint_sebelumnya = None
    for feat in features:
        sprint = sprint_dari(feat)
        if sprint != sprint_sebelumnya:
            r = ringkas(per_sprint[sprint])
            html += f"""
            <h2 class="text-xs font-bold uppercase tracking-widest text-blue-400 pt-4">{sprint} &bull; {r["fitur"]} Fitur &bull; {r["skenario"]} Skenario &bull; {r["step"]} Steps</h2>
"""
            sprint_sebelumnya = sprint
        feat_name = feat.get("name", "Feature")
        feat_uri = feat.get("uri", "")
        scenarios = [el for el in feat.get("elements", []) if el.get("type") == "scenario"]
        if all(skenario_lulus(sc) for sc in scenarios):
            lencana = ("bg-emerald-500/20 text-emerald-400 border-emerald-500/30", "PASSED")
        else:
            lencana = ("bg-red-500/20 text-red-400 border-red-500/30", "FAILED")

        html += f"""
            <details open class="bg-slate-800/80 border border-slate-700 rounded-xl overflow-hidden">
                <summary class="cursor-pointer px-5 py-4 bg-slate-800 hover:bg-slate-750 flex items-center justify-between select-none">
                    <div class="flex items-center space-x-3">
                        <span class="px-2.5 py-1 rounded text-[11px] font-extrabold border {lencana[0]}">{lencana[1]}</span>
                        <div>
                            <h2 class="text-sm font-bold text-white"><span class="text-amber-400 font-extrabold">Feature:</span> {feat_name}</h2>
                            <p class="text-[11px] font-mono text-slate-400">{feat_uri}</p>
                        </div>
                    </div>
                    <span class="text-xs font-semibold text-slate-400">{len(scenarios)} Skenario</span>
                </summary>
                <div class="p-5 space-y-4 border-t border-slate-700/80">
"""
        for sc in scenarios:
            sc_name = sc.get("name", "Scenario")
            if skenario_lulus(sc):
                status_sc = '<span class="text-[11px] font-bold text-emerald-400">&#10004; PASSED</span>'
            else:
                status_sc = '<span class="text-[11px] font-bold text-red-400">&#10008; FAILED</span>'
            steps = sc.get("steps", [])
            html += f"""
                    <div class="bg-slate-900/90 border border-slate-700/80 rounded-lg p-4">
                        <div class="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
                            <h3 class="text-xs font-bold text-slate-100">
                                <span class="text-purple-400 font-extrabold">Scenario:</span> {sc_name}
                            </h3>
                            {status_sc}
                        </div>
                        <ul class="space-y-1.5 text-xs font-mono">
"""
            for st in steps:
                kw = st.get("keyword", "").strip()
                txt = st.get("name", "")
                if status_step(st) == "passed":
                    tanda = '<span class="text-emerald-400 mr-2">&#10003;</span>'
                else:
                    tanda = '<span class="text-red-400 mr-2">&#10007;</span>'
                dur_ns = st.get("result", {}).get("duration", 0)
                dur_ms = round(dur_ns / 1_000_000, 2) if dur_ns > 1000 else round(dur_ns * 1000, 2)
                html += f"""
                            <li class="flex items-start justify-between py-1 px-2 rounded bg-slate-800/50">
                                <div>
                                    {tanda}
                                    <span class="font-bold text-sky-400">{kw}</span>
                                    <span class="text-slate-200 ml-1">{txt}</span>
                                </div>
                                <span class="text-[10px] text-slate-400 ml-4 shrink-0">{dur_ms} ms</span>
                            </li>
"""
            html += """
                        </ul>
                    </div>
"""
        html += """
                </div>
            </details>
"""

    html += """
        </div>
    </div>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as out_f:
        out_f.write(html)
    print(f"Laporan BDD Cucumber HTML berhasil dibuat di: {out_path}")
    print(f"  {len(features)} fitur, {passed_scenarios}/{total_scenarios} skenario passed, "
          f"{passed_steps}/{total_steps} step passed")
    for sprint, daftar in per_sprint.items():
        r = ringkas(daftar)
        print(f"  {sprint}: {r['fitur']} fitur, {r['skenario_lulus']}/{r['skenario']} skenario, "
              f"{r['step_lulus']}/{r['step']} step")


if __name__ == "__main__":
    build_cucumber_html()