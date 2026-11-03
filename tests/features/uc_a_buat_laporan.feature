Feature: Reporting Road Damage
  In order to kondisi jalan rusak di lingkungan saya segera ditangani oleh dinas terkait
  As a Warga
  I want to membuat laporan kerusakan jalan dengan mengunggah foto, lokasi, dan deskripsi

  Scenario: Valid Report Successfully Submitted
    Given I am logged in and on the "Buat Laporan" page
    When I upload a road damage photo "jalan_berlubang_dharmawangsa.jpg" (size 2.4MB)
    And I select the location "Jl. Dharmawangsa No. 20, Surabaya" via GPS
    And I see the AI category recommendation "Jalan Berlubang" and keep it as is
    And I enter the description "Lubang besar di tengah jalan membahayakan pengendara motor"
    And I press the "Kirim Laporan" button
    Then I receive a new ticket number with initial status "Dilaporkan"

  Scenario: Photo Fails Format or Size Validation
    Given I am on the "Buat Laporan" page
    When I upload a file with size 15MB or in ".pdf" format
    Then I see the error message "Format harus JPG/PNG dan ukuran maksimal 10MB"
    And I cannot proceed to the next step

  Scenario: Photo Does Not Contain a Road Damage Object
    Given I am on the "Buat Laporan" page
    When I upload a photo that does not show road damage, such as "kucing.jpg"
    Then I see the warning "Objek jalan rusak tidak terdeteksi, silakan ambil ulang foto"
    And my report is not saved

  Scenario: Report Detected as a Duplicate
    Given there is already an active report "REP-2026-00298" at "Jl. Sudirman No. 45" with category "Jalan Berlubang"
    When I submit a new report at the same location with a similar description
    Then my report is merged into ticket "REP-2026-00298" and its exposure count increases by 1
    And I receive the notification "Laporan Anda telah digabungkan dengan laporan serupa yang sudah aktif (REP-2026-00298)"
