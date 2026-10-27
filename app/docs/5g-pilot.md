# 5G — demonstratie Berg en Dal

Deze patch volgt op de definitieve 5A/5B +5D/5E/5F-overdracht. Geen herapplicatie van oudere patches. Alleen fictieve casussen; geen gemeentelijke goedkeuring voor echte cliëntgegevens.

Gemeente is nu uitsluitend expliciete invoer. Genoemde plaatsen blijven zachte geografische context; ze filteren geen contractroutes. Bekende aliases (Groesbeek/Berg en Dal) blijven behouden. Niet-herkende expliciete gemeenten leveren een invoerfout in plaats van een vervangende gemeente. De klassieke index, gedeelde beoordeling en optionele AI-route gebruiken dezelfde scheiding.

POST /api/zoek voegt schema_versie=5G, groepen en aantallen toe. De lijsten onderbouwd/kandidaten/uitgesloten zijn onderling disjunct. Elke reguliere treffer heeft resultaatstatus, ook in de compatibele resultatenlijst. Die laatste blijft de historisch gefilterde indexlijst (bijvoorbeeld zonder onbekende wachttijden); zij is geen lijst van gegarandeerd geschikte aanbieders. Voor volledige zichtbare kandidaten de groepen gebruiken. GET /api/zoek behoudt volledige_match als tekstuele dekking, met expliciete betekenis en resultaatstatus. Selectie-/vergelijkweergaven kunnen uitgesloten aanbieders tonen voor raadpleging met hun afwijzing.

Bij kandidaten verschijnt geen nulresultaatmelding. Het resultaatgedeelte is mobiel compacter; leeftijdsnotatie gebruikt gehele getallen of Nederlandse decimalen. Harde waarschuwingen blijven zichtbaar. Bronnen, contractdetail en beheer blijven apart.

De 18+-stop van Ambulatorium wordt aan zijn eigen tekstdeel getoetst; een plaatsnaam in de voorafgaande jeugd/intakezin verandert de scope niet. HTML-foutpagina’s tellen niet als geldige robots.txt-toestemming.

Contractstatus wordt niet positiever gemaakt: de beschikbare momentopname bewijst geen actuele periode, hulpvorm of toewijzing. De redenen zijn gestructureerd beschikbaar onder contract.redenen_onzeker. Geen aanbiedersgegevens of contractvoorwaarden gewijzigd.

Tests: pytest vanuit app/; mobielcheck/ronde5g.py BASIS_URL met lokaal Playwright/Chromium. Screenshots kunnen via ZORGZOEKER_SCREENSHOTS naar een eigen artefactmap. Geen screenshots of testcache in de applicatiebron nodig.
