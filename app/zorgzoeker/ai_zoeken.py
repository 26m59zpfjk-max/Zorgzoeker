"""Experimentele hybride zoekfunctie. Bestaande Index.zoek blijft ongewijzigd.

LLM: voorstel interpretatie; embeddings: rangschikking; bronbewijs en harde regels:
beslissend. Geen diagnose, providerfeiten, contracten of capaciteit uit een model.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
import math,re,time
from urllib.parse import urlsplit

from zorgzoeker.beschikbaarheid import relevante_regels,actueel,stop_actief
from zorgzoeker.contracten import algemene_stop,code_sleutel
from zorgzoeker.kwaliteit import hashwaarde,valideer_beoordeling
from zorgzoeker.kwaliteitsbronnen import openbare_url
from zorgzoeker.synoniemen import CONCEPT_LABEL
from zorgzoeker.zoeken import Index,Filters,KLINISCH,analyseer_vraag,leeftijd_oordeel,leeftijdsgrenzen,_concepten_in,normaliseer,_past_wachttijd,_gender

LABELS={**CONCEPT_LABEL,'medicatie':'medicatie'}


def basis_interpretatie(q,index):
    a=analyseer_vraag(q,index.plaatstabel,index.bekende_codes)
    return {'leeftijden':a.leeftijden,'signalen':[{'concept':c,'citaat':q,'status':'genoemd','bron':'zoekregels'} for c in a.concepten],
            'uitsluitingen':[{'concept':c,'citaat':q,'bron':'zoekregels'} for c in a.uitgesloten],
            'waarschuwingen':[],'backend':'zoekregels','bevestigd':False,'aangepast':False}


def valideer_modelantwoord(q,antwoord,index):
    if not isinstance(antwoord,dict) or set(antwoord)!={'signalen','uitsluitingen'}:raise ValueError('Onjuist modelschema.')
    r=basis_interpretatie(q,index);r['backend']='lokaal_taalmodel'
    analyse=analyseer_vraag(q,index.plaatstabel,index.bekende_codes)
    for key in ('signalen','uitsluitingen'):
        if not isinstance(antwoord[key],list) or len(antwoord[key])>8:raise ValueError('Onjuiste signaallijst.')
        for item in antwoord[key]:
            if not isinstance(item,dict) or set(item)!={'concept','citaat'}:raise ValueError('Onjuist signaal.')
            c=item['concept'];citaat=item['citaat']
            if not isinstance(c,str) or c not in LABELS or not isinstance(citaat,str) or not citaat.strip():raise ValueError('Ongeldig modelcitaat.')
            begin=q.casefold().find(citaat.casefold())
            if begin<0:raise ValueError('Modelcitaat ontbreekt in de originele vraag.')
            citaat=q[begin:begin+len(citaat)]
            if key=='uitsluitingen':
                if c not in analyse.uitgesloten:continue  # Negaties blijven door de oorspronkelijke regels begrensd.
            elif c not in analyse.ontkend and c not in analyse.uitgesloten and c not in {s['concept'] for s in r[key]}:
                r[key].append({'concept':c,'citaat':citaat,'status':'mogelijk','bron':'modelinterpretatie'})
    # 'Vermoedelijke ADHD' wordt nooit een vastgestelde diagnose in de UI.
    for s in r['signalen']:
        if re.search(r'\b(?:vermoed\w*|mogelijk\w*)\s+(?:'+re.escape(s['concept'])+r')\b',q,re.I):s['status']='mogelijk'
    r['waarschuwingen'].append('Interpretatievoorstel, geen diagnose. Controleer en bevestig vóór zoeken.')
    return r


def pas_interpretatie_aan(r,*,leeftijden=None,concepten=None,uitsluitingen=None):
    if not isinstance(r,dict) or not {'leeftijden','signalen','uitsluitingen','backend'}<=r.keys():raise ValueError('Onvolledige interpretatie.')
    for key in ('signalen','uitsluitingen'):
        if not isinstance(r[key],list) or len(r[key])>len(LABELS) or any(not isinstance(s,dict) or not isinstance(s.get('concept'),str) or s['concept'] not in LABELS for s in r[key]):raise ValueError('Ongeldige interpretatiesignalen.')
    nieuw=deepcopy(r)
    nieuw['aangepast']=leeftijden is not None or concepten is not None or uitsluitingen is not None
    if leeftijden is None:leeftijden=r['leeftijden']
    if leeftijden is not None:
        if not isinstance(leeftijden,list) or len(leeftijden)>10 or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=120 for n in leeftijden):raise ValueError('Ongeldige leeftijden.')
        nieuw['leeftijden']=leeftijden
    for key,waarden in [('signalen',concepten),('uitsluitingen',uitsluitingen)]:
        if waarden is not None:
            if not isinstance(waarden,list) or len(waarden)>len(LABELS) or any(not isinstance(c,str) or c not in LABELS for c in waarden):raise ValueError('Onbekend zoekbegrip.')
            nieuw[key]=[{'concept':c,'citaat':'Door gebruiker aangepast','status':'zoekvoorkeur','bron':'gebruikersaanpassing'} for c in dict.fromkeys(waarden)]
    if {s['concept'] for s in nieuw['signalen']}&{s['concept'] for s in nieuw['uitsluitingen']}:raise ValueError('Een begrip kan niet tegelijk gewenst en uitgesloten zijn.')
    nieuw['bevestigd']=True
    return nieuw


def _onderbouwd(document,a,k,v):
    if not isinstance(v,dict) or not openbare_url(v.get('bron_url')) or not v.get('opgehaald_op'):return False
    reviews=document.get('kwaliteitsbeoordelingen',[])
    geldig=[b for b in reviews if b.get('aanbieder_id')==a['id'] and b.get('veld')==k and b.get('waarde_hash')==hashwaarde(v) and not valideer_beoordeling(b)]
    if reviews and any(b.get('aanbieder_id')==a['id'] and b.get('veld')==k for b in reviews) and not geldig:return False
    if geldig:
        b=max(geldig,key=lambda b:b['gecontroleerd_op'])
        return b['status']=='geverifieerd' and b['hercontrole_op']>date.today().isoformat()
    # Alleen bestaande expliciet geverifieerde eigen-brongegevens, nooit de 114 naamafleidingen.
    website=a.get('website') or {}
    return (v.get('label')=='geverifieerd' and website.get('label')=='geverifieerd'
            and openbare_url(website.get('waarde')) and urlsplit(v['bron_url']).hostname.removeprefix('www.')==urlsplit(website['waarde']).hostname.removeprefix('www.'))


def diensten(document):
    resultaat=[]
    for a in document['aanbieders']:
        expliciet=a.get('diensten')
        eenheden=expliciet if isinstance(expliciet,list) and expliciet else [{'id':'profiel:'+a['id'],'naam':'Aanbiedersprofiel (dienstscope onbekend)'}]
        for d in eenheden:
            v=d.get('expertise') if expliciet else a.get('expertise')
            if not _onderbouwd(document,a,'expertise',v) or not isinstance(v.get('waarde'),list) or not v['waarde']:continue
            if not isinstance(d.get('id'),str) or not isinstance(d.get('naam'),str):continue
            ruw={**a,**{k:d[k] for k in ('expertise','doelgroepen','type_aanbod','productcodes','wachttijd','beschikbaarheid','vestigingen','toelatingsregels','uitsluitingscriteria','toelatingsvoorwaarden') if k in d}}
            resultaat.append({'id':a['id']+'/'+d['id'],'aanbieder_id':a['id'],'dienst':d['naam'],'naam':a['naam']['waarde'],
                'ruw':ruw,'profiel':a,'dienstscope_bevestigd':bool(expliciet),'expertise':v['waarde'],
                'bewijs':{'veld':'expertise','bron_url':v['bron_url'],'citaat':'; '.join(v['waarde']),'opgehaald_op':v['opgehaald_op'],
                         'status':'bestaand geverifieerd bronveld; zie kwaliteitsrapport voor hercontrole'},
                'tekst':d['naam']+'; '+'; '.join(v['waarde'])})
    return resultaat


def toelating_past(document,d,analyse,interpretatie):
    """Alleen expliciet gestructureerde, onderbouwde uitsluitingen automatisch toepassen.

    Vrije voorwaarden blijven zichtbaar en vereisen beoordeling. Geen AI-parser
    die zelf toelatingsregels uit een website afleidt.
    """
    regels=d['ruw'].get('toelatingsregels',[])
    for regel in regels if isinstance(regels,list) else []:
        if not isinstance(regel,dict) or not _onderbouwd(document,d['profiel'],'toelatingsregels',regel):continue
        soort=regel.get('soort');waarde=regel.get('waarde')
        if soort=='geslacht' and waarde in {'meisjes','jongens'} and analyse.gender in {'meisjes','jongens'} and analyse.gender!=waarde:return False
        if soort=='uitsluit_concept' and isinstance(waarde,str) and waarde in LABELS and waarde in (set(analyse.concepten)|{s['concept'] for s in interpretatie['signalen']}):return False
    return True


class HybrideZoeker:
    def __init__(self,document,taalmodel=None,embeddings=None):
        self.document=document;self.index=Index(document);self.taalmodel=taalmodel;self.embeddings=embeddings
        self.diensten=diensten(document)
        self.vectors=None
        if embeddings and self.diensten:
            self.vectors=embeddings.encode([d['tekst'] for d in self.diensten])
    def interpreteer(self,q):
        if not isinstance(q,str) or not q.strip() or len(q)>500:raise ValueError('Formuleer een fictieve vraag van maximaal 500 tekens.')
        r=basis_interpretatie(q,self.index)
        if not self.taalmodel:
            r['backend']='regel_fallback';r['waarschuwingen'].append('Lokaal taalmodel niet beschikbaar; bestaande zoekregels gebruikt.');return r
        try:return valideer_modelantwoord(q,self.taalmodel.interpreteer(q,list(LABELS)),self.index)
        except (OSError,ValueError,KeyError,TypeError):
            r['backend']='regel_fallback';r['waarschuwingen'].append('Modelantwoord onbruikbaar; bestaande zoekregels gebruikt.');return r
    def zoek(self,q,r,filters=None):
        if not r.get('bevestigd'):raise ValueError('Bevestig of corrigeer eerst de interpretatie.')
        start=time.perf_counter();filters=filters or Filters()
        analyse=analyseer_vraag(q,self.index.plaatstabel,self.index.bekende_codes)
        plaats=filters.gemeente or (analyse.gemeenten[0] if len(analyse.gemeenten)==1 else None)
        gemeente=self.index.plaatstabel.get(normaliseer(plaats),normaliseer(plaats)) if plaats else None
        codes=list(analyse.codes)+([filters.productcode] if filters.productcode else [])
        wenst={s['concept'] for s in r['signalen']};uit={s['concept'] for s in r['uitsluitingen']}
        scores={};embedding_fout=False
        if self.embeddings and self.vectors:
            try:
                v=self.embeddings.encode([q+'; '+', '.join(LABELS[c] for c in sorted(wenst))],query=True)[0]
                scores={d['id']:sum(a*b for a,b in zip(v,e)) for d,e in zip(self.diensten,self.vectors)}
            except (ValueError,RuntimeError,OSError):embedding_fout=True
        resultaten=[]
        for d in self.diensten:
            if gemeente and not self.index._plaatsfilter(self.index._op_id[d['aanbieder_id']],gemeente):continue
            if not toelating_past(self.document,d,analyse,r):continue
            p=d['ruw'];bewijs=set(_concepten_in('; '.join(d['expertise'])))
            # Embeddings zijn geen bewijs van expertise. Alleen bronbegrippen dragen de match.
            specifieke_vormen=wenst&{'emdr','medicatie','logeer','residentieel','pleegzorg','gezinshuis','dagbesteding'}
            if not specifieke_vormen<=bewijs:continue
            if not wenst or not wenst&bewijs or uit&bewijs or (wenst&KLINISCH and not wenst&KLINISCH&bewijs):continue
            leeftijden=r['leeftijden'];doelen=(p.get('doelgroepen') or {}).get('waarde') or []
            bereiken=[(t,leeftijdsgrenzen(t)) for t in doelen] if isinstance(doelen,list) else []
            oordelen=[leeftijd_oordeel(n,n,bereiken)[0] for n in leeftijden]
            if 'buiten' in oordelen:continue
            if filters.doelgroep and not any(normaliseer(filters.doelgroep) in normaliseer(t) for t in doelen):continue
            producten=[x['code'] for x in (p.get('productcodes') or {}).get('waarde',[]) if isinstance(x,dict)]
            if codes and not {code_sleutel(c.removeprefix('code_')) for c in codes}<={code_sleutel(c) for c in producten}:continue
            if filters.vestigingsplaats and not any(normaliseer(v.get('plaats',''))==normaliseer(filters.vestigingsplaats) for v in (p.get('vestigingen') or {}).get('waarde',[])):continue
            routecodes=codes or (producten if d['dienstscope_bevestigd'] else [])
            toets=self.index.contractregister.oordeel(d['profiel'],gemeente=gemeente,codes=routecodes,op_datum=filters.op_datum or analyse.op_datum)
            wens=filters.gecontracteerd or analyse.contract
            if wens:
                label=(d['profiel'].get('gecontracteerd_regio') or {}).get('label')
                if wens=='bevestigd_nee':past=toets['status']=='nee' and label=='geverifieerd'
                elif wens=='niet_aangetroffen':past=toets['status']=='nee' and label=='afgeleid'
                else:past=toets['status']==wens
                if not past:continue
            datum=filters.op_datum or analyse.op_datum
            op=date.fromisoformat(datum) if datum and len(datum)==10 else date.today()
            regels=relevante_regels(self.document,d['aanbieder_id'],gemeente=gemeente,codes=routecodes,leeftijden=leeftijden,locatie=filters.vestigingsplaats)
            if analyse.max_wachttijd is not None:
                if regels:
                    if not (len(regels)==1 and actueel(regels[0]) and regels[0]['start_behandeling_weken'] is not None and regels[0]['start_behandeling_weken']<=analyse.max_wachttijd):continue
                elif not _past_wachttijd(p.get('wachttijd'),analyse.max_wachttijd):continue
            stop=toets['toeleiding']=='geblokkeerd' or any(algemene_stop(p,gemeente,datum,n,[] if toets['routes'] else routecodes) for n in (leeftijden or [None])) or any(stop_actief(x,op) or (actueel(x,op) and x['nieuwe_clienten']=='nee') for x in regels)
            beschikbaar='nee — relevante stop' if stop else ('ja — aanbieder bevestigd' if len(regels)==1 and actueel(regels[0]) and regels[0]['nieuwe_clienten']=='ja' else 'onbekend')
            ontbreekt=sorted(wenst-bewijs);score=scores.get(d['id'],0)
            resultaten.append({'id':d['id'],'aanbieder_id':d['aanbieder_id'],'naam':d['naam'],'dienst':d['dienst'],
              'inhoudelijk':'gedeeltelijk bronbewijs' if ontbreekt else 'bronbewijs gevonden; geschiktheid controleren',
              'ontbreekt':ontbreekt,'contract':toets,'beschikbaar':beschikbaar,'stop':stop,
              'leeftijd':'onbekend' if not oordelen or 'onbekend' in oordelen else 'binnen bronbereik',
              'toelatingsvoorwaarden':[(p.get(k) or {}).get('waarde') for k in ('uitsluitingscriteria','toelatingsvoorwaarden') if (p.get(k) or {}).get('waarde') not in (None,'','onbekend',[])],
              'dienstscope_bevestigd':d['dienstscope_bevestigd'],'bronbewijs':[d['bewijs']],
              'reden':'Bron vermeldt: '+d['bewijs']['citaat'],'score':round(score,6)})
        resultaten.sort(key=lambda x:(bool(x['ontbreekt']),len(x['ontbreekt']),-x['score'],x['naam'],x['id']))
        return {'backend':'regel_fallback' if r['backend']=='regel_fallback' else ('hybride_lokaal' if self.vectors and not embedding_fout else 'bronregels_zonder_embeddings'),
                'resultaten':resultaten[:20],'duur_ms':(time.perf_counter()-start)*1000,'kosten_eur':0,
                'waarschuwingen':['Geen garantie op geschiktheid, contractgeldigheid of instroom. Stops blijven zichtbaar.',
                                  'Afgeleide expertise/websites worden niet semantisch geïndexeerd.']}
