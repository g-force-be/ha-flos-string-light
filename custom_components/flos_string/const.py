"""Constants for the Flos String Light integration."""

DOMAIN = "flos_string"

# BLE UUIDs (lowercase for Bleak compatibility)
SERVICE_UUID = "0dcecf0c-ad06-11e3-81e4-425861b86ab6"
BRIGHTNESS_CHAR_UUID = "335c1504-ad06-11e3-81e4-425861b86ab6"

# Default brightness when turning on without specifying (%)
DEFAULT_BRIGHTNESS_PCT = 100

# BLE connection parameters
DISCONNECT_DELAY = 30.0  # seconds before disconnecting after last command
MAX_RETRIES = 3          # max retry attempts per operation

# Polling interval for reading state (seconds)
SCAN_INTERVAL_SECONDS = 60
