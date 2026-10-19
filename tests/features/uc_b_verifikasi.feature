Feature: Verifying Damage Reports
  In order to memastikan hanya laporan valid yang diteruskan ke proses penugasan
  As a Admin
  I want to memverifikasi laporan kerusakan

  Scenario: Admin Approves a Ticket
    Given I open ticket "REP-2026-00341" with Risk Score "8.4 (Urgent)"
    When I press the "Setujui Tiket" button
    Then I see the ticket status change to "Disetujui"

  Scenario: Ticket with Ambiguous Risk Score
    Given I open ticket "REP-2026-00355" with Risk Score "5.1 (Borderline)"
    When I view the ticket detail
    Then I see the option "Butuh Verifikasi Lapangan"

  Scenario: Admin Assigns Additional Inspection
    Given I see ticket "REP-2026-00355" marked "Butuh Verifikasi Lapangan"
    When I select "Tugaskan Inspeksi Tambahan" and assign Penilik Jalan "Budi Santoso"
    Then I see the ticket status change to "Menunggu Inspeksi"

  Scenario: Admin Proceeds Without Additional Inspection
    Given I see ticket "REP-2026-00355" marked as ambiguous
    When I press the "Lanjutkan Tanpa Inspeksi" button
    Then I see my decision logged as "Log Keputusan Manual - admin@dpupr.surabaya.go.id"
