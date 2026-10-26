"""Lokale webinterface. Zoekvragen worden niet gelogd."""

from __future__ import annotations

from pathlib import Path
from datetime import date
from urllib.parse import quote

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from zorgzoeker import __versie__
from zorgzoeker.pilot import registreer as registreer_pilot
from zorgzoeker.ai_web import registreer as registreer_ai, ingeschakeld as ai_ingeschakeld
from zorgzoeker.kaarten import samenvatting
from zorgzoeker.config import data_pad
from zorgzoeker.laden import laad_document
from zorgzoeker.valideer import valideer_document
from zorgzoeker.weergave import toon_veld, vergelijk_rijen, website_url
from zorgzoeker.zoeken import Filters, Index, Treffer

PAKKET = Path(__file__).resolve().parent
SJABLONEN = Jinja2Templates(directory=str(PAKKET / "sjablonen"))
SJABLONEN.env.filters["urlencode"] = lambda waarde: quote(str(waarde), safe="")

VOORBEELDEN = (
    "jongen 14 met autisme en angst in Groesbeek, ambulant",
    "gezinshuis voor meisje van 10 regio Nijmegen",
    "dagbesteding zorgboerderij Wijchen",
)

MAX_VRAAG = 500


def _fictief(pad: Path, document: dict) -> bool:
    if "fixture" in pad.name:
        return True
    namen = []
    for aanbieder in document.get("aanbieders") or []:
        naam = (aanbieder.get("naam") or {}).get("waarde")
        namen.append(str(naam or ""))
    return bool(namen) and all(naam.startswith("FICTIEF") for naam in namen)


def maak_app(pad: Path | None = None) -> FastAPI:
    application = FastAPI(title="Zorgzoeker", docs_url=None, redoc_url=None)
    application.mount("/statisch", StaticFiles(directory=str(PAKKET / "statisch")), name="statisch")

    bron_pad = Path(pad) if pad is not None else data_pad()
    application.state.pad = bron_pad
    application.state.versie = __versie__
    application.state.fout = None
    application.state.validatiefouten = []
    application.state.document = None
    application.state.index = None
    try:
        document = laad_document(bron_pad)
        import os,json
        from zorgzoeker.bewijs import hashwaarde,Kwaliteitslezing
        if os.getenv('ZORGZOEKER_KWALITEIT_PAD'):
            pakket=json.loads(Path(os.environ['ZORGZOEKER_KWALITEIT_PAD']).read_text())
            if pakket['dataset_hash']!=hashwaarde(document):raise ValueError('Kwaliteitspakket hoort bij andere dataset')
            document={**document,'kwaliteitsbeoordelingen':pakket['beoordelingen']}
        Kwaliteitslezing(document)
        application.state.document = document
        application.state.validatiefouten = valideer_document(document)
        if application.state.validatiefouten:
            application.state.fout = "Het aanbiedersbestand bevat ongeldige gegevens. Zoeken is geblokkeerd totdat de brongegevens zijn hersteld."
            raise ValueError("Ongeldige brongegevens")
        application.state.index = Index(document)
        application.state.fictief = _fictief(bron_pad, document)
    except (OSError, ValueError, KeyError, TypeError) as fout:
        application.state.fout = application.state.fout or f"Het aanbiedersbestand kan niet worden gelezen ({bron_pad.name})."
        application.state.fictief = "fixture" in bron_pad.name
        # Bewust geen volledige fouttekst: die kan een pad of een zoekvraag bevatten.
        _ = fout

    def index() -> Index:
        if application.state.index is None:
            raise RuntimeError("geen index")
        return application.state.index

    def basis() -> dict:
        document = application.state.document or {}
        meta = document.get("meta") or {}
        return {
            "ai_ingeschakeld": ai_ingeschakeld(),
            "versie": application.state.versie,
            "fictief": application.state.fictief,
            "bestand": application.state.pad.name,
            "meta": meta,
            "validatiefouten": application.state.validatiefouten,
            "aantal_totaal": len(document.get("aanbieders") or []),
            "fout": application.state.fout,
        }

    def opties() -> dict:
        if application.state.index is None:
            return {"plaatsen": [], "doelgroepen": [], "productcodes": [], "contracten": []}
        return index().filteropties()

    @application.get("/gezondheid")
    def gezondheid() -> dict:
        return {
            "status": "ok" if application.state.fout is None else "fout",
            "aanbieders": basis()["aantal_totaal"],
            "bestand": application.state.pad.name,
        }

    @application.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        q: str = "",
        gecontracteerd: str = "",
        productcode: str = "",
        doelgroep: str = "",
        gemeente: str = "",
        vestigingsplaats: str = "",
        op_datum: str = "",
        alles: str = "",
    ) -> HTMLResponse:
        omgeving = basis()
        if application.state.fout:
            return SJABLONEN.TemplateResponse(
                request,
                "fout.html",
                {**omgeving, "melding": application.state.fout},
                status_code=500,
            )
        if len(q) > MAX_VRAAG:
            return SJABLONEN.TemplateResponse(
                request,
                "fout.html",
                {
                    **omgeving,
                    "melding": "De zoekvraag is te lang. Formuleer een korte zorgvraag zonder persoonsgegevens.",
                },
                status_code=400,
            )
        if op_datum:
            try:
                date.fromisoformat(op_datum)
            except ValueError:
                return JSONResponse({"fout": "Contractdatum moet een geldige datum YYYY-MM-DD zijn."}, status_code=400)
        filters = Filters.van(
            gecontracteerd=gecontracteerd,
            productcode=productcode,
            doelgroep=doelgroep,
            gemeente=gemeente,
            vestigingsplaats=vestigingsplaats,
            op_datum=op_datum,
        )
        gezocht = bool(q.strip() or filters.actief() or alles == "1")
        treffers = index().zoek("" if alles == "1" and not q.strip() else q, filters) if gezocht else []
        return SJABLONEN.TemplateResponse(
            request,
            "index.html",
            {
                **omgeving,
                "q": q,
                "filters": filters,
                "opties": opties(),
                "gezocht": gezocht,
                "meldingen": index().meldingen(q, filters),
                "kaarten": [_kaart(treffer, q) for treffer in treffers],
                "alleen_gedeeltelijk": bool(treffers) and all(t.ontbrekende_expertise for t in treffers),
                "voorbeelden": VOORBEELDEN,
            },
        )

    @application.get("/vergelijken", response_class=HTMLResponse)
    def vergelijken(request: Request, ids: list[str] = Query(default=[]), q: str = "",
                    gemeente: str = "", productcode: str = "", gecontracteerd: str = "",
                    doelgroep: str = "", vestigingsplaats: str = "", op_datum: str = "") -> HTMLResponse:
        omgeving = basis()
        if len(q) > MAX_VRAAG:
            return JSONResponse({"fout": "Zoekvraag is te lang."}, status_code=400)
        if op_datum:
            try:
                date.fromisoformat(op_datum)
            except ValueError:
                return JSONResponse({"fout": "Contractdatum moet een geldige datum YYYY-MM-DD zijn."}, status_code=400)
        filters = Filters.van(gemeente=gemeente, productcode=productcode, gecontracteerd=gecontracteerd,
                              doelgroep=doelgroep, vestigingsplaats=vestigingsplaats, op_datum=op_datum)
        if application.state.fout:
            return SJABLONEN.TemplateResponse(
                request,
                "fout.html",
                {**omgeving, "melding": application.state.fout},
                status_code=500,
            )
        gekozen_ids = []
        for aanbieder_id in ids:
            if aanbieder_id and aanbieder_id not in gekozen_ids:
                gekozen_ids.append(aanbieder_id)
        if not 2 <= len(gekozen_ids) <= 3:
            return SJABLONEN.TemplateResponse(
                request,
                "vergelijken.html",
                {**omgeving, "melding": "Kies twee of drie aanbieders om ze naast elkaar te zetten.", "kolommen": [], "rijen": []},
            )
        kolommen = []
        ontbreekt = []
        for aanbieder_id in gekozen_ids:
            ruw = index().op_id(aanbieder_id)
            if ruw is None:
                ontbreekt.append(aanbieder_id)
            else:
                kolommen.append(ruw)
        if ontbreekt or len(kolommen) < 2:
            return SJABLONEN.TemplateResponse(
                request,
                "vergelijken.html",
                {
                    **omgeving,
                    "melding": "Een of meer gekozen aanbieders zitten niet in deze dataset.",
                    "kolommen": [],
                    "rijen": [],
                },
            )
        return SJABLONEN.TemplateResponse(
            request,
            "vergelijken.html",
            {
                **omgeving,
                "melding": None,
                "kolommen": [
                    {"id": item["id"], "naam": (item.get("naam") or {}).get("waarde"), "website": website_url(item)}
                    for item in kolommen
                ],
                "rijen": vergelijk_rijen(kolommen, [index().contracttoets_voor(item["id"], q, filters) for item in kolommen]),
            },
        )

    @application.get("/api/zoek")
    def api_zoek(
        q: str = "",
        gecontracteerd: str = "",
        productcode: str = "",
        doelgroep: str = "",
        gemeente: str = "",
        vestigingsplaats: str = "",
        op_datum: str = "",
    ) -> JSONResponse:
        if application.state.fout:
            return JSONResponse({"fout": application.state.fout, "validatiefouten": application.state.validatiefouten}, status_code=500)
        if len(q) > MAX_VRAAG:
            return JSONResponse({"fout": "Zoekvraag is te lang."}, status_code=400)
        if op_datum:
            try:
                date.fromisoformat(op_datum)
            except ValueError:
                return JSONResponse({"fout": "Contractdatum moet een geldige datum YYYY-MM-DD zijn."}, status_code=400)
        filters = Filters.van(
            gecontracteerd=gecontracteerd,
            productcode=productcode,
            doelgroep=doelgroep,
            gemeente=gemeente,
            vestigingsplaats=vestigingsplaats,
            op_datum=op_datum,
        )
        treffers = index().zoek(q, filters)
        return JSONResponse(
            {
                "aantal": len(treffers),
                "waarschuwingen": index().meldingen(q, filters),
                "resultaten": [
                    {
                        "id": treffer.id,
                        "naam": treffer.naam,
                        "website": website_url(treffer.aanbieder),
                        "rang": treffer.rang,
                        "reden": treffer.reden,
                        "contracttoets": treffer.contracttoets,
                        "ontbrekende_expertise": treffer.ontbrekende_expertise,
                        "volledige_match": not treffer.ontbrekende_expertise,
                        "wachttijd": toon_veld("wachttijd", treffer.aanbieder.get("wachttijd")),
                        "beschikbaarheid": toon_veld(
                            "beschikbaarheid", treffer.aanbieder.get("beschikbaarheid")
                        ),
                    }
                    for treffer in treffers
                ],
            }
        )

    registreer_ai(application, SJABLONEN, basis)
    registreer_pilot(application, SJABLONEN, basis)
    @application.middleware('http')
    async def privacy_headers(request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    return application


def _kaart(treffer: Treffer, vraag: str = "") -> dict:
    return {**samenvatting(treffer, vraag), "id": treffer.id, "rang": treffer.rang,
            "naam": treffer.naam, "website": website_url(treffer.aanbieder),
            "reden": treffer.reden, "contracttoets": treffer.contracttoets}


app = maak_app()
