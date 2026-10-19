Feature: Viewing the Infrastructure Priority Dashboard
  In order to memantau sebaran dan prioritas kerusakan infrastruktur secara menyeluruh
  As a Admin
  I want to melihat dashboard prioritas infrastruktur

  Scenario: Monitoring the Damage Distribution Map
    Given I see 245 active Work Orders in the system
    When I open the "/Dashboard" page
    Then I see a damage distribution map with color gradation according to severity
    And I see a list of tickets sorted from highest Risk Score, "REP-2026-00341 (8.4)"

  Scenario: Filter Produces No Data
    Given I apply the filter "Wilayah: Wonokromo, Status: Selesai, Kategori: Drainase"
    Then I see the message "Tidak ada laporan sesuai filter"
