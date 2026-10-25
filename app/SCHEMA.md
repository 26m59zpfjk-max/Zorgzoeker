# Dataschema Zorgzoeker v0.2 (25-10-2026)

Bestand: `data/aanbieders.json` (UTF-8). Eén object:

```json
{
  "meta": { "schema_versie": "0.2", "regio": "Rijk van Nijmegen", "gegenereerd_op": "YYYY-MM-DD" },
  "bronnen": [
    { "id": "src-...", "naam": "...", "url": "https://...", "opgehaald_op": "YYYY-MM-DD", "soort": "contractlijst|register|zorgkaart|sociale-kaart|website|kaart|overig", "opmerking": "..." }
  ],
  "aanbieders": [
    {
      "id": "slug-van-naam",
      "naam": Veld<string>,
      "kvk_nummer": Veld<string|"onbekend">,
      "vestigingen": Veld<[{ "plaats": "...", "postcode": "...", "adres": "..." }]>,
      "website": Veld<string|"onbekend">,
      "type_aanbod": Veld<[string]>,
      "gecontracteerd_regio": Veld<"ja"|"nee"|"onbekend">,
      "hoofdaannemer": Veld<string|"onbekend">,   // alleen bij onderaannemers (zie regel 7)
      "productcodes": Veld<[{ "code": "...", "omschrijving": "..." }]>,
      "expertise": Veld<[string]>,
      "doelgroepen": Veld<[string]>,
      "werkgebied": Veld<[string]>,
      "wachttijd": Veld<string|"onbekend">,
      "beschikbaarheid": Veld<string|"onbekend">,
      "gevonden_via": ["src-..."]
    }
  ]
}
```

`Veld<T>` = `{ "waarde": T, "bron_url": string|null, "opgehaald_op": "YYYY-MM-DD"|null, "label": "geverifieerd"|"afgeleid"|"onbekend", "toelichting": string (optioneel) }`

Regels (worden door tests afgedwongen):
1. Label `geverifieerd` of `afgeleid` => `bron_url` en `opgehaald_op` zijn verplicht.
2. Label `onbekend` => `waarde` is `"onbekend"` (of lege lijst bij lijstvelden).
3. `wachttijd` en `beschikbaarheid` zijn `onbekend` tenzij de aanbieder of regio ze openbaar publiceert; dan bevat `toelichting` de peildatum zoals gepubliceerd. Nooit schatten.
4. `geverifieerd` = letterlijk zo in de bron. `afgeleid` = logisch afgeleid uit een bron (toelichting verplicht).
5. Alleen organisatiegegevens. Bij eenmanszaken/zzp'ers: geen woonadres (alleen plaats), geen privételefoon, geen BIG-nummers of namen van individuele medewerkers buiten de handelsnaam.
6. `gevonden_via` verwijst naar `bronnen[].id` en toont de dekking per bron.
7. Onderaannemers (op ROB-tabblad 'Onderaannemers', of gezinshuis onder een gecontracteerde franchise-/moederorganisatie): `gecontracteerd_regio` = `ja`, label `afgeleid`, toelichting begint letterlijk met `Onderaannemer van <naam>`; daarnaast veld `hoofdaannemer` (waarde = naam gecontracteerde organisatie, met bron_url/opgehaald_op/label). Andere aanbieders hebben géén veld `hoofdaannemer`.
   Weergaveregel UI: toon bij deze aanbieders "gecontracteerd: onderaannemer van <hoofdaannemer>" in plaats van het label "afgeleid".

## Optionele uitbreiding: contractregister

Een algemene regionale vermelding bewijst geen product- of periodegebonden
contractgeldigheid. Bij zoeken en vergelijken gaat de onderstaande brongebonden
toets vóór de algemene vermelding. Ontbrekende routes blijven onbekend.

`contractregister` op documentniveau bevat `bron_url`, `peildatum`,
`opgehaald_op`, `sha256` van de openbare werkmap, `gemeenten_bron`,
`toelichting` en `regels` (lijst). Elke regel bevat:

- `aanbieder_id`: een bestaande aanbieder;
- `productcode`: een product dat bij die aanbieder in de dataset staat;
- `hoofdaannemer`: de letterlijk vermelde naam, of `null` voor rechtstreeks;
- `gemeenten`: alleen aantoonbare contractdekking, los van vestiging/werkgebied;
- `opmerkingen`: letterlijke bronvoorwaarden, inclusief toepasselijke voorwaarden van de hoofdaannemer;
- `bewijs`: lijst met `tabblad` en `rij` in de genoemde werkmap.

De publicatiedatum van een overzicht is een momentopname, geen ingangs- of
einddatum. Een andere gevraagde datum of een ontbrekende route levert
`onbekend` op. Een toeleidingsstop wordt per gemeente, product en route getoetst;
een andere niet-gestopte route blijft een mogelijkheid. Afwezigheid van een stop
bewijst geen beschikbare plaats. Bij afgeleide negatieve contractlabels zegt de
weergave daarom ‘niet aangetroffen’, geen bewezen contractloosheid.

Wachttijd/beschikbaarheid mag alleen bekend zijn met label `geverifieerd`, een
bron, geldige ophaaldatum en een expliciet vermelde, geldige peildatum die niet
na het ophalen ligt. Gepubliceerde samengestelde wachttijden blijven als tekst
beschikbaar; de zoekmachine rekent ze niet om tot een algemene belofte. De
interface toont ophaaldatum en peildatum afzonderlijk. Een ongeldig bestand
wordt niet geïndexeerd; gezondheid meldt `fout`, zoeken geeft HTTP 500 met
validatiefouten. Losse veldweergave onderdrukt ongeldige wachttijden eveneens.
