# Herstel van de vijf auditbevindingen

Werkbranch: `fix/zoekbetrouwbaarheid`, gebaseerd op upstream
`b606aae563f6344cc24664deecc8412bcbb06d41`. Geen merge naar main.

1. Leeftijd: herkenning van onder meer `14-jarige`, `14 jarige`, `zoon van 10`
   en `dochter van 7`. Een bekende ongeschikte leeftijd valt af. ‘Tot 18’ is
   exclusief, ‘tot en met 18’ inclusief. Onbegrensde kinder-/gezinszorg wordt
   niet uitgesloten door een grens voor een andere dienst, zoals 18+ wonen.
2. Negatie: ontkende diagnoses leveren geen positief matchsignaal op.
   Expliciet ongewenste methoden/zorgvormen worden uitgesloten, met uitleg.
   Positieve klachtenfrasen met ‘niet’ blijven intact, zoals ‘niet meer naar school’.
3. Gemeente: contractdekking en vestigingsplaats zijn aparte filters.
   Regionale aanbieders met onbekende vestiging verdwijnen daardoor niet meer.
4. Contracten: 688 bronregels voor 166 aanbieders, per product en hoofd-/onderaannemerroute.
   Stops worden in hun gemeente-/productcontext getoetst. De bestaande patches
   voor AlkaZorg en Apollis Zorg zijn bevestigd tegen de werkmap. De contractdatum
   gaat mee naar vergelijken; een onbekende periode blijft ook daar onbekend.
5. Zorginhoud: zonder inhoudelijk bewijs geen aanbeveling op basis van leeftijd,
   plaats of gender. Volledige dekking gaat vóór gedeeltelijke dekking, ongeacht
   de tekstscore. Een gedeeltelijke match benoemt de ontbrekende bevestiging.
   Een generieke ggz-code bewijst geen OCD/trauma-expertise. Ongeldige datasets
   blokkeren het zoeken; onbewezen wachttijden worden niet als geverifieerd getoond.

Een bijkomende correctie houdt BM25 op een vaste corpusbasis: anders verdwenen
unieke naamtreffers zoals AlkaZorg juist nadat de overige kandidaten afvielen.
Voor rouwverwerking of verslavingszorg blijft een expliciete bronvermelding in
het zorgaanbod geldig bewijs; een generieke ggz-code blijft onvoldoende.

## Bronnen en herhaling

ROB-overzicht 23 oktober 2026:
<https://robregionijmegen.nl/wp-content/uploads/2026/10/Totaaloverzicht-gecontracteerde-aanbieders-23okt26.xlsx>

SHA-256: `dce423adc9586178a456df77cc893c37e196e922d7cfe7313360c3f180dfb281`.
Opnieuw opgehaald en gelijk aan het eerder gecontroleerde auditbestand.
Zeven regiogemeenten bevestigd via <https://robregionijmegen.nl/over-ons/>.
De dataset bevat per regel het tabblad en de bronrij; de import is reproduceerbaar
met `scripts/importeer_contracten.py`. Geen nieuwe expertise of contractperiodes toegevoegd.

De twintig fictieve auditvragen staan ongewijzigd in `tests/audit_scenarios.json`.
Veiligheidscontroles staan in `tests/test_audit_scenarios.py`; concrete ranglijsten
vóór/na en onzekerheden in [audit-hertest.json](audit-hertest.json).
De oorspronkelijke 53-vragenlijst en recall-drempel zijn niet aangepast.
De bestaande leeftijdstest is aangescherpt: de 15+-aanbieder moet afwezig zijn
voor een 14-jarige, in plaats van met alleen een waarschuwing te verschijnen.

## Grenzen

- Voor Gezinshuis Koru en Gezinshuis Hemma ontbreekt een exacte productgebonden
  koppeling aan een ROB-bronrij. Hun specifieke contractroute blijft onbekend.
- Buiten de bewezen peildatum wordt geen contractgeldigheid toegezegd. Ook
  actuele instroom vraagt bevestiging; een publicatie is geen plaatsgarantie.
- Negatie is regelgebaseerd. Niet elke complexe Nederlandse formulering wordt
  begrepen. Bijvoorbeeld handen wassen uit angst voor besmetting wordt geen
  verzonnen OCD-diagnose. Onbekende klachten vragen verdere verduidelijking.
- Een behandelmethode die alleen in een geverifieerde organisatienaam staat
  blijft hooguit een gemarkeerde gedeeltelijke match. Expliciet aanbod weegt zwaarder.
- ‘Geen EMDR’ verbergt aanbieders die EMDR noemen. Zij kunnen ook andere
  methoden bieden; dat wordt niet zonder bron aangenomen.
- Oudere datasets zonder contractregister blijven leesbaar, met een waarschuwing
  dat productgebonden voorwaarden ontbreken. De nieuwe concrete contracttoets
  vereist het bronregister; historische ja/nee-labels worden niet naar andere jaren doorgetrokken.

Geen extra afhankelijkheden of betaalde diensten nodig. Alle zorgvragen in de
tests zijn fictief; aanbiedersinformatie komt uit openbare bronnen.

## Uitgevoerde controles (25 oktober 2026)

- Volledige suite: **108 geslaagd**, één deprecatiewaarschuwing van de externe
  Starlette/httpx-testclient. Dit omvat de bestaande tests, nieuwe regressies en
  alle twintig oorspronkelijke auditvragen. Oorspronkelijke evaluatie: 53/53
  voldoen aan de ongewijzigde recall-drempel; dat blijft geen precisiegarantie.
- Alle 32 bestaande mobiele/desktopcontroles opnieuw geslaagd in Chromium,
  tegen de uiteindelijke applicatie op 390 en 1280 pixels.
- Beide datasets door de aangescherpte CLI-validatie; geen fouten.
- Herimport van de openbare ROB-werkmap levert exact dezelfde 688 regels en
  dataset op. AlkaZorg/Apollis Zorg getoetst op zowel geblokkeerde als toegestane
  gemeente-/productcombinaties; alternatieve hoofdaannemerroute apart getest.
- Zoeken: circa 13,4 ms mediaan bij 30 herhalingen; indexopbouw circa 6 s in deze
  omgeving. Geen schaal- of gelijktijdigheidsclaim.

Ruwe uitvoer: [pytest](testresultaten.txt) en [mobiel/desktop](mobiele-controles.txt).
Herhalen: voer `python -m pytest -o addopts='' -q` uit vanuit `app`.
Start daar ook `python -m zorgzoeker`. Voer daarna vanuit de repositoryroot
`CHROME=/usr/bin/chromium python mobielcheck/controle.py http://127.0.0.1:8741`
uit. Playwright/Chromium zijn alleen nodig voor de aanvullende browsercontrole.
