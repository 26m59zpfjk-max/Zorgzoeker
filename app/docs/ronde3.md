# Overdracht ronde 3

Basis: GitHub-main `a460b53934595bd9b225e70471b1dd696d7c9457`.
Pas alleen `zorgzoeker-ronde3.patch` toe, zonder eerdere patches opnieuw toe te passen.
Controle: `git apply --check zorgzoeker-ronde3.patch`; toepassen op een eigen
werkbranch: `git apply zorgzoeker-ronde3.patch`. Er zijn geen commits gemaakt.
Geen nieuwe runtime-afhankelijkheden, externe diensten of verzendfuncties.

## Gedrag

- Kaarten tonen zorginhoud, contractstatus, route, bevestigde producten,
  leeftijd/toelating, wachttijd en instroom. De vier contractstatussen zijn
  gescheiden. Onderaannemerschap is geen rechtstreeks contract.
- Details zijn op ieder scherm standaard gesloten. Naamlinks en vergelijken
  blijven werken; bronnen, voorwaarden, hoofdaannemers, volledige codes en
  overige bronvelden blijven beschikbaar. Stops en ontbrekende expertise
  blijven buiten het uitklapblok zichtbaar.
- Naamzoeken (exacte naam of aanbieder-id) en bladeren tonen gestopte
  aanbieders met waarschuwing. Zorgvragen verbergen relevante gestopte routes;
  vrije tekst krijgt geen uitzondering. Contract en instroom blijven aparte feiten.
- Puberleeftijden, meerdere kinderen, decimalen, jr, medicatienegaties en
  AD(H)D zijn ondersteund. Bij meerdere expliciete leeftijden moet iedere
  leeftijd passen; een oncontroleerbare leeftijd blijft gemarkeerd.
- Gemeentefilters gebruiken canonieke gemeenten: Groesbeek valt onder Berg en
  Dal. Vestigingsplaatsen blijven afzonderlijke plaatsen.
- Stops worden per gemeente, product en expliciete periode getoetst. Zonder
  datumfilter wordt vandaag gebruikt voor de stop, niet de oude contractsnapshot.
  Een onbekende einddatum wordt niet zelf ingevuld.
- Letterlijk gepubliceerde `gemiddeld 13 weken` / `indicatie 6–8 weken` blijven
  bewaard als indicatieve publicatie, met bron en datum. Ze gelden nooit als
  actuele wachttijd, actuele instroom of bewijs voor een maximumwachttijd.
  Andere schattingen blijven geweigerd tenzij expliciet als
  `publicatie_type: indicatief` opgeslagen met geldige bron en peildatum.
  De 30-dagenregel voor andere publicaties blijft gelden.

## Optioneel beschikbaarheidsregister

Bestaande JSON-bestanden hoeven niet te migreren en zijn niet aangepast.
Voeg later bovenin het document een lijst `beschikbaarheidsregister` toe.
Elke regel heeft precies de volgende velden (uitsluitend fictief voorbeeld):

```json
{
  "id": "fictief-dienst-locatie",
  "aanbieder_id": "bestaande-aanbieder-id",
  "dienst": "FICTIEF jeugdbehandeling",
  "locatie": null,
  "productcode": null,
  "intake_weken": null,
  "start_behandeling_weken": null,
  "nieuwe_clienten": "onbekend",
  "capaciteit": null,
  "leeftijd_van": null,
  "leeftijd_tot": null,
  "regios": [],
  "stop": null,
  "bevestigd_op": null,
  "herbevestigen_op": null,
  "bron_url": "https://example.org/fictieve-publicatie",
  "verificatie": "gepubliceerd",
  "gepubliceerd_op": "2026-10-25"
}
```

- Ontbrekende getallen zijn `null`, nooit 0. Capaciteit is een geheel aantal
  beschikbare plaatsen, geen afgeleide uit een wachttijd.
- `nieuwe_clienten`: `ja`, `nee`, `onbekend`. `verificatie`:
  `aanbieder_bevestigd`, `gepubliceerd` of `historisch`.
- Alleen `aanbieder_bevestigd` met een bevestigingsdatum én latere
  herbevestigingsdatum kan actueel zijn. Op de herbevestigingsdatum vervalt de
  actualiteit. Een publicatie/ophaaldatum is geen aanbiederbevestiging.
- `stop` is null of bijvoorbeeld
  `{"soort":"aanmeldstop","vanaf":"2026-10-25","tot":null,"toelichting":"FICTIEF expliciete melding"}`.
  Soort kan ook `toeleidingsstop` zijn; `tot` is een inclusieve ISO-einddatum.
  Een brongebonden stop vervalt niet door een herbevestigingsdeadline.
- Een ingevulde productcode, locatie, regio of leeftijd beperkt de scope.
  Alleen overeenkomende, ingevulde zoekcontext maakt zo'n regel toepasbaar.
  Alle regels blijven in de kaartdetails beschikbaar als de zoekcontext ontbreekt.
  Meerdere/tegenstrijdige toepasselijke regels worden niet samengevoegd tot
  één gunstig getal of 'ja'. Een intakewachttijd wordt geen behandelwachttijd.
- De maximale-wachttijdfilter gebruikt bij toepasselijke registerregels alleen
  één actuele, bevestigde wachttijd tot **start behandeling**. Anders is de
  maximumduur onbevestigd, ook als een oudere publicatie gunstiger was.

## Offline workflow voor toekomstige agenten

Start vanuit `app/`. Alle acties schrijven een **nieuw** uitvoerbestand;
brondata worden nooit automatisch overschreven. Bestaande uitvoerbestanden
worden geweigerd. `--help` beschrijft de parameters.

```sh
python scripts/beschikbaarheidsworkflow.py signaleer data/aanbieders.json --uitvoer verouderd.json
python scripts/beschikbaarheidsworkflow.py concept data/aanbieders.json --regel-id REGEL --uitvoer verzoek.json
python scripts/beschikbaarheidsworkflow.py keur-verzoek data/aanbieders.json --invoer verzoek.json --beoordelaar CONTROLEUR --expliciet-goedgekeurd --uitvoer goedgekeurd-verzoek.json
python scripts/beschikbaarheidsworkflow.py voorstel data/aanbieders.json --invoer voorgestelde-regel.json --uitvoer wijziging.json
python scripts/beschikbaarheidsworkflow.py neem-op data/aanbieders.json --invoer wijziging.json --beoordelaar CONTROLEUR --expliciet-goedgekeurd --uitvoer aanbieders-ter-review.json
```

Ook een goedgekeurd verzoek wordt **niet verstuurd**. Een toekomstige externe
verzendintegratie moet die expliciete toestemming zelfstandig controleren.
Een ontvangen antwoord wordt door een agent/beheerder vertaald naar een
voorgestelde gestructureerde regel, met bewijsverwijzing. Geen cliëntgegevens
of ongestructureerde correspondentie opslaan. Geen ontbrekende antwoorden invullen.
De beoordelaar controleert identiteit, scope, datums en de letterlijke bron.
Na goedkeuring levert `neem-op` een nieuw document op met wijzigingshistorie.
Een wijziging van de bron sinds het voorstel blokkeert opname. De normale
validatie draait vóór het schrijven; publicatie/deployment blijft apart.

Voor later zelf bijwerken bestaan `maak_linkbewijs` en `verbruik_linkbewijs`:
256-bit willekeurig token, alleen SHA-256-hash bewaren, maximaal 48 uur,
gebonden aan aanbieder én regel, eenmalig. Zo'n link mag alleen voorstellen
opleveren. Er is nu geen publiek endpoint, login of portaal. Voor ingebruikname
zijn identiteitscontrole bij uitgifte, HTTPS, rate limits en atomair eenmalig
verbruik in duurzame opslag nog nodig. Geen tokens in logs of analyses opnemen.

## Controle en beperkingen

Tests: `python -m pytest -o addopts='' -q` vanuit `app/`.
Browser: `CHROME=/pad/chromium python mobielcheck/controle.py BASIS_URL` en
`python mobielcheck/ronde3.py BASIS_URL` vanuit de repositoryroot; Playwright
alleen als ontwikkeltool, geen download door deze scripts.

De oorspronkelijke 53 scenario's en twintig onafhankelijke auditvragen zijn
ongewijzigd. Oude tests voor het verbergen van naam-/bladerresultaten zijn
expliciet aangepast aan de nieuwe opdracht, met behoud van uitsluiting bij
zorgvragen. De eindcontrole staat bij de overdracht van het patchbestand.

Grenzen: regelgebaseerde taalherkenning; geen garantie dat iedere Nederlandse
formulering begrepen wordt. Een seizoensaanduiding zoals 'Kerstvakantie 2026'
krijgt geen verzonnen einddatum. Contractbronnen blijven snapshots, geen bewezen
geldigheidsperioden. Zonder toepasbare actuele aanbiederbevestiging blijft
instroom onbekend. Het nieuwe register is bewust nog niet met echte actuele
bevestigingen gevuld. Geen berichten, portal of automatische bronactualisatie.
