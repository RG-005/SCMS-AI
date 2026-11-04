Feature: UC-L Export Infrastructure Performance Report
  As a Head of Division (Kepala Bidang)
  I want to view and download the infrastructure handling performance recap
  So that I can evaluate SLA compliance and risk statistics per rayon region

  Scenario: Head of Division views and downloads the performance report (Happy Path)
    Given the head of division opens the "Laporan Kinerja Infrastruktur" page
    When the head of division selects the period "2026-10-01" to "2026-10-31" and region "Semua Wilayah"
    And the head of division clicks the "Tampilkan" button
    Then the system displays the performance recap for region "Wilayah Gubeng" with 4 tickets
    And the SLA status of ticket "REP-2026-00290" is "Terlambat"
    When the head of division downloads the "Unduh Rekap Wilayah (CSV)" file
    Then the downloaded CSV file contains the recap row of "Wilayah Gubeng"

  Scenario: No performance data in the selected period (Negative Path)
    Given the head of division opens the "Laporan Kinerja Infrastruktur" page
    When the head of division selects the period "2025-01-01" to "2025-01-31" and region "Semua Wilayah"
    And the head of division clicks the "Tampilkan" button
    Then the system displays the message "Tidak ada data kinerja pada periode yang dipilih"
    And the download buttons are not shown
