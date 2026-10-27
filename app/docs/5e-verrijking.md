# 5E — begrensde aanbiedersverrijking

Vereist 5D na 5A/5B. Geen automatische publicatie, actief schema of providercontacten per e-mail. Geen betaald model, sleutel of nieuwe afhankelijkheid vereist. Zoekverzoeken voeren nooit scraping uit.

Vanuit app/:

    python -m zorgzoeker.verrijking data/aanbieders.json identiteiten.json --uitvoer nieuwe-run.json

De invoer is een lijst met per aanbieder: aanbieder_id, website (HTTPS), expliciet_vrijgegeven (true), beoordelaar, bewijs_url (onafhankelijk domein), naam_hash (hashwaarde van het oorspronkelijke naamveld), gecontroleerd_op (ISO-datum) en toegangsvoorwaarden ('toegestaan'). Leg identiteit, datum en onafhankelijke onderbouwing bij die vrijgave vast. De operator is verantwoordelijk voor echte broncontrole; de toepassing kan een ingevoerde vrijgave niet als menselijke identiteit authenticeren. Bestaande afgeleide links zijn geen vrijgave. --inventariseer haalt alleen de homepage op voor identiteitsverkenning, levert geen inhoudelijke profielbevindingen op en vereist eveneens beoordeelde toegangsvoorwaarden.

Maximaal twaalf aanbieders per proefrun en twintig pagina’s per aanbieder. Eén synchronische worker, minimaal drie seconden tussen verzoekstarts per host. Robots wordt vóór inhoud opgehaald; onleesbaar/404/verbod stopt conservatief. 403/429/503 blokkeert het domein voor de rest van de run (geen automatische retry); plan een nieuwe run nooit vóór Retry-After. Geen redirect buiten het goedgekeurde origin, geen interne doelen, logins of query-URL’s. Maximaal2MB bron,12s timeout. ETag/Last-Modified gelden binnen één run; er is geen geactiveerde periodieke scheduler.

HTMLtekstextractie houdt quotes, uitsluitingen en scopeonzekerheid intact. Termen worden naar de bestaande taxonomie gekoppeld; dit bewijst geen expertise of dienstbinding. Alleen beperkte fragmenten worden opgeslagen, geen volledige HTML. Persoonsgerichte/medewerkers-/cliëntsignalen en e-mailfragmenten worden conservatief overgeslagen. Privacyfiltering blijft een extra reviewpunt; ze is geen garantie van volledige anonimisering. Niet-HTML/PDF en javascript-afhankelijke bronnen worden als handmatige controle gemeld; er is geen OCR of browsercrawler. Contractvelden zijn uitgesloten. Bestaande stops/wachttijdlogica blijft onaangeroerd.

Bevindingen bevatten bronURL/hash/datum, citaat, taxonomie, bron-/profielbinding, oude waarde en een conservatieve vergelijkingsstatus. Gewijzigde bytes bewijzen geen inhoudelijke wijziging; afwezigheid bewijst geen beëindiging. Scope is standaard niet vastgesteld. De reviewer kiest dienstscope en nieuwe waarde; een scraper maakt geen geverifieerde waarde.

Voor offline vrijgave maakt een reviewer een JSON met bevinding, nieuwe_waarde en beoordeling volgens het bestaande kwaliteitsschema. Gebruik scripts/voorstel_uit_verrijking.py met --beoordelaar en --expliciet-goedgekeurd. BronURL/citaat moeten overeenkomen, profielhash moet nog passen. Daarna geldt scripts/profielvoorstel.py neem-op met een afzonderlijke expliciete goedkeuring. Uitvoer is een nieuw bestand; de live dataset wordt niet overschreven.

## Proef en grenzen

docs/verrijkingsproef/offline-verkenning.json bevat een verkenning op twaalf eerder opgehaalde openbare homepage-snapshots (hash gecontroleerd), geen actuele crawl of nieuwe identiteitsvrijgave. Alleen bronmetadata/aantallen zijn behouden. Dit is geen representatieve onafhankelijke precisie/recallmeting; de websitevormen zijn nog niet volledig geclassificeerd.

Voor liveopschaling: twaalf representatieve websites selecteren en identiteit/toegangsvoorwaarden beoordelen, goldlabels vastleggen, daarna precision>=95%,recall>=80% op toegankelijke vooraf aangewezen feiten en nul onjuiste identiteitskoppelingen nastreven. Kritische uitsluitingen mogen nooit positieve expertise worden. Laat geblokkeerde bronnen afzonderlijk zien. Geen opschaling zolang die proef niet is goedgekeurd. Technische fixtures testen juist ook weigeringen, verkeerde hosts en ontbrekende goedkeuring.
