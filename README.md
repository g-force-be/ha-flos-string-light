<img src="https://raw.githubusercontent.com/g-force-be/ha-flos-string-light/main/custom_components/flos_string/brand/icon@2x.png" alt="Flos String Light for Home Assistant" width="128" height="128">

# Flos String Light for Home Assistant

A Home Assistant integration for the **Flos String Light**, over Bluetooth Low Energy. Each lamp shows up as a dimmable light (on, off, brightness) and talks to Home Assistant through Home Assistant's own Bluetooth: the adapter in the host or an ESPHome Bluetooth proxy.

> **Status: working, still young.** Home Assistant finds the lamps, keeps a connection to each one and switches and dims them. So far it runs on the author's lamps through an ESPHome Bluetooth proxy; the host's own adapter is untested. Reports from other owners are welcome in [Issues](https://github.com/g-force-be/ha-flos-string-light/issues).

## Installation

**HACS**

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/g-force-be/ha-flos-string-light`, type *Integration*.
2. Download **Flos String Light** and restart Home Assistant.

**By hand:** copy `custom_components/flos_string` to `config/custom_components/` and restart Home Assistant.

You need:

- Home Assistant 2026.3 or later (tested on 2026.10.4).
- The **Bluetooth** integration with an adapter that can connect: the host's own adapter or an ESPHome Bluetooth proxy. Shelly devices only pass on advertisements; they can't connect to the lamp.

## Configuration

**Automatically.** Home Assistant recognises a lamp by the Bluetooth service it advertises (`0dcecf0c-ad06-11e3-81e4-425861b86ab6`) and offers it under *Settings → Devices & services → Discovered*. Confirm it and give it a name if you like.

**By hand.** *Settings → Devices & services → Add integration → Flos String Light*, then enter the lamp's Bluetooth address (`XX:XX:XX:XX:XX:XX`) and a name.

## How it works

- One light entity per lamp. Home Assistant's brightness (0–255) maps to the lamp's 0–100; 0 is off. *Turn on* without a brightness brings back the last one (100 % the first time).
- The brightness is one byte on characteristic `335c1504-ad06-11e3-81e4-425861b86ab6` of service `0dcecf0c-ad06-11e3-81e4-425861b86ab6`.
- **One connection per lamp, kept open.** The integration connects when Home Assistant starts and stays connected. Starting never waits for a lamp: the connection is made in the background.
- **Every connection is made twice.** Home Assistant remembers the lamp's services, but forgets them when it restarts and when the Bluetooth proxy reconnects. On a connection that has to look them up again, the lamp accepts a brightness and reads it back but doesn't carry it out, or the connection stalls. The integration can't tell which kind of connection it got, so it closes every new connection straight away and opens a second, which uses the remembered services. Seen through an ESPHome Bluetooth proxy. It costs a second or two per connection.
- **The lamp reports its own level.** After every connection the integration subscribes to the lamp's indications on the brightness characteristic, and those are the state. Nothing is polled.
- **Safety net.** Every 5 minutes the brightness is read over the open connection, in case an indication never came. After a command the level is read back straight away, because the lamp sends no indication for a change it was told to make.
- **Available means connected.** When the connection drops, the entities turn *unavailable* at once. The integration reconnects after 5, 10 and 30 seconds and then every minute, and sooner when the lamp is seen advertising again.

What the open connection costs:

- **One connection slot per lamp, permanently.** An ESPHome Bluetooth proxy has three by default, so one proxy carries three lamps and nothing else that needs a connection.
- **The Flos app cannot connect while Home Assistant is connected.** The lamp accepts one connection at a time. Disable the lamp's entry in Home Assistant for as long as you want to use the app.
- **Two lamps on one Bluetooth proxy don't both work.** The lamp that connects while the proxy already holds another lamp accepts a brightness and reads it back, but doesn't carry it out. The lamp that was connected first keeps working. Seen with an ESPHome Bluetooth proxy. Use *Connect only when needed* (below) for the lamps on such a proxy.

## Connecting only when needed

Each lamp has two settings, under *Settings → Devices & services → Flos String Light → Configure* (the gear next to the lamp):

- **Connection:** *Stay connected* (the default, described above) or *Connect only when needed*.
- **Poll interval**, in minutes: how often the brightness is read, over a short connection. Only used with *Connect only when needed*.
- **Power check interval**, in seconds: how often Home Assistant checks that the lamp still advertises, without a connection. Only used with *Connect only when needed*.

With *Connect only when needed*:

- **A change connects, writes, reads the result back and disconnects.** That takes a few seconds.
- **Only the last change counts.** A brightness that still waits, for its turn or for the lamp to connect, is replaced by the next one. Dragging a slider gives one or two changes, not ten.
- **At most 3 visits per 30 seconds per lamp.** A lamp that is connected to too often in a short time stops advertising until its power is cut: seen after 6 changes in 20 seconds. So the integration visits a lamp at most 3 times per 30 seconds, counting changes, reads and the Refresh button. The next one waits, up to half a minute. Where the lamp's own limit lies isn't known yet.
- **Lamps take turns.** No two lamps are connected at the same moment, so the problem with two lamps on one proxy doesn't occur. Set all lamps on the same proxy to *Connect only when needed*: a lamp that stays connected spoils it for the others.
- **The state is read when Home Assistant starts, every poll interval and when the lamp advertises again.** With a poll interval of 0 it is never read in between; the state is then what Home Assistant last set. A change made with the Flos app or the dimmer on the cord shows up at the next read.
- **A lamp that stops advertising has no power.** A lamp that isn't connected advertises, and Home Assistant hears that without connecting. Every power check interval (60 seconds by default) the integration looks at when the lamp was last heard. A lamp that wasn't heard since the previous check turns *unavailable*, and nothing connects to it until it advertises again; then its state is read at once. With an interval of 0 the integration waits for Home Assistant itself to miss the lamp, which takes a few minutes.
- **Two diagnostic sensors** show which Bluetooth proxy hears the lamp best and how strong its signal is there, in dBm. They are refreshed at every power check, without a connection. Home Assistant picks the proxy for each connection itself: the one with the best signal that has a free slot. A lamp can't be tied to one proxy; to move a lamp to another proxy, put that proxy closer to it.
- **The Flos app can connect**, except during the seconds of a change or a read. While the app is connected the lamp doesn't advertise, so Home Assistant shows it as *unavailable*.

## The lamp's name

Each lamp also has a text entity **Name**, under *Configuration* on the device page. It shows the name stored in the lamp, the one it advertises over Bluetooth, and lets you change it.

- The lamp stores 18 bytes of UTF-8. Bytes are counted, not characters: an accented letter takes two or more. A name that doesn't fit is refused.
- Changing it renames the lamp itself. The device and entity names in Home Assistant stay as they are.
- A lamp with an empty name shows as *unknown*. Type a name to give it one.
- The name is written to the lamp's own name characteristic (`5be8ef0a-b3d3-11e3-8ed5-425861b86ab6`); the lamp copies it to the standard Bluetooth Device Name, which is where it is read. Windows and iOS keep that standard characteristic to themselves, so a generic Bluetooth tool there can't read or change the name. Linux does the same on the host's own adapter: there the entity can stay *unknown*, while writing still works.

## Reconnect and device information

- Each lamp has a button **Reconnect**, under *Configuration* on the device page. It closes the connection to the lamp and opens a new one straight away. Use it when a lamp is connected but doesn't do what it is told.
- A lamp set to *Connect only when needed* has a button **Refresh** instead. It connects, reads the lamp's state and disconnects.
- The device page shows the lamp's Bluetooth address. The lamp offers nothing else to show: no firmware version and no serial number.

## Limitations

- Brightness and the name only.
- While a lamp stays connected: one permanent connection slot per lamp, no Flos app, and only one lamp per Bluetooth proxy (see above).
- With *Connect only when needed*: a few seconds per change, a fourth change within 30 seconds that waits, and a state that can lag behind until the next read.

## Known issues

- **Invisible character in an old entry's title.** A lamp added with an earlier version can have a title that ends in a NUL character from its Bluetooth name. The device name is cleaned up; rename the entry if the title bothers you. New entries don't get it.

## Debug logging

*Settings → Devices & services → Flos String Light → ⋮ → Enable debug logging*, or in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.flos_string: debug
```

The log then shows each connection and disconnection, every indication, read and write, and once per start the lamp's full GATT table.

## Releases and versions

Versions follow the calendar: **year.week.number**, e.g. `2026.45.1` is the first release in ISO week 45 of 2026, and `2026.45.2` the second. A release is made from the Actions tab (*Release → Run workflow*). It writes the version into `manifest.json`, tags that commit and publishes a GitHub release, which HACS then offers as an update.

## Development

```sh
python -m compileall -q custom_components   # does the Python compile
python tools/brand.py                       # brand icons from docs/images/icon.svg (needs Pillow and Chrome)
```

The *Validate* workflow runs HACS's check and Home Assistant's `hassfest` on every push to `main`.

## Disclaimer

Not affiliated with or endorsed by Flos. Flos is a trademark of Flos S.p.A. This project contains no Flos logo, wordmark or product photography; the icon is original artwork.

## Licence

MIT, see [`LICENSE`](LICENSE).
