# Power switch per lamp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een lamp kan een schakelaar-entiteit krijgen die haar stroom geeft; de integratie reset een lamp die zwijgt, en kan de schakelaar als aan en uit gebruiken.

**Architecture:** Een klein onderdeel `PowerSwitch` (`power.py`) volgt en bedient de gekozen entiteit via de toestanden en diensten van Home Assistant. `FlosStringBLEManager` krijgt het mee en beslist wanneer een lamp zwijgt en wanneer een reset volgt. Zonder schakelaar loopt geen enkele nieuwe regel code.

**Tech Stack:** Python, asyncio, Home Assistant (config entry options, `EntitySelector`, `async_track_state_change_event`), de bestaande Bluetooth-laag.

**Spec:** `docs/superpowers/specs/2026-11-22-power-switch-design.md`

## Global Constraints

- Alleen voor *Connect only when needed*: bij *Stay connected* krijgt de manager geen schakelaar.
- Geen schakelaar gekozen, of het veld leeggemaakt: gedrag identiek aan 2026.47.10. De Shelly is nooit verplicht.
- Domein, unique_id's en entiteits-ID's blijven ongewijzigd.
- De schakelaar wordt alleen bediend met `homeassistant.turn_on` / `homeassistant.turn_off` en gevolgd via zijn toestand.
- Waarden uit het ontwerp: 5 s zonder stroom (instelbaar 1–60), 30 s wachten op de eerste advertentie na het inschakelen, 10 s marge na een verbinding (`ADVERTISE_AGAIN`), *Reset after silence* 0–3600 s met 0 als standaard.
- Teksten in het Engels. Simulaties zijn werkscripts buiten de repo (scratchpad `hacheck/`), uitgevoerd als `venv/Scripts/python <sim> <pad naar de repo>`; de acht bestaande moeten "ALL OK" blijven geven.
- Per stap: eerst de falende simulatie, dan de code, dan de diff aan Peter; commit na zijn akkoord, push en release apart.

## Review Focus

1. De gekozen entiteit bestaat niet meer of is "unavailable": de lamp gedraagt zich als zonder schakelaar, zonder fout.
2. Home Assistant meldt een advertentie met ongewijzigde inhoud niet aan callbacks: het wachten na het inschakelen moet het tijdstip van de laatste advertentie opvragen, niet op de callback rekenen.
3. Een lamp die na een reset wel adverteert maar geen verbinding aanneemt: met *Reset after silence* groter dan 0 mag er geen lus van resets ontstaan.
4. De schakelaar gaat van buitenaf uit terwijl een verbinding openstaat of een wijziging wacht.
5. Home Assistant start terwijl de schakelaar uit staat: niet beschikbaar, geen reset, gelezen zodra de lamp na het inschakelen adverteert.

Elk punt heeft een controle in `sim_power.py` (taak 2).

---

## Stap 1 van het ontwerp: schakelaar, reset en knop

### Task 1: `PowerSwitch` en constanten

**Files:**
- Create: `custom_components/flos_string/power.py`
- Modify: `custom_components/flos_string/const.py`
- Test: scratchpad `hacheck/sim_power.py`

**Interfaces — Produces:**

```python
# const.py
CONF_POWER_SWITCH = "power_switch"   # entity ID; absent: no switch
CONF_OFF_TIME = "off_time";       DEFAULT_OFF_TIME = 5      # seconds without power
CONF_RESET_AFTER = "reset_after"; DEFAULT_RESET_AFTER = 0   # seconds of silence; 0: only for a change
POWER_ON_TIMEOUT = 30   # seconds a lamp gets to advertise after its power comes on
HEARD_POLL = 0.5        # seconds between two looks at the last advertisement

# power.py
class PowerSwitch:
    def __init__(self, hass: HomeAssistant, entity_id: str) -> None
    entity_id: str
    @property
    def is_on(self) -> bool | None      # None: missing, "unavailable" or "unknown"
    async def async_turn_on(self) -> None    # homeassistant.turn_on, blocking
    async def async_turn_off(self) -> None   # homeassistant.turn_off, blocking
    def async_listen(self, listener: Callable[[], None]) -> CALLBACK_TYPE   # on every change of is_on
```

- [ ] Simulatie: `is_on` voor de toestanden on / off / unavailable / unknown / ontbrekend; `async_turn_off` roept `homeassistant.turn_off` met de entiteit; de listener loopt bij on→off en niet bij een wijziging van alleen een attribuut. Draaien: faalt op `No module named flos_string.power`.
- [ ] `power.py` en de constanten schrijven; simulatie slaagt.

### Task 2: de manager reset een lamp die zwijgt

**Files:**
- Modify: `custom_components/flos_string/ble.py`
- Test: scratchpad `hacheck/sim_power.py`

**Interfaces:**
- Consumes: `PowerSwitch`, de constanten van taak 1.
- Produces:

```python
FlosStringBLEManager(..., power: PowerSwitch | None = None,
                     off_time: float = DEFAULT_OFF_TIME,
                     reset_after: float = DEFAULT_RESET_AFTER)
manager.has_power_switch -> bool
async def async_power_cycle(self) -> None   # the button; HomeAssistantError "power_off" / "not_back"
```

Beslissingen die de tests niet afdwingen:

- **Zwijgen** (`_silent(margin=ADVERTISE_AGAIN)`): schakelaar aan, minstens `POWER_ON_TIMEOUT` geleden aangegaan (bij de start: altijd al), geen verbinding open, de manager deed in deze run al een verbindingspoging, die eindigde meer dan `margin` geleden, en de laatste advertentie die Home Assistant kent is niet jonger dan dat einde.
- **Reset** (`_power_cycle() -> bool`): uit, `off_time` wachten, aan, en tot `POWER_ON_TIMEOUT` om de `HEARD_POLL` kijken of de laatste advertentie jonger is dan het inschakelen. Eigen schakelingen tellen niet als schakelen van buitenaf.
- **Eén reset tot de lamp weer antwoordt:** na een reset volgt geen automatische reset meer tot een verbinding slaagt. Dat is strenger dan "tot ze adverteert" in het ontwerp en sluit een lus uit (Review Focus 3).
- **Bij een wijziging:** alleen de helderheid (`_write_wanted`), niet de naam, de poll of *Refresh*. Voor het verbinden als de lamp zwijgt; en na een mislukte verbinding als ze zwijgt met marge 0, gevolgd door één nieuwe poging.
- **Uit zichzelf:** in `_run_on_demand`, zodra de lamp zwijgt en de laatste poging `reset_after` geleden eindigde; daarna één leesbeurt.
- **Beschikbaarheid:** een lamp die zwijgt en nog geen reset kreeg, wordt niet onbereikbaar gemeld (lus, `_on_unavailable`, mislukte leesbeurt). Schakelaar uit: meteen onbereikbaar. Mislukte reset: onbereikbaar.
- **Na het inschakelen** telt de lamp pas als adverterend zodra een advertentie jonger is dan het inschakelen; tot dan kijkt de lus om de `HEARD_POLL`.

- [ ] Simulatie `sim_power.py` met een nagebootste lamp (stroom, opstarttijd, vastlopen na een verbreking, adverteren zonder dat de callback loopt) en een nagebootste schakelaar. Controles: (a) zonder schakelaar blijft een stille lamp onbereikbaar zoals nu; (b) vastgelopen + wijziging → één reset, wijziging uitgevoerd; (c) vastgelopen binnen de marge → verbinding mislukt, reset, tweede poging slaagt; (d) leesbeurt en *Refresh* resetten niet en de lamp blijft beschikbaar; (e) lamp komt niet terug → fout, onbereikbaar, geen tweede reset bij de volgende wijziging; (f) `reset_after` → reset uit zichzelf en een leesbeurt; (g) lamp die na de reset adverteert maar niet verbindt → geen tweede automatische reset; (h) later stil geworden lamp (adverteerde nog na de laatste verbinding) → geen reset; (i) schakelaar van buitenaf uit met open verbinding → onbereikbaar, aan → gelezen; (j) start met schakelaar uit; (k) entiteit onbruikbaar → als zonder schakelaar; (l) `async_power_cycle` op een lamp die niet zwijgt, en met de schakelaar uit (fout). Draaien: faalt op het onbekende argument `power`.
- [ ] `ble.py` aanpassen; `sim_power.py` en de acht bestaande simulaties slagen; `python -m compileall -q custom_components`.

### Task 3: instellingen, knop en teksten

**Files:**
- Modify: `custom_components/flos_string/config_flow.py`, `__init__.py`, `button.py`, `strings.json`, `translations/en.json`
- Test: scratchpad `hacheck/check_options2.py` (uitbreiden)

- **Formulier:** `vol.Optional(CONF_POWER_SWITCH)` met `EntitySelector` voor de domeinen `switch` en `input_boolean`; `CONF_OFF_TIME` 1–60 s; `CONF_RESET_AFTER` 0–3600 s. Het veld leegmaken en opslaan haalt de sleutel uit de opties.
- **`__init__.py`:** alleen bij *Connect only when needed* en met een gekozen entiteit een `PowerSwitch` meegeven.
- **Knop:** `FlosStringPowerCycle`, `translation_key = "power_cycle"`, altijd beschikbaar, alleen aangemaakt met een schakelaar en anders uit het register gehaald, zoals bij *Reconnect* en *Refresh*.
- **Teksten:** labels *Power switch*, *Time without power*, *Reset after silence* met uitleg; knop *Power cycle*; fouten `power_off` en `not_back`.

- [ ] Controle uitbreiden: de drie velden staan in het formulier met hun standaard; opslaan zonder schakelaar geeft opties zonder `power_switch`; `strings.json` en `en.json` zijn gelijk en bevatten elke nieuwe sleutel. Draaien: faalt.
- [ ] Code en teksten schrijven; alle simulaties slagen.
- [ ] Diff aan Peter; commit "Add a power switch per lamp: reset a lamp that went silent" na akkoord.

### Task 4: README

- [ ] De nieuwe instellingen in de tabel, een alinea over de reset en de knop, en de beperking tot *Connect only when needed*. Aparte commit "README: the power switch".

## Stap 2 van het ontwerp: rol *On and off*

Pas na de validatie van stap 1 in de echte Home Assistant. Raakt `const.py` (`CONF_SWITCH_ROLE`, `ROLE_RESET`, `ROLE_ON_OFF`), `ble.py` (`async_turn_on()` / `async_turn_off()` van de schakelaar, een wijziging die wacht tot de lamp na het inschakelen adverteert, geen 0 % schrijven), `light.py` (toestand en commando's volgens de tabel in het ontwerp), `config_flow.py` en de teksten. De taken worden uitgeschreven wanneer stap 1 staat.
