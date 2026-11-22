# Ontwerp: stroomschakelaar per lamp

22/11/2026. Door Peter goedgekeurd op 22/11/2026. Stap 1 is gebouwd, stap 2 nog niet. Waar de bouw van het goedgekeurde ontwerp afwijkt, is de tekst aangepast; de lijst staat onderaan.

## Waarom

- **Vastlopen.** Een Flos String Light kan vastlopen: ze brandt, maar adverteert niet meer en niemand kan nog verbinden, ook de Flos-app niet. Alleen een stroomonderbreking helpt. Dat is drie keer gezien, het laatst op 22/11/2026 om 17:05. Nu moet Peter daarvoor naar de wandschakelaar.
- **Aan en uit.** Via Bluetooth duurt aan of uit 2 s of meer, en een lamp kan "doof" zijn: ze neemt de stand aan en leest hem terug, maar voert hem niet uit. Een relais schakelt meteen en altijd.
- **Shelly.** Peter hangt elke lamp achter een Shelly-relais. De integratie moet die schakelaar kunnen gebruiken.

## Doel

1. Per lamp een schakelaar-entiteit kunnen kiezen die haar stroom geeft.
2. Een lamp die zwijgt terwijl ze stroom heeft, zelf resetten: stroom uit, wachten, stroom aan.
3. Naar keuze die schakelaar ook gebruiken als aan en uit van de lamp. Bluetooth dient dan alleen nog om te dimmen en te lezen.
4. Voor een lamp zonder gekozen schakelaar verandert er niets.

## Niet in deze versie

- **"Stay connected".** De nieuwe instellingen gelden alleen voor *Connect only when needed*, zoals de poll, de limiet en het openhouden. Beide lampen van Peter draaien zo.
- **Een dove lamp herkennen.** De integratie ziet doofheid niet op het moment van de write. Of een stroomonderbreking doofheid geneest, is ook niet bewezen. De knop *Power cycle* laat Peter het zelf proberen.
- **Een Nederlandse vertaling** van het formulier.

## Wat het niet mag doen

- De stroom onderbreken zonder dat iemand iets vroeg, tenzij dat zo is ingesteld. Een reset is een zichtbare knipper, ook 's nachts in de slaapkamer. Een lamp die met de Flos-app verbonden is, zwijgt bovendien ook.
- In een lus resetten.
- Entiteits-ID's, unique_id's of het domein wijzigen: dashboard, HomeKit en de helper "Lampen aan" blijven werken zonder aanpassing.

## Randvoorwaarden

- Bluetooth blijft via de Bluetooth-API van Home Assistant lopen, zoals nu.
- De schakelaar wordt bediend via de gewone diensten van Home Assistant (`homeassistant.turn_on` en `homeassistant.turn_off`) en gevolgd via zijn toestand. De integratie praat niet rechtstreeks met de Shelly.
- De instellingen staan per lamp in de opties van haar config entry. Opslaan herlaadt de lamp.

## Aanpakken

1. **In de integratie, en het deel dat de verbinding beheert kent de stroom.** Gekozen. Eén entiteit per lamp; beschikbaarheid, reset en uitlezen kloppen met elkaar.
2. **Buiten de integratie: een sjabloonlamp met een automatisering.** Afgevallen. Dat geeft een tweede entiteit per lamp, zodat dashboard, HomeKit en "Lampen aan" om moeten, en de Flos-entiteit wordt nog altijd "niet beschikbaar" als de lamp uit is.
3. **Alleen de light-entiteit aanpassen.** Afgevallen. De verbindingsbeheerder blijft dan een lamp zonder stroom uitlezen en als onbereikbaar melden.

Peter koos op 22/11/2026 voor een instelling in de configuratie van de lamp, dus voor aanpak 1.

## Instellingen

Vier nieuwe instellingen per lamp, onder *Configure*:

| Instelling | Standaard | Wat ze doet |
| --- | --- | --- |
| **Power switch** | leeg | De entiteit die de lamp stroom geeft. Leeg: alles zoals nu, en de drie instellingen hieronder doen niets. |
| **What the switch does** | *Reset only* | *Reset only*: de schakelaar blijft aan en dient alleen voor een reset. *On and off*: de schakelaar is ook aan en uit van de lamp. |
| **Time without power** | 5 s | Hoe lang de stroom weg is bij een reset. |
| **Reset after silence** | 0 s | 0: alleen resetten wanneer een wijziging de lamp nodig heeft. Meer dan 0: ook uit zichzelf, zodra de lamp zo lang zwijgt. |

## Wanneer een lamp "zwijgt"

Een lamp zwijgt als aan alle drie de voorwaarden voldaan is:

- De schakelaar staat aan, en al minstens 30 s. Na het inschakelen krijgt de lamp die tijd om op te starten.
- Er is geen verbinding met de lamp open en er wordt er geen opgezet.
- Sinds een verbinding van de integratie zelf sloot, hoorde Home Assistant de lamp niet meer adverteren, en dat sluiten is meer dan 10 s geleden. Een poging die mislukt, telt niet: de lamp kan dan ook met de Flos-app verbonden zijn.

Wat daaruit volgt:

- **Dit vangt wat tot nu toe gezien is.** Alle drie de keren liep een lamp vast meteen na een verbreking door Home Assistant.
- **Een lamp die later stil wordt, zwijgt in deze zin niet.** Adverteerde ze nog na haar laatste verbinding en wordt ze pas daarna stil (verbonden met de Flos-app, buiten bereik van elke proxy), dan blijft alles zoals nu: in de rol *Reset only* wordt ze "niet beschikbaar" na de stroomcontrole, en er volgt geen reset. Zo onderbreekt de integratie de stroom niet van een lamp die iemand met de Flos-app bedient.
- **Na een herstart** van Home Assistant, of na het herladen van de lamp, kan een lamp pas zwijgen nadat een verbinding van de integratie zelf sloot. Een lamp die over een herstart heen vastzit, wordt alleen met de knop gereset.
- **De 10 s** komen uit de huidige code: de tijd die een lamp krijgt om na een verbinding weer te adverteren. Een gezonde lamp doet dat meestal binnen een seconde. Is de marge te krap, dan volgt een overbodige reset op een moment dat iemand een wijziging vroeg.

Zonder schakelaar betekent niet adverteren "geen stroom", zoals nu.

## Reset

Een reset is: schakelaar uit, *Time without power* wachten, schakelaar aan, wachten tot de lamp adverteert (hoogstens 30 s), en dan haar stand lezen.

- **Bij een wijziging.** Vraagt iemand een helderheid voor een lamp die zwijgt, dan volgt eerst een reset en daarna de wijziging. Mislukt de verbinding voor een wijziging terwijl de lamp sinds haar laatste verbinding niet meer adverteerde, dan krijgt ze eerst 10 s om gehoord te worden. Blijft ze stil, dan volgt ook een reset en één nieuwe poging. Eén mislukte verbinding mag de stroom van een gezonde lamp niet onderbreken.
- **Uit zichzelf.** Alleen met *Reset after silence* groter dan 0: zodra de lamp zo lang zwijgt.
- **Nooit bij een leesbeurt.** De poll en de knop *Refresh* resetten niet.
- **Eén reset per stilte.** Na een reset volgt geen nieuwe reset, uit zichzelf of bij een wijziging, tot de lamp gehoord is na een verbinding die sloot. Dan staat vast dat ze weer een verbinding verdraagt. Een lamp die na elke verbinding opnieuw vastloopt, wordt zo niet eindeloos gereset; ze wordt "niet beschikbaar". Gewoon inschakelen telt ook als een reset: adverteert de lamp daarna niet binnen 30 s, dan volgt geen nieuwe onderbreking. De knop kan altijd.
- **Als de lamp niet terugkomt** binnen 30 s, mislukt de wijziging met een foutmelding.
- **De stroom komt terug.** De integratie vraagt de schakelaar aan tot hij zelf "aan" meldt, ook als hij een fout geeft of in die seconden van het netwerk valt. Na 20 s mislukt de wijziging met een foutmelding; het vragen gaat door. Alleen als Home Assistant zelf stopt terwijl de stroom uit is, blijft de lamp uit.

Zolang een lamp zwijgt en nog geen reset mislukte, blijft ze "beschikbaar" met haar laatst gekende stand. Anders kan niemand de wijziging vragen die de reset uitlokt. Na een mislukte reset wordt ze in de rol *Reset only* "niet beschikbaar" tot ze weer adverteert.

## Knop *Power cycle*

Een knop per lamp, onder *Configuration* op de apparaatpagina, alleen als er een schakelaar gekozen is. Hij doet een reset, ook als de lamp niet zwijgt: bedoeld voor een lamp die doof lijkt. Hij werkt alleen als de schakelaar aan staat. Een verbinding die nog openstaat, wordt eerst gesloten.

## Rol *On and off*

De toestand van de lamp volgt de schakelaar:

- **Schakelaar uit:** de lamp toont "uit" en is beschikbaar. Er wordt niet gelezen en niet gecontroleerd of ze adverteert.
- **Schakelaar aan:** de lamp toont "aan" met haar laatst gelezen helderheid. Leest de integratie 0 %, dan toont de lamp "uit": ze heeft stroom maar brandt niet.
- **Altijd beschikbaar** zolang de schakelaar bruikbaar is, ook als Bluetooth de lamp niet bereikt. Aan en uit hebben Bluetooth niet nodig; alleen dimmen kan dan mislukken, met een foutmelding.

Wat een commando doet:

| Commando | Schakelaar staat uit | Schakelaar staat aan |
| --- | --- | --- |
| Uit | niets | Schakelaar uit. Een wijziging die nog wacht, vervalt. Een open verbinding wordt losgelaten. |
| Aan, zonder helderheid | Schakelaar aan. Zodra de lamp adverteert: haar stand lezen, niets schrijven. | Brandt de lamp: niets. Staat ze op 0 %: de vorige stand schrijven via Bluetooth, zoals nu. |
| Aan, met helderheid | Schakelaar aan. Zodra de lamp adverteert: die helderheid schrijven. | Die helderheid schrijven via Bluetooth, zoals nu. |

- **Na "aan" wordt niets teruggeschreven** (Peter, 22/11/2026). De lamp komt terug op de stand die ze zelf onthield; de integratie leest die alleen.
- **De integratie schrijft nooit 0 %** in deze rol. Uit is de schakelaar.
- **Schakelen van buitenaf** (wandschakelaar op de ingang van de Shelly, de Shelly-app, de schakelaar-entiteit zelf) volgt de integratie op dezelfde manier als haar eigen commando's.
- **De naam, de twee sensoren en de knop *Refresh*** hebben Bluetooth nodig. Ze zijn niet beschikbaar zolang de schakelaar uit staat.

In de rol *Reset only* blijven aan, uit en dimmen via Bluetooth lopen, zoals nu. Zet iemand de schakelaar toch uit, dan is de lamp meteen "niet beschikbaar" (geen stroom), en wordt ze gelezen zodra ze na het inschakelen adverteert.

## Schakelaar niet bruikbaar

Bestaat de gekozen entiteit niet, of is ze "niet beschikbaar" of "onbekend" (Shelly offline), dan gedraagt de lamp zich alsof er geen schakelaar gekozen is: aan, uit en dimmen via Bluetooth, zwijgen betekent geen stroom, en er wordt niet gereset. Zodra de schakelaar terug is, geldt zijn rol weer.

## Te meten zodra de Shelly's hangen

Deze punten zijn niet bekend en bepalen de standaardwaarden. Ze worden gemeten in de echte Home Assistant voor erop gerekend wordt:

- Hoe lang na het inschakelen de lamp begint te adverteren. Daarvan hangt af of 30 s wachten klopt.
- Hoe kort de stroomonderbreking mag zijn. Daarvan hangt de standaard van 5 s af.
- Hoe snel een gezonde lamp na een verbreking weer adverteert. Daarvan hangt af of de marge van 10 s klopt.
- Of de lamp altijd terugkomt op haar laatste stand. Op 22/11/2026 kwamen beide terug op hun stand van voor de onderbreking (39 % en 17 %); voor 0 % is het niet gezien.
- Of een reset een dove lamp weer doet luisteren.

Tot de Shelly's hangen, kan de logica in de echte Home Assistant alleen getest worden met een hulpschakelaar (`input_boolean`) in de plaats van het relais. De lamp verliest dan geen stroom.

## Aan de bouwer overgelaten

- Welke domeinen de keuzelijst toelaat (minstens `switch` en `input_boolean`; `light` alleen als de eigen entiteit van de lamp uitgesloten is).
- Hoe de schakelaar in de code zit (een klein eigen onderdeel naast de verbindingsbeheerder) en hoe de light-entiteit haar toestand samenstelt.
- De precieze teksten van de instellingen, de knop en de foutmeldingen, in het Engels zoals de rest.
- Of de teller van de limiet (3 bezoeken per 30 s) na een reset op nul gaat.
- De logregels: op debugniveau elke stap van een reset met zijn duur, zodat de metingen hierboven uit het log te halen zijn.
- De simulaties blijven werkscripts buiten de repo, zoals tot nu. Ze krijgen een nagebootste schakelaar erbij: zijn toestand en de diensten om hem te bedienen.

## Stappen

Elke stap krijgt een eigen diff, een eigen commit en een simulatie die eerst faalt. De README volgt per stap in een aparte commit.

1. **Schakelaar, reset en knop.** De instellingen *Power switch*, *Time without power* en *Reset after silence*, de reset en de knop *Power cycle*. De rol is nog niet kiesbaar en is *Reset only*.
2. **Rol *On and off*.** De instelling *What the switch does* en het gedrag uit de tabel.

## Afwijkingen van het goedgekeurde ontwerp (stap 1)

Gevonden bij de bouw en bij de review van de diff. De tekst hierboven is aangepast.

- **Zwijgen telt vanaf een verbinding die sloot,** niet vanaf een poging. Het ontwerp sprak zichzelf tegen: een mislukte poging op een lamp die de Flos-app vasthoudt, maakte van die lamp een lamp om te resetten.
- **Ook de eerste van twee verbindingen telt.** Met *Second connection* op *Always* sluit elk bezoek eerst een verbinding. Loopt de lamp daar vast, dan wordt dat nu herkend.
- **Eerst luisteren, dan onderbreken.** Na een mislukte verbinding krijgt de lamp 10 s om gehoord te worden voor de stroom eraf gaat.
- **Eén reset tot de lamp gehoord is na een verbinding die sloot.** Strenger dan "tot ze adverteert": anders reset een lamp die telkens opnieuw vastloopt zichzelf zonder einde.
- **De schakelaar wordt aan gevraagd tot hij "aan" meldt.** Home Assistant geeft geen fout voor een entiteit die net niet beschikbaar is; alleen de toestand van de schakelaar telt.
- **Een lamp die zwijgt, wordt weer beschikbaar** zodra haar schakelaar terug bruikbaar is. Anders kan niemand de wijziging vragen.
- **Zonder schakelaar doet *Reset after silence* niets,** ook als er nog een waarde voor bewaard is.

Open: stopt Home Assistant in de seconden zonder stroom, dan blijft de lamp uit tot iemand haar inschakelt. Dat dichten vraagt een bestandje dat de openstaande reset over een herstart heen onthoudt.
