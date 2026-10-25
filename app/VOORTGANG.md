# Voortgang Zorgzoeker

Korte stand van het lokale prototype. Bij een onderbreking hier verdergaan.

## Stap 1 — datalaag

Gedaan in deze commit als de tests groen zijn.

- Package `zorgzoeker` met configuratie (`ZORGZOEKER_DATA`, anders `data/aanbieders.json`, anders de fixture).
- `data/fixture_aanbieders.json`: 12 fictieve aanbieders, namen beginnen met `FICTIEF -`, bronnen op example.org.
- Validatie volgens `SCHEMA.md`: `python -m zorgzoeker.valideer pad/naar/aanbieders.json`.
- Tests: `tests/test_validatie.py`, `tests/test_wachttijd.py`.

## Stap 2 — zoekfunctie

Gedaan.

- `zorgzoeker/synoniemen.py`: jeugdhulptermen (autisme/ASS, angst, trauma, LVB, gezinshuis, dagbesteding, ambulant, verslaving, leeftijden) en kernen in het Rijk van Nijmegen.
- `zorgzoeker/zoeken.py`: normalisatie, herkenning van leeftijd, plaats/gemeente, productcode en contractstatus, BM25 plus die signalen, en een korte reden per treffer. Geen wachttijd in de reden.
- Handmatig gecontroleerd: 18 voorbeeldvragen geven de verwachte eerste treffer op de fixture. De formele testlijst volgt in stap 4.

## Dataset

`data/aanbieders.json` is de standaarddataset: 191 aanbieders, waarvan 25 niet gecontracteerd. `data/producten.json` hoort erbij. Validatie draait tegen fixture én deze dataset. Zoektests: `tests/zoekvragen.yaml` (fixture) en `tests/zoekvragen_dataset.yaml` (echte data). Bij een afgeleid contract toont de kaart de toelichting.

## Zoeken op productcode

Een vraag als "autisme en angst" matcht ook de omschrijving van productcodes (en type aanbod), lager dan expertise van de website. De reden zegt `Past via productcode X (omschrijving)`. Het expertiseveld in de data blijft ongewijzigd.

## Stap 3 — webinterface

Gedaan. `python -m zorgzoeker` start FastAPI op poort 8741. Zoekveld, filters, kaarten met bron en label, en een vergelijking van twee of drie aanbieders. Wachttijd met label onbekend wordt als onbekend getoond.

## Stap 4 — zoektests en API-smoke

Gedaan. 18 zoekvragen in `tests/zoekvragen.yaml` tegen de fixture, plus validatie van `data/aanbieders.json` en een rooktest van de pagina's.

## Stap 5 — schermafbeeldingen

Gedaan, tegen `data/aanbieders.json` (191 aanbieders). Drie voorbeeldzoekvragen en een vergelijking van Novaera, Shelterzorg en Gezinshuis Koru. De app draait op poort 8741.
