"""4C leeswerkplek. Geen browserwrites of opgeslagen casussen."""
import json,csv,io
from urllib.parse import parse_qs
from fastapi import Request
from fastapi.responses import JSONResponse,Response
from zorgzoeker.beslissen import Beslisservice
from zorgzoeker.zoeken import Filters
from zorgzoeker.synoniemen import CONCEPT_LABEL


def registreer(app,templates,basis):
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
        return d
    def uitvoeren(d):
        if not service:raise ValueError('Brongegevens niet beschikbaar')
        q=d.get('q','');f=Filters.van(**{k:d.get(k) for k in ('gemeente','productcode','doelgroep','vestigingsplaats','gecontracteerd','op_datum')})
        correcties={}
        if d.get('aanpassing'):
            ages=d.get('leeftijden','')
            if isinstance(ages,str):ages=[float(x.strip().replace(',','.')) for x in ages.split(';') if x.strip()]
            correcties={'leeftijden':ages,'concepten':d.get('concepten',[]),'uitsluitingen':d.get('uitsluitingen',[])}
        result=service.zoek(q,f,**correcties)
        ids=d.get('ids',[])
        if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(i,str) or i not in service.ruw for i in ids):raise ValueError('Kies maximaal drie bekende aanbieders')
        d['ids']=list(dict.fromkeys(ids))
        return result,d['ids']
    def render(request,d,result,ids,vergelijk=False):
        if vergelijk:
            if not 2<=len(ids)<=3:raise ValueError('Kies twee of drie aanbieders')
            a,c=service.context(d.get('q',''),Filters.van(**{k:d.get(k) for k in ('gemeente','productcode','doelgroep','vestigingsplaats','gecontracteerd','op_datum')}),**({'leeftijden':result['context']['leeftijden'],'concepten':result['context']['concepten'],'uitsluitingen':result['context']['uitsluitingen']}))
            result={**result,'resultaten':[{'id':i,'naam':service.ruw[i]['naam']['waarde'],'beoordeling':service.beoordeel(i,analyse=a,context=c,filters=Filters.van(**{k:d.get(k) for k in ('gemeente','productcode','op_datum','vestigingsplaats')}))} for i in ids]}
        if not d:result={**result,'resultaten':[]}
        return templates.TemplateResponse(request,'pilot.html',{**basis(),'d':d,'r':result,'ids':ids,'labels':{**CONCEPT_LABEL,'medicatie':'medicatie'},'vergelijk':vergelijk,'buiten_selectie':[{'id':i,'naam':service.ruw[i]['naam']['waarde']} for i in ids if i not in {x['id'] for x in result['resultaten']}]})
    @app.get('/werkplek')
    def start(request:Request):
        if not service:return JSONResponse({'fout':'Brongegevens ontbreken'},status_code=503)
        return render(request,{},service.zoek(''),[])
    @app.post('/zoeken')
    async def zoeken(request:Request):
        try:
            d=await data(request);r,ids=uitvoeren(d);return render(request,d,r,ids)
        except (ValueError,TypeError,KeyError):return JSONResponse({'fout':'Controleer vraag, interpretatie, datum en selectie.'},status_code=400)
    @app.post('/vergelijken')
    async def vergelijken(request:Request):
        try:
            d=await data(request);r,ids=uitvoeren(d);return render(request,d,r,ids,True)
        except (ValueError,TypeError,KeyError):return JSONResponse({'fout':'Controleer context en kies twee of drie aanbieders.'},status_code=400)
    @app.post('/api/zoek')
    async def api(request:Request):
        try:
            d=await data(request);r,ids=uitvoeren(d);return JSONResponse(r)
        except (ValueError,TypeError,KeyError):return JSONResponse({'fout':'Ongeldige zoekcontext'},status_code=400)
    @app.post('/bronchecklijst')
    async def checklist(request:Request):
        try:
            d=await data(request);r,ids=uitvoeren(d)
            if not ids:raise ValueError('Selecteer aanbieders')
            # Uitsluitend openbare aanbiederinformatie; geen vraag, leeftijden, voorkeuren of casustekst exporteren.
            regels=[]
            for i in ids:
                f=Filters.van(**{k:d.get(k) for k in ('gemeente','productcode','doelgroep','vestigingsplaats','gecontracteerd','op_datum')})
                a,c=service.context(d.get('q',''),f,leeftijden=r['context']['leeftijden'],concepten=r['context']['concepten'],uitsluitingen=r['context']['uitsluitingen'])
                b=service.beoordeel(i,filters=f,analyse=a,context=c)
                regels.append({'aanbieder_id':i,'naam':service.ruw[i]['naam']['waarde'],'datasetversie':service.versie,
                    'gemeente':r['context']['gemeente'],'datum':r['context']['op_datum'],'contract':b['contract'],
                    'controlepunten':b['controlepunten'],'kwaliteit':b['kwaliteit']})
            return Response(json.dumps(regels,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="bronchecklijst.json"'})
        except (ValueError,TypeError,KeyError):return JSONResponse({'fout':'Controleer selectie'},status_code=400)
    @app.get('/kwaliteit')
    def kwaliteit(request:Request,export:bool=False):
        if not service:return JSONResponse({'fout':'Brongegevens ontbreken'},status_code=503)
        from zorgzoeker.kwaliteit import analyseer
        rapport=analyseer(service.document,beoordelingen=service.document.get('kwaliteitsbeoordelingen',[]))
        if export:
            out=io.StringIO();w=csv.writer(out,lineterminator='\n');w.writerow(['aanbieder','veld','prioriteit','reden','bron','laatste_controle','hercontrole','datasetversie'])
            for p in rapport['problemen']:
                b=rapport['aanbieders'][next(n for n,a in enumerate(rapport['aanbieders']) if a['id']==p['aanbieder_id'])]['velden'].get(p['veld'],{})
                row=[p['aanbieder_id'],p['veld'],p['prioriteit'],p['toelichting'],b.get('bron_url'),b.get('laatste_controle'),b.get('hercontrole_op'),service.versie]
                w.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in row])
            return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="controlepunten.csv"'})
        return templates.TemplateResponse(request,'kwaliteit.html',{**basis(),'rapport':rapport,'versie_data':service.versie})
