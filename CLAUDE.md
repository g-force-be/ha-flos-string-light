# ha-flos-string-light

Peters eigen Home Assistant-integratie `flos_string` voor de Flos String Light via Bluetooth LE. De code komt uit zijn HA (`/config/custom_components/flos_string`, 3/11/2026). Vanaf nu is deze repo de bron.

## Lees eerst
- `docs/CLAUDE_CODE_PROMPT.md` is de startopdracht: omgeving (HAOS, lampen, Bluetooth-paden), bekende problemen en de stappen.
- `README.md` beschrijft wat de integratie doet, de installatie, de beperkingen en de bekende problemen.
- `custom_components/flos_string/const.py` bevat de service- en kenmerk-UUID's en de timing.
- `custom_components/flos_string/light.py` bevat de BLE-manager (verbinden, lezen, schrijven) en de light-entiteit.

## Vaste regels
- **Peters HA:**
  - Wijzig niets (bestanden, integraties, herstart) zonder zijn akkoord.
  - Verwijder de bestaande integratie en config entries niet. Houd het domein `flos_string` en de unique_id (MAC-adres zonder dubbele punten) ongewijzigd. Anders krijgen `light.flos_string_light_slaapkamer` en `light.badkamer` nieuwe entiteiten, en die gebruikt het dashboard `google-home-hub-keuken` (view Lights) en de helper "Lampen aan".
  - HACS overschrijft de map gewoon.
  - Een reload van de config entry laadt geen nieuwe Python-code; daarvoor is een herstart nodig.
- **Lokale gegevens:** IP-adressen, MAC-adressen en config-entry-ID's staan alleen in `docs/LOCAL.md` (in `.gitignore`). In de repo gebruik je placeholders.
- **Geheimen:** geen tokens, wachtwoorden of encryptiesleutels in de repo.
- **BLE:** gebruik de HA-bluetooth-API (`bluetooth.async_ble_device_from_address`, `bleak_retry_connector.establish_connection`). Geen eigen adapters, geen subprocess.
- **CCCD:** gebruik `start_notify()`/`stop_notify()`, nooit een directe write op de CCCD (0x2902).
- **Merk en beeld:**
  - Geen Flos-logo en geen Flos-productfoto's in de repo.
  - Het icoon is eigen tekenwerk: bron `docs/images/icon.svg`, PNG's in `brand/` via `python tools/brand.py`.
- **[verifiëren]-punten** controleer je eerst in de echte HA en rapporteer je voor je erop bouwt.
- **Samenwerking:**
  - Beperk je in elke stap tot wat gevraagd is.
  - Toon de diff voor je commit als de wijziging niet triviaal is.
  - Eén wijziging tegelijk; valideer voor je aan de volgende begint. Peter debugt via de HA-UI en de logs.
  - Commitboodschappen in het Engels, communicatie in het Nederlands.
