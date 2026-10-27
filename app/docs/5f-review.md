# 5F — aparte reviewweergave

Vereist 5E. Configureer alleen in de bestaande private omgeving:

    ZORGZOEKER_VERRIJKING_REVIEW=/absoluut/pad/nieuwe-run.json python -m zorgzoeker

GET /beheer/verrijking toont oude waarden naast bronfragmenten, identiteit, scope en vervolgvragen. Geen POST-, goedkeurings- of publicatie-endpoint. Een ontbrekend pakket geeft503; een verkeerde datasetbinding400. Publicatie blijft via de offlineworkflow uit5E. Dit is geen rechtenbeheersysteem of aanvullende beveiligingsgrens; behoud Tailscale en beperk beheerbereikbaarheid in de bestaande private configuratie. De app wijzigt die infrastructuur niet.

Alle runs blijven voorstellen, ook als geen conflict werd gevonden. Nieuwe gegevens komen niet vanzelf in de zoekindex. Geen extra providerdata in de consulentenlijst. JSONHTML wordt automatisch geescaped. De bestaande /kwaliteit werklijst blijft beschikbaar voor beheer.
