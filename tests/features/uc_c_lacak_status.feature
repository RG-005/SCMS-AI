Feature: UC-C Track Citizen Report Status
  As a citizen of Surabaya who has reported road damage
  I want to track the status and progress history of my report
  So that I can transparently know the progress of the road repair

  Scenario: Citizen successfully views report progress and timeline (Happy Path)
    Given the citizen has accessed the "Riwayat & Lacak Laporan" page
    And a registered report with ID "LAP-2026-0001" exists for the citizen
    When the citizen searches for report ID "LAP-2026-0001"
    Then the system displays the report details along with the AI severity score and priority level
    And the system displays the current progress timeline for report "LAP-2026-0001"

  Scenario: Report ticket ID not found (Negative Path)
    Given the citizen is on the report tracking page
    When the citizen enters unregistered report ID "LAP-9999-XXXX"
    Then the system rejects the search
    And the system displays an error message "Nomor tiket laporan tidak ditemukan, periksa kembali ID Laporan Anda"
