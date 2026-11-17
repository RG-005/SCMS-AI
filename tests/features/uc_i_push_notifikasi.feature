# Sprint 3 — backlog 2: push notification versi sederhana (PRD bagian 5.2, tanpa Web Push/VAPID).
# Dihubungkan ke step definition di tests/step_definitions/test_uc_i_push_notifikasi.py (Sprint 3).
#
# Data seed yang dipakai (sudah ada):
#   - Warga 0812xxxxxxx (USR-01) dengan 1 notifikasi belum dibaca (NTF-SEED-0001, LAP-2026-0001).
#   - REP-2026-00341 / LAP-2026-0001 "Disetujui", Budi Santoso "Tersedia".
# Konfigurasi baru: interval polling bisa diperkecil untuk tes (mis. env SCMS_POLL_NOTIF_DETIK, bawaan 15).
# Endpoint baru: GET /api/notifikasi/belum-dibaca -> {"jumlah": n, "terbaru": [...]} (hanya Warga).
# DOM ID tetap: #badgeNotif, #menuNotifikasi. DOM ID baru: #toastNotif.

@sprint3
Feature: UC-I Live Notification Badge and In-page Toast
  As a Reporting Citizen
  I want the notification badge and a toast to appear without refreshing the page
  So that I know right away when my report status changes

  Scenario: Badge and toast update without refreshing the page (Happy Path)
    Given the citizen "0812xxxxxxx" is on the "Beranda" page with notification badge "1"
    When the admin assigns road inspector "Budi Santoso" to ticket "REP-2026-00341"
    Then within one polling interval the notification badge shows "2" without a page reload
    And a toast containing "LAP-2026-0001" appears on the page

  Scenario: Browser notification is shown when the citizen grants permission (Happy Path)
    Given the citizen "0812xxxxxxx" is on the "Beranda" page
    And the browser notification permission is "granted"
    When the admin assigns road inspector "Budi Santoso" to ticket "REP-2026-00341"
    Then within one polling interval a browser notification with title "Status laporan LAP-2026-0001 diperbarui" is shown

  Scenario: Permission denied falls back to the in-page toast only (Negative Path)
    Given the citizen "0812xxxxxxx" is on the "Beranda" page
    And the browser notification permission is "denied"
    When the admin assigns road inspector "Budi Santoso" to ticket "REP-2026-00341"
    Then within one polling interval a toast containing "LAP-2026-0001" appears on the page
    And no browser notification is shown and no script error is logged

  Scenario: Unread-count endpoint is only for the logged-in citizen (Negative Path)
    Given I am not logged in
    When I request the unread notification count endpoint
    Then the response status is 401 and contains no notification data
    When the admin requests the unread notification count endpoint
    Then the response status is 403
