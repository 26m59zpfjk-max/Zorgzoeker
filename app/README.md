# Zorgzoeker

Lokaal zoekprototype voor gemeentelijke jeugdconsulenten in de regio Rijk van Nijmegen. Je typt een zorgvraag in gewoon Nederlands en krijgt een gerangschikte lijst jeugdhulpaanbieders, met per gegeven een bron, een ophaaldatum en een label.

Dit prototype draait volledig op de eigen computer. Er zijn geen betaalde API's, geen externe taalmodellen en geen hosting. `data/aanbieders.json` is de standaarddataset (189 aanbieders, waarvan 21 niet gecontracteerd, schema 0.2, Rijk van Nijmegen). `data/producten.json` bevat de regionale productcodes. `data/begrippen.yaml` koppelt gewone taal aan zorgcategorieën. `data/fixture_aanbieders.json` blijft de fictieve set voor de zoektests met verwachte fixture-treffers.

## Installeren

Python 3.11 of nieuwer.

```bash
python3 -m pip install -r requirements.txt
```

## Starten

Vanuit de projectmap:

```bash
python3 -m zorgzoeker
```

Daarna staat de interface op [http://127.0.0.1:8741](http://127.0.0.1:8741). De server luistert standaard alleen op `127.0.0.1`, niet op het netwerk. Een ander adres kan met `ZORGZOEKER_HOST`.

Een andere poort: `ZORGZOEKER_POORT=8750 python3 -m zorgzoeker`.

Zoekvragen worden niet in een logbestand weggeschreven.

## Tests

```bash
python3 -m pytest
python3 -m zorgzoeker.valideer data/fixture_aanbieders.json
```

De twintig oorspronkelijke fictieve auditvragen staan ongewijzigd in
`tests/audit_scenarios.json`; `tests/test_audit_scenarios.py` toetst de
veiligheidsvoorwaarden. Hertesten met ranglijsten vóór/na:

```bash
python3 scripts/evalueer_audit.py docs/audit-hertest.json
```

Bekende leeftijdsmismatches en uitgesloten methoden vallen af vóór de
rangschikking. Volledige zorginhoudelijke dekking komt altijd vóór gedeeltelijke
dekking. Een gedeeltelijke match noemt welke kenmerken niet in de bron zijn
bevestigd; onbekende informatie wordt niet als afwezig aanbod uitgelegd.

`gemeente` toetst regionale contractdekking (of het bekende werkgebied van een
niet-gecontracteerd alternatief); `vestigingsplaats` is een apart filter.
`op_datum=YYYY-MM-DD` vraagt om contractgeldigheid op die datum. Een brondatum
bewijst geen geldigheidsperiode: buiten de vastgestelde brondekking blijft het
antwoord onbekend. Dezelfde context gaat mee naar de vergelijking.

Het optionele `contractregister` bevat 688 openbare ROB-bronregels voor 166
aanbieders, met product, gemeente, hoofd-/onderaannemerroute en beperkingen.
Actualiseren vanuit de openbare, gedownloade werkmap (geen betaalde dienst):

```bash
python3 scripts/importeer_contracten.py /pad/naar/Totaaloverzicht-gecontracteerde-aanbieders-23okt26.xlsx
python3 -m pytest
```

De importeur accepteert uitsluitend exacte namen en reeds bekende productcodes.
Een andere bronversie vereist een bewuste controle van bron-URL, publicatiedatum,
tabbladen en regiogemeenten in het script. Er worden geen contractperiodes of
ontbrekende routes ingevuld. Zie [wijzigingen en grenzen](docs/zoekbetrouwbaarheid.md).

Validatie tegen een later aangeleverd bestand:

```bash
python3 -m zorgzoeker.valideer pad/naar/aanbieders.json
python3 -m pytest tests/test_validatie.py tests/test_wachttijd.py --aanbieders pad/naar/aanbieders.json
```

`tests/zoekvragen.yaml` bevat de zoektests tegen de fixture, omdat de verwachte treffers daarbij horen. `tests/test_dataset.py` controleert `data/aanbieders.json`.

## Aanvullende controles na de audit

Zie [de vervolgfixes](docs/vervolg-herstel.md) voor stops bij vrije tekst,
negaties, decimale leeftijden en verouderde wachttijden. Het standaardbeleid
voor wachttijden is 30 dagen vanaf de peildatum, instelbaar met
`ZORGZOEKER_WACHTTIJD_MAX_DAGEN`. Een bekende toeleidingsstop veroudert niet
mee met een wachttijdpublicatie.

## Echte dataset inpluggen

1. Lever het bestand aan volgens [SCHEMA.md](SCHEMA.md).
2. Zet het neer als `data/aanbieders.json`, of wijs een ander pad aan:

```bash
ZORGZOEKER_DATA=/pad/naar/aanbieders.json python -m zorgzoeker
```

`data/aanbieders.json` gaat vóór de fixture. `ZORGZOEKER_DATA` gaat vóór allebei. De app leest het bestand alleen lokaal.

## Architectuur

Alles blijft in dit proces. Er gaat geen zoekvraag naar een externe dienst.

- `zorgzoeker/laden.py` leest het JSON-bestand. `ZORGZOEKER_DATA` wint, anders `data/aanbieders.json`, anders de fixture.
- `zorgzoeker/valideer.py` controleert bron, datum, label en de regel dat een wachttijd alleen mag als er een bron en een peildatum zijn.
- `zorgzoeker/zoeken.py` normaliseert de tekst, herkent leeftijd, plaats, productcode en contractstatus, en koppelt gewone woorden via `data/begrippen.yaml` aan een categorie. Expertise weegt zwaarder dan type aanbod of een productcode. Bestaat de categorie nergens, dan volgt de bovencategorie als breder resultaat. De reden citeert alleen tekst die in de data staat. Er wordt geen expertise bijgeschreven. Een onderaannemer wordt getoond als gecontracteerd via de hoofdaannemer.
- `zorgzoeker/app.py` serveert de pagina's. Kaarten en de vergelijking tonen per veld het label, de bronlink en de ophaaldatum.

Er staan geen cliëntgegevens in de code, de fixtures of de logs.
