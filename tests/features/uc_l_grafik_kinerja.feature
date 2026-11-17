# Sprint 3 — backlog 3: grafik Laporan Kinerja dengan Chart.js (PRD bagian 5.2).
# Dihubungkan ke step definition di tests/step_definitions/test_uc_l.py (Sprint 3).
#
# Data seed yang dipakai (sudah ada), periode 2026-10-01 s.d. 2026-10-31:
#   - 5 tiket: Wilayah Gubeng 4 (REP-2026-00341, -00355, -00298, -00290), Wilayah Benowo 1 (REP-2026-00360).
#   - Prioritas: Urgent 2 (00341, 00298), Tinggi 2 (00360, 00290), Borderline 1 (00355), Rendah 0.
#   - Selesai 1 (REP-2026-00290).
# Data seed baru: untuk skenario "Ditutup", step definition menutup REP-2026-00341 lewat alur resmi,
#   atau seed opsional REP-2026-00370 (lihat uc_b_tutup_tiket.feature) berstatus "Ditutup".
# Data grafik dibaca dari atribut data-* / JSON di halaman (mis. #dataGrafikKinerja) agar bisa diuji tanpa canvas.

@sprint3
Feature: UC-L Performance Charts
  As a Head of Division (Kepala Bidang)
  I want to see the performance recap as charts that follow the period and region filter
  So that I can spot trends and bottlenecks faster than by reading tables

  Scenario: Charts show the same numbers as the tables (Happy Path)
    Given the head of division opens the "Laporan Kinerja Infrastruktur" page
    When the head of division selects the period "2026-10-01" to "2026-10-31" and region "Semua Wilayah"
    And the head of division clicks the "Tampilkan" button
    Then the charts "Tren Tiket Masuk vs Selesai per Minggu", "Distribusi Prioritas", "Rata-rata Durasi per Tahap" and "Rekap per Wilayah" are displayed
    And the "Distribusi Prioritas" chart shows "Urgent" 2, "Tinggi" 2, "Borderline" 1 and "Rendah" 0
    And the weekly trend chart totals 5 incoming and 1 completed tickets
    And every chart value equals the matching value in the recap tables

  Scenario: Charts follow the region filter (Happy Path)
    Given the head of division opens the "Laporan Kinerja Infrastruktur" page
    When the head of division selects the period "2026-10-01" to "2026-10-31" and region "Wilayah Benowo"
    And the head of division clicks the "Tampilkan" button
    Then the "Rekap per Wilayah" chart shows only "Wilayah Benowo" with 1 ticket
    And the "Distribusi Prioritas" chart shows "Tinggi" 1

  Scenario: Closed tickets are shown separately and not counted as completed (Alternative Path)
    Given ticket "REP-2026-00341" has been closed with reason "Laporan tidak valid"
    When the head of division shows the performance report for "2026-10-01" to "2026-10-31" and region "Semua Wilayah"
    Then the "Ditutup" section shows 1 ticket for reason "Laporan tidak valid"
    And the total ticket count is 4 and the completed count is still 1
    And the completion rate is calculated from 4 tickets, not 5
    And the "Distribusi Prioritas" chart shows "Urgent" 1, "Tinggi" 2, "Borderline" 1 and "Rendah" 0

  Scenario: Empty period shows no charts (Negative Path)
    Given the head of division opens the "Laporan Kinerja Infrastruktur" page
    When the head of division selects the period "2025-01-01" to "2025-01-31" and region "Semua Wilayah"
    And the head of division clicks the "Tampilkan" button
    Then the system displays the message "Tidak ada data kinerja pada periode yang dipilih"
    And no chart is displayed
