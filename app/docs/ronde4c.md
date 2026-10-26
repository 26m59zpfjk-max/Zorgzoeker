# 4C — controleerbare consulentenpilot

Basis: GitHub-main `169e0669a7a99eff9b04974a16a58bdf3975d9cc`, inclusief4A/4B.
Geen aanbiedersgegevens gewijzigd, geen commits/pushes/merges, geen betaalde dienst.

## Gebruik

`/werkplek` is de nieuwe, optionele consulentenflow. Zoek en vergelijk met POST;
vragen staan niet in de URL of titel. Er is geen casusdatabase, localStorage of
sessieopslag. De lopende formulieren dragen de context. Gebruik uitsluitend
fictieve vragen; browsers/infrastructuur kunnen niet door deze app worden
gegarandeerd. Responses gebruiken no-store en no-referrer. De bestaande GET- en
AI-routes blijven bestaan; GET-URLs kunnen nog steeds zoektekst bevatten.
De CLI zet toeganglogs uit; configureer ook reverse proxies zonder verzoekbodylogs.

De interpretatie kan zonder AI worden aangepast: leeftijden scheiden met `;`,
decimalen met komma, meerdere hulpvraagbegrippen en uitsluitingen kiezen.
Een algemene vraag vraagt om verduidelijking. Selecteer twee of drie aanbieders,
vergelijk en ga met dezelfde context/selectie terug. Een bronchecklijst bevat
openbare aanbieders-/routegegevens, bronversie en controlepunten, geen vraagtekst.
De verantwoordelijke gemeente moet door de consulent worden bevestigd; er is
geen automatische woonplaatsbeginselbeslissing of toewijzing.

`Zoekcontext` en `Beoordeling` zijn het gemeenschappelijke leesmodel voor normale
zoekresultaten, de werkplek en de AI-route. Alle beoordelingen bevatten dataversie,
inhoudelijk bronbewijs, per-leeftijd toelating, contractbron/geldigheid, instroom,
kwaliteit en controlepunten. Semantische score compenseert geen expertiseconflict.
Een bronvermelding is geen geldigheidsperiode. Bij6en14 verdwijnt een stop voor14
niet. Afgevallen leeftijd-/stopkandidaten zijn afzonderlijk raadpleegbaar.
Onbekende wachttijd wordt geen bewezen afwezig zorgaanbod.

## Kwaliteit vrijgeven en terugrollen

`/kwaliteit` is alleen lezen; CSV-export bevat geen casus. De gewone brongegevens
worden nooit automatisch overschreven. De bestaande offline voorstel- en review-
functies blijven de ingang voor correcties. Beoordeel bronidentiteit, scope en
inhoud; een werkende website bewijst geen expertise.

Vanuit `app/`, uitsluitend na inhoudelijke vrijgave:

```sh
python scripts/publiceer_kwaliteitspakket.py data/aanbieders.json docs/profielkwaliteit-2026-10-26/beoordelingen.json --uitvoer vrijgegeven-kwaliteit.json --expliciet-vrijgegeven
ZORGZOEKER_KWALITEIT_PAD=/absoluut/pad/vrijgegeven-kwaliteit.json python -m zorgzoeker
```

Het manifest bindt beoordelingen aan een dataset-hash; de beoordeling blijft ook
gebonden aan de afzonderlijke veldwaarde. Het script weigert bestaande uitvoer.
Bij een andere dataset faalt laden gesloten, in plaats van verkeerde reviews te
gebruiken. Een nieuwe dataset vergt een nieuw gecontroleerd manifest. Bewaar
vorige versies en zet bronpad en manifest samen terug voor rollback. Zonder manifest
worden aanwezige ingebedde beoordelingen gebruikt; ontbrekende beoordeling blijft
zichtbaar 'bron te controleren'. Er worden geen nieuwe verificaties verzonnen.
Tegenstrijdige/verlopen beoordelingen en gewijzigde hashes tellen niet als positief
expertisebewijs. Gelijke controledatums met conflicterende statussen zijn onzeker.
Lezen en publiceren zijn gescheiden; een later beveiligde beheeromgeving kan
hetzelfde leesmodel en bestaande voorstel/reviewfuncties gebruiken.

Dienstspecifieke regels kunnen een optioneel `dienst_id` krijgen. Een binding
wordt alleen toegepast bij die dienst; een andere dienst met dezelfde code neemt
de stop niet over. Zonder dienstkeuze bij expliciete diensten blijft een beperkte
regel onbevestigd. Een historische dienstbeschrijving wordt niet automatisch
omgezet naar een nieuwe dienst-id. Brondata blijven onveranderd.

## Grenzen en validatie

Regressies: `tests/test_4c.py`. Browser: `mobielcheck/ronde4c.py BASIS_URL`
met lokaal Chromium/Playwright; geen automatische downloads. De tests gebruiken
fictieve mutaties en openbare bestaande profielen, geen cliëntdata of providercontacten.
AI blijft standaard uit, de pilot vereist geen model of externe sleutel.

De werkplek toont criteria/controlepunten; volledige bestaande administratieve
profielvelden blijven via de bestaande zoekpagina/details beschikbaar. Dit is
geen vervanging voor dossier, beschikking, contractjurist of medische beoordeling.
De read-only werklijst heeft geen schrijf- of publicatie-API. Authenticatie,
organisatieafbakening en productieprivacybeoordeling zijn bewust nog latere stappen.

Niet vanuit deze ontwikkelomgeving uitvoerbaar: taakproef met6–8 echte consulenten
en2 beheerders, professionele inhoudelijke validatie en een echte schermlezertest.
Voer die vóór een echte gemeentepilot uit. Voorlopige doelen zijn80% juiste
kaartinterpretatie binnen10seconden,100% herkenning van stops en25% minder tijd
tot een verdedigbare shortlist, zonder meer foutieve aannames. Dit zijn doelen,
geen gemeten claims. Browsermetingen bewijzen geen WCAG-conformiteit.
