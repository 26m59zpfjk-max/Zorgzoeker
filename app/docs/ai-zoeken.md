# Ronde 4b — optionele lokale AI-zoekpilot

Basis: `0839a02f35bc80efdd8a07b0ae49783e0ecfc216` **na** toepassing van
`zorgzoeker-4a-profielkwaliteit.patch`. Geen brondata of bestaande zoekalgoritmen
vervangen. De normale zoekpagina en `/api/zoek` blijven beschikbaar.

## Architectuur en begrenzing

1. Lokale Qwen2.5-1.5B-Instruct (GGUF Q4_K_M) stelt gestructureerde zoekbegrippen
   met letterlijke citaten voor. Geen diagnoseveld en geen aanbiederfeiten uit
   het model. Niet letterlijk genoemde klinische signalen heten `mogelijk`.
2. De consulent ziet de interpretatie en kan leeftijden, problematiek, gewenste
   hulp en uitsluitingen aanpassen. Zoeken vereist expliciete bevestiging.
   Leeftijd, gemeente/product/datum en negaties uit de originele vraag blijven
   afzonderlijk verwerkt; het taalmodel kan ze niet stilzwijgend herschrijven.
3. Multilingual-e5-small (ONNX) rangschikt brongebonden dienstteksten. Een kleine
   in-memory index volstaat voor 189 aanbieders; geen vectorcloud nodig.
4. Semantische gelijkenis is geen expertisebewijs. Alleen bevestigde bronvelden
   kunnen zorginhoud dragen. Afgeleide websites/expertise worden niet opgenomen.
   Leeftijd, product, gemeentelijke dekking, route en stops blijven harde regels.
   Een stop blijft vindbaar maar krijgt `beschikbaar: nee`, nooit een inzetgarantie.
   Inhoudelijke overeenkomst, contracttoets en beschikbaarheid zijn aparte assen.

`diensten` is een optionele lijst binnen een aanbieder. Elke dienst heeft een
unieke `id`, `naam` en eigen brongebonden `expertise` (Veld-object). Optioneel:
`doelgroepen`, `type_aanbod`, `productcodes`, `beschikbaarheid`, `wachttijd`,
`vestigingen`, `uitsluitingscriteria`, `toelatingsvoorwaarden`, `toelatingsregels`.
Expertise op aanbiederniveau wordt **niet** naar ontbrekende dienstexpertise gekopieerd.
Zonder diensten blijft één expliciet gemarkeerde aanbiedersprofieleenheid over:
dienstscope onbekend, geen automatische expertise-productkoppeling.

Bestaande velden met `label: geverifieerd`, bron op de eigen geverifieerde website
en ophaaldatum mogen voor de pilot als bestaand bronbewijs worden gebruikt.
Dat is niet hetzelfde als een nieuwe inhoudelijke herbeoordeling in 4a; de bronstatus
blijft in het resultaat zichtbaar. Nieuwe/afgeleide velden moeten eerst via 4a
worden gecontroleerd. Een aanwezige ongunstige/verlopen kwaliteitsbeoordeling
wordt niet door een gunstig legacy-label gecompenseerd.

Een gestructureerde `toelatingsregel` kan bijvoorbeeld `soort: geslacht`,
`waarde: meisjes`, of `soort: uitsluit_concept`, `waarde: crisis` hebben, met
geverifieerde eigen bron, ophaaldatum en label. Alleen zulke onderbouwde regels
worden automatisch toegepast. Vrije toelatingsvoorwaarden blijven zichtbaar en
vereisen inhoudelijke beoordeling; een AI maakt daar zelf geen nieuwe regels van.

## Werkelijk getest — nog niet geschikt als standaardzoekmachine

60 bevroren fictieve vragen op 14 expliciete fictieve profielen/diensten.
De referentie is vooraf handmatig vastgelegd door de implementerende AI, **niet**
onafhankelijk door een jeugdprofessional. Laat Carlton die labels beoordelen.
De bestaande twintig auditvragen en 53-vragenevaluatie zijn daarnaast behouden.
Geen test die alleen controleert of één gewenste aanbieder ergens voorkomt:
precision/recall en TP/FP/FN op top 5, exacte resultaatsets, beste eerste resultaat,
interpretatie en expliciete harde fouten worden gerapporteerd.

Werkelijk lokaal uitgevoerd: Qwen2.5-1.5B en multilingual-e5-small. Een eerste
losse proef met Qwen2.5-0.5B was onvoldoende en is niet als eindmodel gekozen.
Na aanscherping van de zoeklaag zijn de vastgelegde echte interpretaties opnieuw
gebruikt met echte embeddings; die herhaling doet geen nieuwe LLM-calls.
De originele interpretatietijden blijven apart herkenbaar. De benchmark gebruikt een 60-secondenlimiet; de webpilot 20 seconden en kan dus vaker terugvallen. Er is geen mock
gebruikt om modelkwaliteit te claimen. Unit-/API-tests gebruiken juist wel mocks
voor foutafhandeling, privacygrenzen en harde voorwaarden.

Eindmeting (`ai-pilot/vergelijking.json`):

| Maat | Bestaande regels | AI-pilot |
|---|---:|---:|
| Juiste matches top 5 | 68 | 76 |
| Onterechte matches top 5 | 3 | 22 |
| Gemiste matches top 5 | 27 | 19 |
| Precision@5 | 95,8% | 77,6% |
| Recall@5 | 71,6% | 80,0% |
| Exacte resultaatset | 38/60 | 34/60 |
| Mediane totale tijd | 2,4 ms | 7,8 s |

AI: 41/60 juiste eerste resultaten, 31/60 exact juiste conceptinterpretaties,
16/60 terugvallen op bron-/zoekregels; 0 gevonden overtredingen van de expliciet
getoetste leeftijd-/gemeente-/stop-/onderaannemercontroles. Die nul is geen bewijs
voor alle denkbare voorwaarden. De lagere precisie en interpretatiefouten maken
professionele beoordeling en verdere onafhankelijke evaluatie noodzakelijk.
Een pilot met hoger recall en lagere precisie is geen bewezen algemene verbetering.

Reproduceer vanuit `app/` met lokaal geïnstalleerde modellen:

```sh
python scripts/vergelijk_ai_zoeken.py --e5-model PAD/e5.onnx --e5-tokenizer PAD/tokenizer.json --uitvoer nieuwe-modelrun.json
python scripts/vergelijk_ai_zoeken.py --modelantwoorden docs/ai-pilot/modelinterpretaties.json --e5-model PAD/e5.onnx --e5-tokenizer PAD/tokenizer.json --uitvoer herhaling.json
```

## Lokale installatie, standaard uit

Geen downloads bij starten of zoeken. Optioneel `pip install -r requirements-ai.txt`.
Zorg voor een lokale llama.cpp-server en handmatig gedownloade modelbestanden.
Gewichten/binaries zijn niet meegeleverd in de patch.

Geteste bronnen/revisies:

- Qwen: `https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF`,
  revisie `91cad51170dc346986eccefdc2dd33a9da36ead9`, bestand
  `qwen2.5-1.5b-instruct-q4_k_m.gguf` (Apache-2.0; circa 1,1 GB).
- E5: `https://huggingface.co/Xenova/multilingual-e5-small`, revisie
  `761b726dd34fb83930e26aab4e9ac3899aa1fa78`, `onnx/model_quantized.onnx`
  (118 MB), `tokenizer.json` (17 MB). Basismodel intfloat/multilingual-e5-small: MIT.
- llama.cpp geteste build `b11890`, commit `a07421535`; uitvoerbestanden en
  SHA-256 van gewichten staan bij de vastgelegde modelinterpretaties.

Bijvoorbeeld, uitsluitend voor een expliciet gestarte fictieve test:

```sh
llama-server -m PAD/qwen2.5-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8765 -c 4096 -t 4 --parallel 1 --log-disable
ZORGZOEKER_AI_AAN=1 ZORGZOEKER_AI_FICTIEVE_TESTS=1 ZORGZOEKER_AI_E5_MODEL=PAD/model_quantized.onnx ZORGZOEKER_AI_E5_TOKENIZER=PAD/tokenizer.json python -m zorgzoeker
```

`/ai` is zonder beide vlaggen uitgeschakeld (404); de normale applicatie werkt
zonder modelpakketten of modelserver. `ZORGZOEKER_AI_LOKALE_URL` accepteert alleen
een letterlijk loopback-IP via HTTP, geen cloudadres, credentials, redirects of
proxy. De modeladapter gebruikt schema-output en een time-out; bij een fout blijft
bron-/regelzoeken werken, met een zichtbaar fallbacklabel. Model/embedding-initialisatie
gebeurt pas bij gebruik van de pilot. ONNX-telemetrie wordt uitgeschakeld.

## Kosten, privacy en vervolgstappen

Geteste route: **€0 externe API-kosten per zoekopdracht**, exclusief bestaande
hardware, stroom en beheer. RAM en CPU zijn nodig; de gemeten CPU-latentie is
geen productiesnelheidsgarantie. Geen API-sleutel of nieuw abonnement nodig.

Een betaalde gestructureerde-interpretatie-API kan latentie/kwaliteit verbeteren,
maar is niet ingebouwd of geactiveerd. OpenAI/Mistral zijn mogelijke alternatieven;
prijs, modelkwaliteit, bewaartermijnen en EU-verwerking moeten dan afzonderlijk
worden beoordeeld. Rekenvoorbeeld, geen leveranciersprijs: bij 1.000 inputtokens,
200 outputtokens en tarieven $0,25/$2 per miljoen is dat $0,00065 per interpretatie
(10.000 vragen: $6,50), exclusief retries. Controleer vóór toestemming de actuele
prijzen: `https://developers.openai.com/api/docs/pricing` en `https://mistral.ai/pricing`.
Een cloudvariant zou een nieuwe goedgekeurde adapter en API-sleutel nodig hebben.
Nu worden geen vragen naar die diensten gestuurd.

Alleen fictieve testcasussen zijn toegestaan. POST-routes vermijden zorgvragen in
URL's; deze code logt of bewaart geen invoervragen. Modelserverlogging moet uit
blijven. De fictief-checkbox is geen anonimisering en beschermt niet tegen een
gebruiker die toch echte gegevens invoert. Er is geen productieautorisatie,
DPIA, verwerkersovereenkomst, toegangsscheiding of beveiligingsaudit toegevoegd.
Productiegebruik met echte casussen vereist expliciet een afzonderlijke privacy-
en beveiligingsbeoordeling. De twee pilotvlaggen zijn daarvoor geen toestemming.

De echte browserproef `mobielcheck/ai_pilot.py` controleert op 390 en 1280 pixels
interpretatie, expliciete bevestiging, correctie naar 18 jaar, bronbewijs en
zichtbare stops. De proef gebruikt een werkelijk lokaal model op de fictieve
dataset; 26 controles slagen. De bestaande 110 browsercontroles blijven slagen.
