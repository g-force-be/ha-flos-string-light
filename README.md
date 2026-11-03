<img src="https://raw.githubusercontent.com/g-force-be/ha-flos-string-light/main/custom_components/flos_string/brand/icon@2x.png" alt="Flos String Light for Home Assistant" width="128" height="128">

# Flos String Light for Home Assistant

A Home Assistant integration for the **Flos String Light**, over Bluetooth Low Energy. Each lamp shows up as a dimmable light (on, off, brightness) and talks to Home Assistant through Home Assistant's own Bluetooth: the adapter in the host or an ESPHome Bluetooth proxy.

> **Status: work in progress.** Home Assistant finds the lamps, connects and writes the brightness, but **the lamp doesn't act on it yet** (see [Known issues](#known-issues)). Reports from other owners are welcome in [Issues](https://github.com/g-force-be/ha-flos-string-light/issues).

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
- The integration connects for each command or poll and disconnects 5 seconds after the last one. Each operation gets up to three attempts.
- Every 60 seconds it reads the brightness, so changes made elsewhere show up within a minute. After a command the entity shows the new state straight away.

## Limitations

- Brightness only.
- Each poll opens a Bluetooth connection for a few seconds. On an ESPHome proxy that takes one of its connection slots (three by default) for that time, per lamp.
- When no adapter can see the lamp, the entity keeps its last state instead of turning *unavailable*.

## Known issues

1. **The lamp doesn't respond.** Writing the brightness succeeds at the Bluetooth level, but the lamp doesn't change. The cause is not known yet and is being investigated.
2. **Test service `flos_string.gatttool_write`.** Left over from debugging. It needs the `gatttool` program, which Home Assistant OS doesn't have. Don't use it; it will be removed.
3. **Invisible character in the name.** A lamp found automatically can get a name that ends in a NUL character from its Bluetooth name. Rename the entry if it bothers you; a later version strips it.
4. **Fixed: "Cannot write to CCCD (0x2902) directly".** The Bluetooth library in Home Assistant 2026.10 refuses that write, and updates failed with a traceback. The integration now subscribes to the characteristic with `start_notify()`.

## Debug logging

*Settings → Devices & services → Flos String Light → ⋮ → Enable debug logging*, or in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.flos_string: debug
```

The log then shows each connection, every brightness read and write, and `Subscribed to …` when the lamp offers notifications on the brightness characteristic.

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
