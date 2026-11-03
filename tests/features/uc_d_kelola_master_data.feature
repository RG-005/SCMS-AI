Feature: UC-D Manage Region and Road Inspector Master Data
  As a PUPR Admin
  I want to manage Rayon Region master data and Road Inspector data
  So that every road damage report can be distributed to the correct rayon and officer

  Scenario: Admin successfully adds a new Road Inspector data (Happy Path)
    Given the admin opens the "Data Master (Wilayah & Penilik Jalan)" page
    When the admin inputs NIP "199005122022031005", name "Budi Santoso", and selects region "Wilayah Gubeng"
    And the admin clicks the "Simpan Data" button
    Then the system saves the new Road Inspector data to the database
    And the system displays a confirmation message "Data master berhasil diperbarui"

  Scenario: Failed to save due to duplicate NIP or Region Code (Negative Path)
    Given the admin opens the "Data Master (Wilayah & Penilik Jalan)" page
    And NIP "198501012015021001" is already registered in the system
    When the admin enters NIP "198501012015021001" on the add Road Inspector form
    And the admin clicks the "Simpan Data" button
    Then the system rejects saving the master data
    And the system displays an error message "Kode Wilayah atau NIP Penilik Jalan sudah terdaftar di sistem"
