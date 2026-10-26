# Ronde 4a: controleerbare profielkwaliteit

Basis GitHub-main: `0839a02f35bc80efdd8a07b0ae49783e0ecfc216`.
Geen brondata gewijzigd. Het rapport en de CSV in `profielkwaliteit-2026-10-26/`
bevatten alle 189 profielen en een geprioriteerde werklijst voor Carlton/de bot.

## Wat feitelijk gecontroleerd is

197 openbare bron-URL's zijn op 26 oktober 2026 via gewone GET opgehaald/geprobeerd:
188 opgehaald, 7 controles mislukt, 2 HTTP-fouten. Van 114 afgeleide websitekoppelingen:
108 opgehaald, 5 mislukt, 1 HTTP-fout. 51 profielen hebben geen bekende website.
Bereikbaarheid, paginatitel en een kort tekstfragment zijn **geen** identiteits-
of expertiseverificatie. Alle 114 afgeleide koppelingen blijven een onderzoekstaak.
Er is geen betrouwbare basis om die automatisch naar geverifieerd te promoveren.

De officiële ROB-werkmap is opnieuw gedownload. SHA-256:
`dce423adc9586178a456df77cc893c37e196e922d7cfe7313360c3f180dfb281`.
Exacte vergelijking van naam, product, route/hoofdaannemer en bronrij leverde
493 waardegebonden beoordelingen op (naam, contractbron en/of productlijst).
Dit bewijst de snapshot van 23 oktober, geen geldigheidsperiode of vrije plek.
Geen gemeente of aanbieder is benaderd. Volledige HTML is niet in de patch opgenomen;
URL, responstoestand, hash, korte brontekst en controle-instant zijn bewaard.

Alle profielen zijn op veldniveau onderzocht op volledigheid, bronherleidbaarheid,
leeftijdsteksten, productroutes, onderaannemerschap, stops en wachtactualiteit.
De broncontrole is geen volledige handmatige herverificatie van alle zorginhoud.
Zonder aanvullende inhoudelijke controle blijft die informatie expliciet onzeker.
De strenge indicator `kern_voldoende_onderbouwd` vereist alle acht kernvelden;
0 volledig onderbouwde profielen betekent niet dat alle afzonderlijke gegevens fout zijn.

## Gebruik

Vanuit `app/`, uitvoermap moet nieuw zijn:

```sh
python scripts/controleer_profielen.py data/aanbieders.json --uitvoer rapport-nieuw --beoordelingen docs/profielkwaliteit-2026-10-26/beoordelingen.json --waarnemingen docs/profielkwaliteit-2026-10-26/waarnemingen.json
```

Zonder de twee optionele bestanden: uitsluitend offline structurele controle.
`--haal-openbare-bronnen-op` start een begrensde nieuwe openbare broncontrole.
Er is geen geactiveerde timer, agent, externe AI of automatische actie. Periodiek
kan hetzelfde commando expliciet gestart worden. `vergelijk_waarneming` signaleert
hashwijzigingen als openbare verandering, nooit als direct bevestigde zorgwijziging.
Een dynamische webpagina kan zonder betekenisvolle wijziging een andere hash hebben.
Ophaaltool: maximaal vier workers, vijf redirects, 4 MB per bron, time-outs,
geen cookies/authenticatie, geen lokale/private doeladressen. Alleen beheerders-
CLI; niet als onbeveiligde publieke URL-fetch-API aanbieden. Gebruik in productie
ook netwerk-egressregels tegen DNS-rebinding en ongewenste doelen.

`rapport.json` geeft vier statussen per veld: geverifieerd, bron te controleren,
tegenstrijdig/verouderd, ontbrekend. Verificatiemethode is afzonderlijk vastgelegd:
gecontroleerde openbare bron, rechtstreeks bevestigd, afgeleid of onbekend.
Een waarde/hash, bron, reviewer, controledatum, hercontroledatum en citaat zijn
vereist. Publicatie-/geldigheidsdatums worden alleen ingevuld als bekend.
Dubbelkandidaten worden nooit automatisch samengevoegd. Meerdere leeftijdsteksten
kunnen verschillende diensten betreffen en gelden niet automatisch als conflict.
Onbereikbaarheid bewijst geen bedrijfsbeëindiging.

## Correcties uitsluitend na review

`kwaliteit.voorstel` en CLI `scripts/profielvoorstel.py voorstel` maken een voorstel.
Invoer: `aanbieder_id`, `veld`, `nieuwe_waarde` (volledig Veld-object),
`beoordeling` en `soort`: openbare_verandering, rechtstreeks_bevestigd of vermoeden.
Een beoordeling heeft de structuur uit `beoordelingen.json`; de waarde_hash
wordt met `kwaliteit.hashwaarde` berekend. Een afleiding kan niet geverifieerd heten.
Een vermoeden is geen directe bevestiging.

`profielvoorstel.py neem-op DATASET VOORSTEL --beoordelaar NAAM --expliciet-goedgekeurd --uitvoer NIEUW.json`
levert na validatie een nieuw document met geschiedenis. Het originele bestand
blijft behouden; gewijzigde bron sinds het voorstel blokkeert opname. Nieuwe expertise,
websites of voorwaarden mogen uitsluitend uit het gecontroleerde bewijs komen.
Beoordelingen worden ongeldig zodra de gekoppelde veldwaarde wijzigt/veroudert.

Geen API-sleutels, abonnementen of betaalde diensten nodig. Hercontrole vereist
nog menselijke/inhoudelijke beoordeling, vooral de identiteit achter websitelinks,
expertise, dienstspecifieke toelating en actuele aanmeldmogelijkheden.
