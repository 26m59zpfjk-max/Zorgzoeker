# 5B — professionele, controleerbare werkplek

Vereist eerst 5A op basiscommit 46bb89e3ea011a05930f0ff29ce4dcb9fc36d3ba.
Geen datamigratie, nieuwe abonnementen, modellen of externe diensten.

De kale start-URL verwijst naar /werkplek. /klassiek biedt de oude zoekpagina;
bestaande /?q= en GET-API-links blijven compatibel. Nieuwe invoer gebruikt POST.
Er is geen casusdatabase, localStorage of querycache. Rapportcache bevat uitsluitend
openbare kwaliteitsgegevens en vervalt bij een nieuwe datum of applicatie/datasetstart.
Tailscale-, host- en poortinstellingen blijven onaangeroerd.

De nieuwe kaarten groeperen brononderbouwde voorwaarden, onzekere kandidaten en
bewezen uitsluitingen. Onbekende wachttijden voldoen niet aan een limiet.
Meer kinderen vereist een keuze: gezamenlijk of afzonderlijke routes. Bronvermelding,
inhoudelijke controle en actuele inzetbaarheid zijn geen synoniemen.

Desktopvergelijking heeft criteriumrijen en aanbiederskolommen; mobiel per criterium.
Vergelijkselectie/context blijven behouden. Verschilfilter verbergt geen waarschuwingen.
Volledige profielvelden blijven in details beschikbaar. De kwaliteitswerklijst is
alleen lezen, filterbaar, op urgentie geordend en gepagineerd met 25 aanbieders.
De bestaande CSV en JSON exports blijven; een printbare bronchecklijst bevat geen
vrije vraagtekst of leeftijd. Geen automatische contact- of publicatiefuncties.

Twee bestaande UI-asserties zijn expliciet bijgewerkt: startpagina toont de preciezere
term Contractvermelding in bron; algemene meerkindvraag mag eerst de nieuwe
keuzestap tonen. De onderliggende eisen (contractfilter beschikbaar, geen ongefundeerde
resultaten) blijven. Benchmarkvragen, recallgrenzen en brondata zijn niet aangepast.

Tests: pytest vanuit app/; mobielcheck/ronde5.py BASIS_URL gebruikt lokale Chromium.
De browsertests wachten op response/URL/inhoud, met herhaalde vertraagde navigaties;
geen sleeps. Oudere browserbestanden blijven als historisch regressiemateriaal;
ronde4c.py verwacht bewust het oude kaartvergelijkontwerp en is geen 5B acceptatiescript.

Nog niet bewezen: WCAG-conformiteit, echte schermlezerbediening, professionele
inhoudelijke validatie en tijdwinst bij echte consulenten. Eerst de afgesproken
fictieve taakproef uitvoeren. Geen productie- of beschikbaarheidsgarantie.
Rollback: herstel beide codepatches samen; brondata zijn ongewijzigd. Herstart alleen
de bestaande private applicatie na afzonderlijke beoordeling door de beheerder.
