"""Constants for the Flos String Light integration."""

DOMAIN = "flos_string"

# BLE UUIDs (lowercase for Bleak compatibility)
SERVICE_UUID = "0dcecf0c-ad06-11e3-81e4-425861b86ab6"
BRIGHTNESS_CHAR_UUID = "335c1504-ad06-11e3-81e4-425861b86ab6"
# The name is written to the lamp's own characteristic; the lamp copies it to the
# standard Device Name (Generic Access), which is where it is read.
NAME_CHAR_UUID = "5be8ef0a-b3d3-11e3-8ed5-425861b86ab6"
DEVICE_NAME_CHAR_UUID = "00002a00-0000-1000-8000-00805f9b34fb"
NAME_LENGTH = 18  # bytes of UTF-8; shorter names are padded with NULs
# The copy to the Device Name takes a moment: 0.3 s after the write the old name
# was still there. Read it back this often, this many seconds apart.
NAME_READBACK_ATTEMPTS = 4
NAME_READBACK_INTERVAL = 0.5

# Default brightness when turning on without specifying (%)
DEFAULT_BRIGHTNESS_PCT = 100

# The connection stays open. All times in seconds.
CONNECT_ATTEMPTS = 2  # tries within one connection attempt, before the backoff
RECONNECT_BACKOFF = (5, 10, 30, 60)  # waits between attempts; the last one repeats
STABLE_CONNECTION = 60  # a connection that lasted this long resets the backoff
REFRESH_INTERVAL = 300  # safety-net read of the brightness over the open connection

# Options of a lamp: how Home Assistant connects to it.
CONF_CONNECTION = "connection"
CONNECTION_ALWAYS = "always"  # one connection, kept open
CONNECTION_ON_DEMAND = "on_demand"  # connect for a change or a read, then disconnect
CONF_POLL_INTERVAL = "poll_interval"  # minutes between reads on demand; 0 is never
DEFAULT_POLL_INTERVAL = 5
# On demand: at most VISIT_LIMIT visits (connect, read or change, disconnect) to
# one lamp per VISIT_WINDOW seconds; the next one waits. A lamp that is visited
# too often in a short time stops advertising until its power is cut: seen on
# 21/11/2026 after 6 changes in 20 seconds. Where the limit lies is not known.
VISIT_LIMIT = 3
VISIT_WINDOW = 30

# Seconds between checks, on demand, that the lamp still advertises: no connection.
# 0 leaves it to Home Assistant, which takes some minutes to miss a lamp.
CONF_POWER_CHECK_INTERVAL = "power_check_interval"
DEFAULT_POWER_CHECK_INTERVAL = 60

# Open every connection, close it and open it again before use (see _connect()
# in ble.py). Off saves the time of one connection.
CONF_CONNECT_TWICE = "connect_twice"
DEFAULT_CONNECT_TWICE = True
