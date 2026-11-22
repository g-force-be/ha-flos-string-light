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
STABLE_CONNECTION = 60  # a connection that lasted this long resets the backoff
REFRESH_INTERVAL = 300  # safety-net read of the brightness over the open connection

# Options of a lamp: how Home Assistant connects to it.
CONF_CONNECTION = "connection"
CONNECTION_ALWAYS = "always"  # one connection, kept open
CONNECTION_ON_DEMAND = "on_demand"  # connect for a change or a read, then disconnect
CONF_POLL_INTERVAL = "poll_interval"  # minutes between reads on demand; 0 is never
DEFAULT_POLL_INTERVAL = 5
# On demand: seconds the connection stays open after a change. The next change
# within that time is written at once, over that connection. 0 closes it at
# once.
CONF_HOLD_TIME = "hold_time"
DEFAULT_HOLD_TIME = 0
# Home Assistant forgets a lamp that is silent for minutes, as one is whose
# connection is kept open. After a connection the lamp advertises again: it
# gets this many seconds before it is taken for a lamp without power.
ADVERTISE_AGAIN = 10
# On demand: at most so many visits (connect, read or change, disconnect) to one
# lamp per window of so many seconds; the next one waits. 0 visits is no limit.
# A lamp that is visited too often in a short time stops advertising until its
# power is cut: seen on 21/11/2026 after 6 changes in 20 seconds. Where the
# limit lies is not known.
CONF_VISIT_LIMIT = "visit_limit"
DEFAULT_VISIT_LIMIT = 3
CONF_VISIT_WINDOW = "visit_window"
DEFAULT_VISIT_WINDOW = 30

# On demand: wait until no other lamp is connected. Needed for lamps on the same
# Bluetooth proxy; a lamp with a proxy of its own need not wait.
CONF_TAKE_TURNS = "take_turns"
DEFAULT_TAKE_TURNS = True

# Seconds between checks, on demand, that the lamp still advertises: no connection.
# 0 leaves it to Home Assistant, which takes some minutes to miss a lamp.
CONF_POWER_CHECK_INTERVAL = "power_check_interval"
DEFAULT_POWER_CHECK_INTERVAL = 60

# Whether a connection is closed and opened again before use (see _connect() in
# ble.py): always, only when it had to look up the lamp's services, or never.
CONF_SECOND_CONNECTION = "second_connection"
SECOND_ALWAYS = "always"
SECOND_WHEN_NEEDED = "when_needed"
SECOND_NEVER = "never"
DEFAULT_SECOND_CONNECTION = SECOND_ALWAYS
# The on/off setting that 2026.47.9 stored instead: on is always, off is never.
CONF_CONNECT_TWICE = "connect_twice"
# So many services, as Home Assistant handed them out, are remembered per lamp:
# one for every adapter or proxy the lamp connected through.
KNOWN_SERVICES = 4

# Tries within one connection attempt, before the wait for the next attempt.
CONF_CONNECT_ATTEMPTS = "connect_attempts"
DEFAULT_CONNECT_ATTEMPTS = 2

# Seconds until the next attempt after a connection that failed. The attempts
# after that follow after RETRY_STEPS times as long; the last step repeats.
# With 5 seconds: 5, 10 and 30 seconds, then every minute.
CONF_RETRY_INTERVAL = "retry_interval"
DEFAULT_RETRY_INTERVAL = 5
RETRY_STEPS = (1, 2, 6, 12)
