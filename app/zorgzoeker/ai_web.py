"""Alleen optionele lokale fictieve pilot. Geen productie- of cloudroute."""
import asyncio,json,os
from threading import Lock
from urllib.parse import parse_qs
from fastapi import Request
from fastapi.responses import JSONResponse
from zorgzoeker.ai_zoeken import HybrideZoeker,LABELS,pas_interpretatie_aan
from zorgzoeker.ai_modellen import LokaalTaalmodel,E5Embeddings
from zorgzoeker.zoeken import Filters


def ingeschakeld():
    return os.getenv('ZORGZOEKER_AI_AAN')=='1' and os.getenv('ZORGZOEKER_AI_FICTIEVE_TESTS')=='1'


def registreer(application,sjablonen,basis):
    lock=Lock();service=None
    def zoeker():
        nonlocal service
        with lock:
            if service is None:
                model=None;embedding=None
                try:model=LokaalTaalmodel(os.getenv('ZORGZOEKER_AI_LOKALE_URL','http://127.0.0.1:8765'),timeout=20)
                except ValueError:pass
                mp=os.getenv('ZORGZOEKER_AI_E5_MODEL');tp=os.getenv('ZORGZOEKER_AI_E5_TOKENIZER')
                if mp and tp:
                    try:embedding=E5Embeddings(mp,tp)
                    except (ImportError,OSError,ValueError,RuntimeError):pass
                service=HybrideZoeker(application.state.document,model,embedding)
        return service
    async def inhoud(request):
        data=bytearray()
        async for deel in request.stream():
            data.extend(deel)
            if len(data)>8192:raise ValueError('Verzoek te groot.')
        if 'application/json' in request.headers.get('content-type',''):
            value=json.loads(data)
            if not isinstance(value,dict):raise ValueError('JSON-object vereist.')
            return value
        resultaat={k:v if k in {'concepten','uitsluitingen'} else v[-1] for k,v in parse_qs(data.decode(),keep_blank_values=True).items()}
        resultaat.setdefault('concepten',[]);resultaat.setdefault('uitsluitingen',[])
        return resultaat
    def controle(data):
        if data.get('fictief') not in (True,'1','on'):raise ValueError('Bevestig dat dit uitsluitend een fictieve casus is.')
        q=data.get('q')
        if not isinstance(q,str) or not q.strip() or len(q)>500:raise ValueError('Gebruik een fictieve vraag van maximaal 500 tekens.')
        return q
    async def verwerken(request,api=False,alleen_interpretatie=False):
        if not ingeschakeld():return JSONResponse({'fout':'AI-pilot is uitgeschakeld.'},status_code=404)
        if application.state.index is None:return JSONResponse({'fout':'Brondata niet beschikbaar.'},status_code=503)
        data={};r=None;resultaat=None;fout=None
        try:
            data=await inhoud(request);q=controle(data)
            service=await asyncio.to_thread(zoeker)
            actie=data.get('actie','zoek' if request.url.path.endswith('/zoek') else 'interpreteer')
            if actie=='zoek' and not alleen_interpretatie:
                if data.get('bevestigd') not in (True,'1','on'):raise ValueError('Bevestig de interpretatie.')
                r=data.get('interpretatie')
                if isinstance(r,str):r=json.loads(r)
                if not isinstance(r,dict) or r.get('backend') not in {'lokaal_taalmodel','regel_fallback','zoekregels'}:raise ValueError('Ongeldige interpretatie.')
                leeftijden=data.get('leeftijden')
                if isinstance(leeftijden,str):leeftijden=[float(n.strip().replace(',','.')) for n in leeftijden.split(';') if n.strip()]
                r=pas_interpretatie_aan(r,leeftijden=leeftijden,concepten=data.get('concepten'),uitsluitingen=data.get('uitsluitingen'))
                filters=Filters.van(**{k:data.get(k) for k in ('gemeente','productcode','gecontracteerd','doelgroep','vestigingsplaats','op_datum')})
                if filters.op_datum:
                    from datetime import date
                    date.fromisoformat(filters.op_datum)
                resultaat=await asyncio.to_thread(service.zoek,q,r,filters)
            else:r=await asyncio.to_thread(service.interpreteer,q)
        except (ValueError,TypeError,KeyError):fout='Controleer de fictieve vraag, interpretatie, leeftijden en filters.'
        if api:
            return JSONResponse({'interpretatie':r,'zoekresultaat':resultaat,'fout':fout},status_code=400 if fout else 200)
        return sjablonen.TemplateResponse(request,'ai.html',{**basis(),'q':data.get('q',''),'interpretatie':r,'ai_resultaat':resultaat,'ai_fout':fout,'conceptlabels':LABELS},status_code=400 if fout else 200)
    @application.get('/ai')
    def pagina(request:Request):
        if not ingeschakeld():return JSONResponse({'fout':'AI-pilot is uitgeschakeld.'},status_code=404)
        return sjablonen.TemplateResponse(request,'ai.html',{**basis(),'q':'','interpretatie':None,'ai_resultaat':None,'ai_fout':None,'conceptlabels':LABELS})
    @application.post('/ai')
    async def post(request:Request):return await verwerken(request)
    @application.post('/api/ai/interpreteer')
    async def interpreteer(request:Request):return await verwerken(request,api=True,alleen_interpretatie=True)
    @application.post('/api/ai/zoek')
    async def zoek(request:Request):return await verwerken(request,api=True)
