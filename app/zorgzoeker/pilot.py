"""4C leeswerkplek. Geen browserwrites of opgeslagen casussen."""
import json,csv,io
from datetime import date
from dataclasses import asdict
from urllib.parse import urlencode
from zorgzoeker.weergave import toon_veld
from urllib.parse import parse_qs
from fastapi import Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse,Response
from zorgzoeker.beslissen import Beslisservice
from zorgzoeker.zoeken import Filters
from zorgzoeker.synoniemen import CONCEPT_LABEL


def registreer(app,templates,basis):
    templates.env.filters['leeftijd_nl']=lambda n:format(float(n),'g').replace('.',',')
    service=Beslisservice(app.state.document,app.state.index) if app.state.index else None
    async def data(request):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>16384:raise ValueError('Verzoek te groot')
        if 'application/json' in request.headers.get('content-type',''):
            d=json.loads(body)
            if not isinstance(d,dict):raise ValueError('Object vereist')
        else:
            d={k:v if k in ('ids','concepten','uitsluitingen') else v[-1] for k,v in parse_qs(body.decode(),keep_blank_values=True).items()}
        q=d.get('q','')
        if not isinstance(q,str) or len(q)>500:raise ValueError('Vraag maximaal 500 tekens')
        for k in ('gemeente','productcode','doelgroep','vestigingsplaats','gecontracteerd','op_datum','zoekdoel','wachttijd_soort','wis_filter'):
            if k in d and not isinstance(d[k],str):raise ValueError('Ongeldige filterwaarde')
        if 'max_wachttijd' in d and (isinstance(d['max_wachttijd'],bool) or not isinstance(d['max_wachttijd'],(int,str))):raise ValueError('Ongeldige wachttijdgrens')
        return d
    def uitvoeren(d, geselecteerd=False):
        if not service:raise ValueError('Brongegevens niet beschikbaar')
        q=d.get('q','')
        if d.get('wis_filter') in ('gemeente','productcode','doelgroep','vestigingsplaats','gecontracteerd','op_datum'):d.pop(d['wis_filter'],None)
        d.pop('wis_filter',None)
        f=Filters.van(**{k:d.get(k) for k in ('gemeente','productcode','doelgroep','vestigingsplaats','gecontracteerd','op_datum')})
        correcties={'zoekdoel':d.get('zoekdoel') or 'kiezen'}
        if 'max_wachttijd' in d:
            correcties['max_wachttijd']=int(d['max_wachttijd']) if str(d['max_wachttijd']).strip() else ''
        if d.get('wachttijd_soort'):correcties['wachttijd_soort']=d['wachttijd_soort']
        if d.get('aanpassing'):
            ages=d.get('leeftijden','')
            if isinstance(ages,str):ages=[float(x.strip().replace(',','.')) for x in ages.split(';') if x.strip()]
            correcties.update({'leeftijden':ages,'concepten':d.get('concepten',[]),'uitsluitingen':d.get('uitsluitingen',[])})
        ids=d.get('ids',[])
        if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(i,str) or i not in service.ruw for i in ids):raise ValueError('Kies maximaal drie bekende aanbieders')
        d['ids']=list(dict.fromkeys(ids))
        result = service.selecteer(q,f,d['ids'],**correcties) if geselecteerd else service.zoek(q,f,**correcties)
        return result,d['ids']
    def render(request,d,result,ids,vergelijk=False,detail=False):
        if vergelijk:
            if not 2<=len(ids)<=3:raise ValueError('Kies twee of drie aanbieders')
        from zorgzoeker.zoeken import _concepten_in
        for x in result['resultaten']+result.get('kandidaten',[])+result.get('onderbouwd',[])+result.get('uitgesloten',[]):
            wensen=set(x['beoordeling']['context']['concepten'])
            x['relevante_kenmerken']=[v for v in (x['beoordeling']['inhoud']['expertise'] or []) if isinstance(v,str) and wensen.intersection(_concepten_in(v))][:3]
        if not d:result={**result,'resultaten':[]}
        return templates.TemplateResponse(request,'pilot.html',{**basis(),'d':d,'r':result,'ids':ids,'labels':{**CONCEPT_LABEL,'medicatie':'medicatie'},'vergelijk':vergelijk,'detail':detail,'profielen':service.ruw,'toon_veld':toon_veld,'opties':service.index.filteropties(),'meerkeuze':result.get('keuze_nodig',False),'buiten_selectie':[{'id':i,'naam':service.ruw[i]['naam']['waarde']} for i in ids if detail or i not in {x['id'] for x in result['resultaten']+result.get('kandidaten',[])+result.get('onderbouwd',[])}]})
    def foutantwoord(request,d,melding):
        if not service:return JSONResponse({'fout':'Brongegevens niet beschikbaar'},status_code=503)
        if 'application/json' in request.headers.get('content-type',''):
            return JSONResponse({'fout':melding},status_code=400)
        _,c=service.context('',Filters())
        r={'context':asdict(c),'resultaten':[],'afgevallen':[],'meldingen':[]}
        rawids=d.get('ids',[])
        ids=list(dict.fromkeys(i for i in rawids if isinstance(i,str) and i in service.ruw))[:3] if isinstance(rawids,list) else []
        return templates.TemplateResponse(request,'pilot.html',{**basis(),'fout':melding,'d':d,'r':r,'ids':ids,
            'labels':{**CONCEPT_LABEL,'medicatie':'medicatie'},'vergelijk':False,'profielen':service.ruw,
            'toon_veld':toon_veld,'opties':service.index.filteropties(),'buiten_selectie':[{'id':i,'naam':service.ruw[i]['naam']['waarde']} for i in ids]},status_code=400)
    @app.get('/werkplek')
    def start(request:Request):
        if not service:return JSONResponse({'fout':'Brongegevens ontbreken'},status_code=503)
        a,c=service.context('',Filters())
        from dataclasses import asdict
        return render(request,{}, {'context':asdict(c),'resultaten':[], 'afgevallen':[], 'meldingen':[]},[])
    @app.post('/zoeken')
    async def zoeken(request:Request):
        d={}
        try:
            d=await data(request);r,ids=await run_in_threadpool(uitvoeren,d);return await run_in_threadpool(render,request,d,r,ids)
        except (ValueError,TypeError,KeyError):return foutantwoord(request,d,'Controleer vraag, interpretatie, datum en selectie.')
    @app.post('/vergelijken')
    async def vergelijken(request:Request):
        d={}
        try:
            d=await data(request);r,ids=await run_in_threadpool(uitvoeren,d,True);return await run_in_threadpool(render,request,d,r,ids,True)
        except (ValueError,TypeError,KeyError):return foutantwoord(request,d,'Controleer context en kies twee of drie aanbieders.')
    @app.post('/aanbieder')
    async def aanbieder(request:Request):
        d={}
        try:
            d=await data(request)
            id=d.pop('aanbieder_id','')
            if not service or not isinstance(id,str) or id not in service.ruw:raise ValueError('Onbekende aanbieder')
            gekozen=d.get('ids',[])
            if not isinstance(gekozen,list) or len(gekozen)>3 or any(not isinstance(i,str) or i not in service.ruw for i in gekozen):raise ValueError('Ongeldige selectie')
            r,_=await run_in_threadpool(uitvoeren,{**d,'ids':[id]},True)
            return await run_in_threadpool(render,request,d,r,gekozen,False,True)
        except (ValueError,TypeError,KeyError):return foutantwoord(request,d,'Controleer de aanbieder en zoekcontext.')
    @app.post('/api/zoek')
    async def api(request:Request):
        try:
            d=await data(request);r,ids=await run_in_threadpool(uitvoeren,d)
            r['schema_versie']='5G'
            r['groepen']={k:r.get(k,[]) for k in ('onderbouwd','kandidaten','uitgesloten')}
            r['aantallen']={k:len(v) for k,v in r['groepen'].items()}
            r['resultaten_betekenis']='compatibele gefilterde indexlijst; resultaatstatus bepaalt beoordeling'
            return JSONResponse(r)
        except (ValueError,TypeError,KeyError):return JSONResponse({'fout':'Ongeldige zoekcontext'},status_code=400)
    @app.post('/bronchecklijst')
    async def checklist(request:Request):
        try:
            d=await data(request);r,ids=await run_in_threadpool(uitvoeren,d,True)
            if not ids:raise ValueError('Selecteer aanbieders')
            # Uitsluitend openbare aanbiederinformatie; geen vraag, leeftijden, voorkeuren of casustekst exporteren.
            regels=[]
            for i in ids:
                b=next(x['beoordeling'] for x in r['resultaten'] if x['id']==i)
                regels.append({'aanbieder_id':i,'naam':service.ruw[i]['naam']['waarde'],'datasetversie':service.versie,
                    'gemeente':r['context']['gemeente'],'datum':r['context']['op_datum'],'contract':b['contract'],
                    'controlepunten':[k+': '+v['controle'] for k,v in b['kwaliteit'].items() if v['status']!='geverifieerd'],'kwaliteit':b['kwaliteit']})
            if request.query_params.get('weergave')=='print':
                return templates.TemplateResponse(request,'bronchecklijst.html',{**basis(),'regels':regels})
            return Response(json.dumps(regels,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="bronchecklijst.json"'})
        except (ValueError,TypeError,KeyError):return JSONResponse({'fout':'Controleer selectie'},status_code=400)
    rapportcache={}
    @app.get('/kwaliteit')
    def kwaliteit(request:Request,export:bool=False,pagina:int=1,q:str='',status:str='',veld:str='',probleem:str=''):
        if not service:return JSONResponse({'fout':'Brongegevens ontbreken'},status_code=503)
        from zorgzoeker.kwaliteit import analyseer
        vandaag=date.today().isoformat()
        if rapportcache.get('datum')!=vandaag:
            rapportcache.clear();rapportcache.update(datum=vandaag,rapport=analyseer(service.document,beoordelingen=service.document.get('kwaliteitsbeoordelingen',[])))
        volledig=rapportcache['rapport'];providers=[];problemen=[]
        for a in volledig['aanbieders']:
            ps=[x for x in volledig['problemen'] if x['aanbieder_id']==a['id'] and (not veld or x['veld']==veld) and (not probleem or x['code']==probleem)]
            if q and q.casefold() not in (a['naam']+' '+a['id']).casefold():continue
            if status and not any(v['status']==status for k,v in a['velden'].items() if not veld or k==veld):continue
            if (veld or probleem) and not ps:continue
            providers.append({**a,'problemen':ps,'prioriteit':min((x['prioriteit'] for x in ps),default=9)})
            problemen.extend(ps)
        providers.sort(key=lambda a:(a['prioriteit'],-sum(x['prioriteit']==1 for x in a['problemen']),a['naam'].casefold()))
        rapport={**volledig,'aanbieders':providers,'problemen':problemen}

        if export:
            out=io.StringIO();w=csv.writer(out,lineterminator='\n');w.writerow(['aanbieder','veld','prioriteit','reden','bron','laatste_controle','hercontrole','datasetversie'])
            for p in rapport['problemen']:
                b=rapport['aanbieders'][next(n for n,a in enumerate(rapport['aanbieders']) if a['id']==p['aanbieder_id'])]['velden'].get(p['veld'],{})
                row=[p['aanbieder_id'],p['veld'],p['prioriteit'],p['toelichting'],b.get('bron_url'),b.get('laatste_controle'),b.get('hercontrole_op'),service.versie]
                w.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in row])
            return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="controlepunten.csv"'})
        pages=max(1,(len(providers)+24)//25);pagina=max(1,min(pagina,pages))
        filters={'q':q,'status':status,'veld':veld,'probleem':probleem}
        rapport={**rapport,'aanbieders':providers[(pagina-1)*25:pagina*25]}
        return templates.TemplateResponse(request,'kwaliteit.html',{**basis(),'rapport':rapport,'versie_data':service.versie,
            'filters':filters,'pagina':pagina,'pages':pages,'totaal':len(providers),
            'volgende':'/kwaliteit?'+urlencode({**filters,'pagina':pagina+1}),
            'vorige_url':('/kwaliteit?'+urlencode({**filters,'pagina':pagina-1})) if pagina>1 else None,
            'volgende_url':('/kwaliteit?'+urlencode({**filters,'pagina':pagina+1})) if pagina<pages else None,
            'profielen':service.ruw,'toon_veld':toon_veld,
            'export_url':'/kwaliteit?'+urlencode({**filters,'export':'true'})})
