# Sprint 3 — backlog 4: Integrasi dan Pengujian BDD Seluruh Fitur (PRD bagian 5.2).
# Satu tiket dibawa melewati semua aktor dan status lewat rute web yang sama dengan yang dipakai
# pengguna (login sungguhan per aktor, form POST, halaman dan endpoint JSON), tanpa menyiapkan status
# langsung di database. Step definition: tests/step_definitions/test_integrasi_alur_penuh.py.
#
# Data seed yang dipakai: warga 0812xxxxxxx (USR-01), Admin, Kepala Bidang, Penilik Jalan Budi Santoso
# (Wilayah Gubeng, Tersedia). Lokasi laporan baru dipilih jauh (> 1 km) dari tiket seed agar tidak
# digabung oleh deduplikasi BR-3. Laporan Kinerja dibaca untuk periode hari ini (WIB), sehingga hanya
# tiket baru dari skenario yang terhitung (tiket seed berasal dari Oktober 2026).

@sprint3
Feature: Sprint 3 Integration - Full Ticket Lifecycle Across All Actors
  As the SCMS-AI team
  I want one ticket to go through every actor and status using the real web routes
  So that the Sprint 1, 2 and 3 features are shown to work together

  Scenario: A citizen report goes from submission to rating (Happy Path)
    Given the demo data is loaded
    When the citizen "0812xxxxxxx" submits a report with photo "jalan_berlubang_integrasi.jpg" at "Jl. Kalijudan No. 99, Surabaya"
    Then a new ticket is created with status "Dilaporkan" and priority "Tinggi"
    And the citizen sees the unread notification count go up by 1
    When the admin approves the new ticket
    Then the ticket status is "Disetujui"
    When the admin assigns road inspector "Budi Santoso" to the new ticket
    Then the ticket status is "Ditugaskan"
    When the inspector saves the inspection with damage level "Sedang" and recommendation "Tambal Hotmix"
    Then the ticket status is "Terinspeksi" and its Risk Score is recalculated to 5.5 "Borderline"
    When the admin issues SPK "SPK/PUPR/XI/2026/099" to team "Satgas Rayon Gubeng"
    Then the ticket status is "Dalam Proses"
    When the inspector completes the repair with a proof photo
    Then the ticket status is "Selesai"
    And the citizen's timeline shows every stage as done
    And the citizen received exactly one notification for each status change
    And every notification is listed on the citizen's notification page
    When the citizen rates the repair 5 stars with review "Cepat dan rapi"
    Then the rating is saved and the report can no longer be rated
    And the performance report for today counts 1 incoming and 1 completed ticket in its charts and tables

  Scenario: A rejected report is closed with a reason (Negative Path)
    Given the demo data is loaded
    When the citizen "0812xxxxxxx" submits a report with photo "jalan_retak_integrasi.jpg" at "Jl. Kertajaya Indah No. 7, Surabaya"
    Then a new ticket is created with status "Dilaporkan" and priority "Borderline"
    When the admin rejects the new ticket with reason "Di luar kewenangan DPUPR"
    Then the ticket status is "Ditutup"
    And the citizen's newest notification mentions "Di luar kewenangan DPUPR"
    And the citizen cannot rate the closed report
    And the performance report for today lists the ticket under closed reason "Di luar kewenangan DPUPR" without charts
