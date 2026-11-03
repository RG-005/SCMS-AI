Feature: UC-F Update Field Repair Status (Work Order)
  As a PUPR Admin or Field Execution Team
  I want to issue a Work Order and update the road repair progress status up to Completed
  So that the road damage handling cycle is recorded thoroughly and accountably

  Scenario: Issuing a Work Order and updating status to Processing (Happy Path)
    Given report "LAP-2026-0001" has the status "Terinspeksi"
    When the admin issues a Work Order with SPK number "SPK/PUPR/XI/2026/001" and team "Satgas Rayon Gubeng"
    And the admin selects the progress status "Dalam Proses"
    Then the system saves the data to the WorkOrder table
    And the system updates the status of report "LAP-2026-0001" to "Dalam Proses"
    And the system sends a status update notification to the reporting citizen

  Scenario: Completing road repair with completion proof photo upload (Happy Path)
    Given report "LAP-2026-0001" is in "Dalam Proses" status on the active Work Order list
    When the officer selects progress status "Selesai"
    And the officer inputs completion notes "Lubang sudah ditambal aspal hotmix dan dipadatkan"
    And the officer uploads repair proof photo "selesai_0001.jpg"
    And the officer clicks the "Perbarui Status Penanganan" button
    Then the system updates the WorkOrder status and report status of "LAP-2026-0001" to "Selesai"
    And the system sends a completion notification to the reporting citizen

  Scenario: Updating status to Completed without repair proof photo (Negative Path)
    Given report "LAP-2026-0001" is in "Dalam Proses" status on the active Work Order list
    When the officer selects progress status "Selesai" without uploading a repair proof photo file
    And the officer clicks the "Perbarui Status Penanganan" button
    Then the system rejects the WorkOrder status update
    And the system displays an error message "Foto bukti penyelesaian perbaikan wajib diunggah untuk menutup laporan"
