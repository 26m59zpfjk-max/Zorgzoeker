# 5D — Search-first

Basis: definitieve 5A/5B-overdracht op commit 46bb89e3ea011a05930f0ff29ce4dcb9fc36d3ba plus de eerder geleverde 5A en 5B patches. Niet rechtstreeks op alleen 4C toepassen.

De werkplek heeft een eigen basis en componentenstylesheet search.css. Klassieke routes en beheerschermen houden hun bestaande stijl. De nieuwe consulentenroute laadt geen stijl.css/5b.css, vermijdt een derde overridelaag en toont geen beheernavigatie.
Kaarten tonen relevante bronkenmerken, matchreden, leeftijdsoordeel, drie contractlabels en selectie. Stops, mismatches en expliciete wachttijdrestricties blijven zichtbaar. Gedetailleerde bron- en productinformatie gaat naar POST /aanbieder; de zoekvraag komt niet in de URL. Details, vergelijking en teruggaan behouden context/selectie.
Geen wijzigingen in brondata, matching, harde filters of privacyheaders. Geen nieuwe externe frontenddiensten. De printbare checklist en klassieke zoekroute blijven beschikbaar. Browserchecks gebruiken fictieve vragen; Safari, schermlezer en echte gebruikstests blijven afzonderlijk vereist.
