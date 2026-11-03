Feature: UC-E Record Field Inspection by Road Inspector
  As a PUPR Road Inspector assigned to a specific rayon area
  I want to record field physical survey results on reports with "Verified" status
  So that the PUPR Admin has valid technical field data before issuing a Work Order

  Scenario: Road Inspector successfully saves field inspection results (Happy Path)
    Given the road inspector opens report details for "LAP-2026-0001" with status "Disetujui"
    When the road inspector inputs damage dimensions "2m x 1.5m x 0.15m"
    And the road inspector inputs technical notes "Lapisan aspal terkelupas dan tergenang air"
    And the road inspector selects treatment recommendation "Tambal Hotmix" and uploads survey photo "survei_0001.jpg"
    And the road inspector clicks the "Simpan Hasil Inspeksi" button
    Then the system saves the data to the Inspection table
    And the system updates the report status of "LAP-2026-0001" to "Terinspeksi"
    And the system generates an automatic notification for the reporting citizen

  Scenario: Incomplete inspection form upon submission (Negative Path)
    Given the road inspector opens report details for "LAP-2026-0001" with status "Disetujui"
    When the road inspector leaves mandatory fields like damage dimensions or recommendations blank
    And the road inspector clicks the "Simpan Hasil Inspeksi" button
    Then the system aborts saving the inspection data
    And the system displays a warning message "Lengkapi dimensi kerusakan dan rekomendasi teknis penanganan"
