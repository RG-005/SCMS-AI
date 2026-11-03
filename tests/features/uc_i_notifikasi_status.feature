Feature: UC-I Report Status Notification
  As a Reporting Citizen
  I want to receive and view a list of notifications within the app whenever my report status changes
  So that I can directly know the latest updates without checking tickets manually

  Scenario: Citizen views notification list and marks message as read (Happy Path)
    Given the citizen has a new unread notification for report "LAP-2026-0001"
    When the citizen opens the "Notifikasi" menu and clicks the unread notification item
    Then the system updates the notification read status to read
    And the system redirects the citizen to the detail progress page of report "LAP-2026-0001"
