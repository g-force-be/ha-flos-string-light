"""Constants for the Flos String Light integration."""

DOMAIN = "flos_string"

# BLE UUIDs (lowercase for Bleak compatibility)
SERVICE_UUID = "0dcecf0c-ad06-11e3-81e4-425861b86ab6"
BRIGHTNESS_CHAR_UUID = "335c1504-ad06-11e3-81e4-425861b86ab6"

# Default brightness when turning on without specifying (%)
DEFAULT_BRIGHTNESS_PCT = 100

# The connection stays open. All times in seconds.
CONNECT_ATTEMPTS = 2  # tries within one connection attempt, before the backoff
RECONNECT_BACKOFF = (5, 10, 30, 60)  # waits between attempts; the last one repeats
STABLE_CONNECTION = 60  # a connection that lasted this long resets the backoff
REFRESH_INTERVAL = 300  # safety-net read of the brightness over the open connection
