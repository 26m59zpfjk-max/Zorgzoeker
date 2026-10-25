# Vervolgpatch: resterende zoekproblemen

Deze patch komt **bovenop de eerder geleverde zoekbetrouwbaarheidspatch**.
Werkbranch: `fix/resterende-zoekproblemen`. Geen wijzigingen aan main of aan
aanbiedersgegevens. Geen nieuwe betaalde diensten of afhankelijkheden.

1. Stops worden toegepast bij vrije tekst, naamzoekacties en alleen filters,
   ook zonder herkend onderwerp/productcode. Gemeente-/productscope blijft gelden.
2. Buiten de contractpeildatum blijft het contract onbevestigd, maar routes en
   bekende stops verdwijnen niet. Zonder bewezen einde/opheffing blijft de
   beperking blokkerend. Een expliciete einddatum blijft gerespecteerd.
3. `EMDR niet gewenst bij trauma` behoudt trauma: een achter het begrip
   geplaatste ontkenning blijft bij dat begrip. Positieve klachtenfrasen zoals
   `niet meer naar school` blijven behouden.
4. `17,5 jaar`, `17.5 jaar`, `zoon van 17,5` en `14jr` worden herkend zonder
   afronden. ‘Tot 18’ laat 17,5 toe en sluit 18 uit; ‘tot en met 17’ en
   ‘8 t/m 17’ omvatten ook 17,5. 18+-aanbieders vallen voor deze leeftijd af.
5. Wachttijden met `±`, `~`, `≈`, `+/-`, `indicatie`, `indicatief`, `verwachte`
   en eerdere schattingswoorden worden geweigerd. De peildatum bepaalt de
   ouderdom; recent ophalen maakt een oude publicatie niet actueel.

Actualiteitsbeleid: standaard **30 dagen**, instelbaar via
`ZORGZOEKER_WACHTTIJD_MAX_DAGEN` (niet-negatief geheel getal). Dit is een
softwaregrens, geen feit of garantie over een aanbieder. Na die grens toont de
app de actuele wachttijd als onbekend, met ouderdom en bronlink. De historische
tekst blijft beschikbaar als `publicatie_tekst`, maar telt niet mee voor een
maximale-wachttijdfilter. Oude publicaties blijven schema-geldig bewaarbaar.
Toeleidingsstops vallen niet onder deze verouderingsregel.

De API levert `verouderd`, `peildatum_leeftijd_dagen` en `publicatie_tekst`.
Kaarten en vergelijken vermelden de verouderde bronstatus. Een bijkomende
correctie ondersteunt ook de eenheden `1 week` en `1 dag` in het wachttijdfilter.

Regressies: `tests/test_resterende_problemen.py`, met positieve én negatieve
gevallen. Bestaande gemeentetests eisen nu ook bij alleen filters uitsluiting
van bekende stops. De oude fictieve wachttijd van 15 september wordt nog als
publicatie gecontroleerd, maar niet meer als actuele wachttijd gepresenteerd.
Recall-drempel en de twintig oorspronkelijke auditvragen blijven ongewijzigd.

## Eindcontrole

- Volledige suite: **135 geslaagd**, één externe Starlette/httpx-deprecatiewaarschuwing.
- 27 nieuwe regressiegevallen voor deze vervolgpunten, inclusief grensgevallen,
  toegestane routes en echte leeftijdsgrenzen.
- Twintig oorspronkelijke fictieve auditvragen opnieuw geslaagd; de bestaande
  53-vragenevaluatie voldoet aan de ongewijzigde recall-drempel.
- Alle 32 mobiele/desktopcontroles opnieuw geslaagd in Chromium.
- Beide aanbiedersbestanden slagen voor de CLI-schemavalidatie. Geen wijziging
  van aanbiedersdata, bronwaarden of contractvoorwaarden.

Ruwe uitvoer: [pytest](vervolg-testresultaten.txt) en
[browsercontroles](vervolg-mobiele-controles.txt).
