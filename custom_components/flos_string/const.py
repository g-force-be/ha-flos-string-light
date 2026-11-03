"""Constants for the Flos String Light integration."""

DOMAIN = "flos_string"

# BLE UUIDs (lowercase for Bleak compatibility)
SERVICE_UUID = "0dcecf0c-ad06-11e3-81e4-425861b86ab6"
BRIGHTNESS_CHAR_UUID = "335c1504-ad06-11e3-81e4-425861b86ab6"
# Alternative characteristic - might be the actual control
ALT_CHAR_UUID = "1b74ea4e-b010-11e3-88fe-425861b86ab6"

# Brightness range on the Flos device
BRIGHTNESS_MIN = 0   # off
BRIGHTNESS_MAX = 100  # 0x64

# Default brightness when turning on without specifying (%)
DEFAULT_BRIGHTNESS_PCT = 100

# BLE connection parameters
DISCONNECT_DELAY = 5.0   # seconds before disconnecting after last command
WRITE_TIMEOUT = 10.0     # seconds for BLE write timeout
CONNECT_TIMEOUT = 15.0   # seconds for BLE connection timeout
MAX_RETRIES = 3          # max retry attempts per operation

# Polling interval for reading state (seconds)
SCAN_INTERVAL_SECONDS = 60

# Config entry data keys
CONF_ADDRESS = "address"
CONF_NAME = "name"
