"""Deterministische kwaliteitscontrole. Brongegevens blijven onveranderd.

Bronlabels uit legacy-data bewijzen geen onafhankelijke inhoudelijke controle.
Beoordelingen zijn per waarde/hash, bron, datum en reviewer herleidbaar.
"""
from copy import deepcopy
from datetime import date,timedelta
from difflib import SequenceMatcher
import hashlib
import json
import re
from urllib.parse import urlsplit

from zorgzoeker.contracten import code_sleutel, sleutel
from zorgzoeker.config import max_wachttijd_dagen
from zorgzoeker.kwaliteitsbronnen import openbare_url
from zorgzoeker.valideer import peildatum_veld, wachttijd_ouderdom, valideer_document
from zorgzoeker.zoeken import leeftijdsgrenzen

KERN=('naam','website','expertise','doelgroepen','gecontracteerd_regio','productcodes','beschikbaarheid','wachttijd')
VELDEN=KERN+('handelsnamen','type_aanbod','vestigingen','werkgebied','hoofdaannemer','toelatingsvoorwaarden')
STATUSSEN={'geverifieerd','bron_te_controleren','tegenstrijdig_of_verouderd','ontbrekend'}
METHODEN={'openbare_bron_gecontroleerd','rechtstreeks_bevestigd','afgeleid','onbekend'}


def hashwaarde(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _datum(s):
    try:return date.fromisoformat(s) if isinstance(s,str) else None
    except ValueError:return None


def valideer_beoordeling(b, vandaag=None):
    vandaag=vandaag or date.today();f=[]
    if not isinstance(b,dict):return ['Beoordeling moet een object zijn.']
    for k in ('aanbieder_id','veld','waarde_hash','beoordelaar','citaat'):
        if not isinstance(b.get(k),str) or not b[k].strip():f.append(f'{k} ontbreekt.')
    if not isinstance(b.get('methode'),str) or b['methode'] not in METHODEN:f.append('Ongeldige verificatiemethode.')
    if not isinstance(b.get('status'),str) or b['status'] not in STATUSSEN:f.append('Ongeldige kwaliteitsstatus.')
    if not openbare_url(b.get('bron_url')):f.append('Bron-URL ontbreekt of is onveilig.')
    d=_datum(b.get('gecontroleerd_op'));h=_datum(b.get('hercontrole_op'))
    if not d or d>vandaag or not h or h<=d:f.append('Controle-/hercontroledatum ongeldig.')
    for k in ('gepubliceerd_op','geldig_van','geldig_tot'):
        if b.get(k) is not None and not _datum(b[k]):f.append(f'{k} ongeldig.')
    if _datum(b.get('gepubliceerd_op')) and _datum(b['gepubliceerd_op'])>vandaag:f.append('Publicatiedatum ligt in de toekomst.')
    if _datum(b.get('geldig_van')) and _datum(b.get('geldig_tot')) and b['geldig_tot']<b['geldig_van']:f.append('Geldigheidsperiode omgekeerd.')
    if b.get('status')=='geverifieerd' and b.get('methode') not in {'openbare_bron_gecontroleerd','rechtstreeks_bevestigd'}:
        f.append('Een afleiding is geen verificatie.')
    if not isinstance(b.get('tegenstrijdigheden'),list) or any(not isinstance(t,str) for t in b.get('tegenstrijdigheden',[])):f.append('Tegenstrijdigheden moeten teksten zijn.')
    if b.get('tegenstrijdigheden') and b.get('status')=='geverifieerd':f.append('Tegenstrijdige informatie kan niet geverifieerd heten.')
    return f


def analyseer(document, *, beoordelingen=(), waarnemingen=(), vandaag=None):
    vandaag=vandaag or date.today()
    observaties={w['url']:w for w in waarnemingen}
    reviews={}
    for b in beoordelingen:
        if not valideer_beoordeling(b,vandaag):reviews.setdefault((b['aanbieder_id'],b['veld']),[]).append(b)
    rapport={'gegenereerd_op':vandaag.isoformat(),'dataset_hash':hashwaarde(document),
             'beleid':'Zonder inhoudelijke beoordeling blijft een bron te controleren; bereikbaarheid is geen verificatie.',
             'ongeldige_beoordelingen':[{'index':n,'fouten':valideer_beoordeling(b,vandaag)} for n,b in enumerate(beoordelingen) if valideer_beoordeling(b,vandaag)],'schemafouten':valideer_document(document),'aanbieders':[],'problemen':[]}
    regels=(document.get('contractregister') or {}).get('regels',[])
    register=document.get('contractregister') or {}
    def probleem(a,k,code,prioriteit,tekst):
        item={'aanbieder_id':a['id'],'naam':(a.get('naam') or {}).get('waarde'),
              'veld':k,'code':code,'prioriteit':prioriteit,'toelichting':tekst}
        rapport['problemen'].append(item)
    for a in document['aanbieders']:
        velden={};routes=[r for r in regels if r['aanbieder_id']==a['id']]
        for k in VELDEN:
            v=a.get(k) or {};w=v.get('waarde');bron=v.get('bron_url')
            ontbreekt=w in (None,'','onbekend',[])
            status='ontbrekend' if ontbreekt else 'bron_te_controleren'
            kandidaten=[b for b in reviews.get((a['id'],k),[]) if b['waarde_hash']==hashwaarde(v)]
            b=max(kandidaten,key=lambda b:b['gecontroleerd_op']) if kandidaten else None
            redenen=[]
            if b and not ontbreekt:
                status=b['status']
                if b['hercontrole_op']<=vandaag.isoformat() or (b.get('geldig_tot') and b['geldig_tot']<vandaag.isoformat()):
                    status='tegenstrijdig_of_verouderd';redenen.append('Hercontrole/geldigheid verstreken.')
            if v and not ontbreekt and not openbare_url(bron):
                status='tegenstrijdig_of_verouderd';redenen.append('Geen bruikbare bron.')
                probleem(a,k,'bron_ontbreekt',1,'Waarde heeft geen openbare herleidbare bron.')
            oud=wachttijd_ouderdom(v,vandaag) if k=='wachttijd' else None
            if oud is not None and oud>max_wachttijd_dagen():
                status='tegenstrijdig_of_verouderd';redenen.append(f'Wachttijdpublicatie {oud} dagen oud.')
                probleem(a,k,'wachttijd_verouderd',1,redenen[-1])
            if ontbreekt and k in KERN:probleem(a,k,'kerngegeven_ontbreekt',1 if k in {'expertise','doelgroepen','beschikbaarheid'} else 2,'Ontbreekt; niet door AI invullen.')
            if status=='bron_te_controleren' and k in KERN:probleem(a,k,'inhoudelijke_controle_nodig',2,'Bronlabel alleen is onvoldoende; vergelijk het veld met de bron.')
            if k=='website' and not ontbreekt:
                if not openbare_url(w):
                    status='tegenstrijdig_of_verouderd';probleem(a,k,'website_ongeldig',1,'Website is geen veilige openbare http(s)-URL.')
                if v.get('label')=='afgeleid':probleem(a,k,'website_identiteit_onbevestigd',1,'Koppeling op naam afgeleid; controleer identiteit vóór expertise aan deze website toe te schrijven.')
                obs=observaties.get(w)
                if obs and obs['status']!='opgehaald':
                    redenen.append('Website niet bereikbaar tijdens controle; dit bewijst geen bedrijfsbeëindiging.')
                    probleem(a,k,'website_niet_bereikbaar',1,redenen[-1])
            velden[k]={'status':status,'legacy_label':v.get('label','onbekend'),'waarde_hash':hashwaarde(v),
                       'bron_url':bron,'bron':(b.get('bron') if b else None),'gepubliceerd_op':b.get('gepubliceerd_op') if b else peildatum_veld(v),
                       'geldig_van':b.get('geldig_van') if b else None,'geldig_tot':b.get('geldig_tot') if b else None,
                       'laatste_controle':b['gecontroleerd_op'] if b else None,'laatste_ophaal':v.get('opgehaald_op'),
                       'methode':b['methode'] if b else ('afgeleid' if v.get('label')=='afgeleid' else 'onbekend'),
                       'beoordelaar':b['beoordelaar'] if b else None,'tegenstrijdigheden':b.get('tegenstrijdigheden',[]) if b else [],
                       'hercontrole_nodig':status!='geverifieerd','hercontrole_op':b['hercontrole_op'] if b else vandaag.isoformat(),
                       'redenen':redenen,'waarneming':observaties.get(w if k=='website' and isinstance(w,str) else bron)}
        # Leeftijdsteksten met expliciet omgekeerde grenzen; meerdere diensten zijn geen bewezen tegenspraak.
        doelen=(a.get('doelgroepen') or {}).get('waarde') or []
        for t in doelen if isinstance(doelen,list) else []:
            if re.search(r'\b(\d+)\s*(?:-|tot|t/m)\s*(\d+)',t):
                m=re.search(r'\b(\d+)\s*(?:-|tot|t/m)\s*(\d+)',t)
                if int(m[1])>int(m[2]):probleem(a,'doelgroepen','leeftijd_tegenstrijdig',1,t);velden['doelgroepen']['status']='tegenstrijdig_of_verouderd'
        expliciet=[t for t in doelen if leeftijdsgrenzen(t)] if isinstance(doelen,list) else []
        if len(expliciet)>1:
            probleem(a,'doelgroepen','leeftijd_per_dienst_controleren',2,'Meerdere leeftijdsteksten: controleer dienstscope; dit bewijst nog geen tegenspraak.')
        if doelen and not expliciet:probleem(a,'doelgroepen','leeftijdsgrenzen_onduidelijk',1,'Doelgroep bekend, expliciete leeftijdsgrenzen niet vastgesteld.')
        products=(a.get('productcodes') or {}).get('waarde') or []
        for p in products if isinstance(products,list) else []:
            if not any(code_sleutel(r['productcode'])==code_sleutel(p['code']) for r in routes):probleem(a,'productcodes','contractbron_per_product_ontbreekt',1,p['code'])
        if any(r.get('hoofdaannemer') for r in routes) and not all(r.get('hoofdaannemer') for r in routes if r.get('hoofdaannemer') is not None):
            probleem(a,'hoofdaannemer','hoofdaannemer_ongeldig',1,'Onvolledige hoofdcontractant in route.')
        if (a.get('gecontracteerd_regio') or {}).get('waarde')=='ja' and re.search(r'als onderaannemer|via (?:de )?hoofdaannemer',str((a.get('gecontracteerd_regio') or {}).get('toelichting','')),re.I) and not routes and not a.get('hoofdaannemer'):
            probleem(a,'hoofdaannemer','hoofdaannemer_ontbreekt',1,'Onderaannemerschap genoemd zonder herleidbare route/hoofdaannemer.')
        if (a.get('gecontracteerd_regio') or {}).get('waarde')=='ja':
            probleem(a,'gecontracteerd_regio','contractperiode_onbekend',1,'Bron is een snapshot op '+str(register.get('peildatum'))+'; geen bewezen begin/einddatum.')
        stoptekst=str((a.get('beschikbaarheid') or {}).get('waarde',''))
        if re.search(r'(?:aanmeld|toeleidings|cliënten)stop',stoptekst,re.I):
            probleem(a,'beschikbaarheid','stop_scope_en_periode_controleren',1,'Vergelijk gemeenten, zorgvormen/producten, leeftijden en einddatum met de bron; een ongedateerde stop niet stilzwijgend opheffen.')
        if not a.get('handelsnamen'):probleem(a,'handelsnamen','handelsnamen_onbekend',3,'Alternatieve handelsnamen niet vastgelegd; geen varianten verzinnen.')
        for v in velden.values():v['hercontrole_nodig']=v['status']!='geverifieerd'
        rapport['aanbieders'].append({'id':a['id'],'naam':(a.get('naam') or {}).get('waarde'),
          'kern_voldoende_onderbouwd':all(velden[k]['status']=='geverifieerd' for k in KERN),
          'velden':velden})
    # Kandidaten voor dubbelingen zijn onderzoeksvragen, nooit automatisch samenvoegen.
    aanbieders=document['aanbieders']
    for n,a in enumerate(aanbieders):
        for b in aanbieders[n+1:]:
            an=sleutel(str((a.get('naam') or {}).get('waarde','')));bn=sleutel(str((b.get('naam') or {}).get('waarde','')))
            aw=(a.get('website') or {}).get('waarde');bw=(b.get('website') or {}).get('waarde')
            zelfde_domein=openbare_url(aw) and openbare_url(bw) and urlsplit(aw).hostname==urlsplit(bw).hostname
            if an==bn or (min(len(an),len(bn))>6 and SequenceMatcher(None,an,bn).ratio()>.9) or zelfde_domein:
                probleem(a,'naam','mogelijke_dubbeling',2,f"Vergelijk met {b['id']}: naam-/domeinovereenkomst is geen bewijs van dezelfde organisatie.")
    rapport['problemen'].sort(key=lambda p:(p['prioriteit'],p['aanbieder_id'],p['veld'],p['code']))
    rapport['samenvatting']={'aanbieders':len(aanbieders),'kern_voldoende':sum(a['kern_voldoende_onderbouwd'] for a in rapport['aanbieders']),
       'problemen':len(rapport['problemen']),'afgeleide_websites':sum((a.get('website') or {}).get('label')=='afgeleid' for a in aanbieders),
       'veldstatussen':{s:sum(v['status']==s for a in rapport['aanbieders'] for v in a['velden'].values()) for s in sorted(STATUSSEN)}}
    return rapport


def voorstel(document, aanbieder_id, veld, nieuwe_waarde, beoordeling, *, soort='vermoeden'):
    if soort not in {'openbare_verandering','rechtstreeks_bevestigd','vermoeden'}:raise ValueError('Onbekende wijzigingssoort.')
    if valideer_beoordeling(beoordeling):raise ValueError('Ongeldige veldbeoordeling.')
    a=next(a for a in document['aanbieders'] if a['id']==aanbieder_id)
    if veld not in VELDEN or beoordeling['aanbieder_id']!=aanbieder_id or beoordeling['veld']!=veld or beoordeling['waarde_hash']!=hashwaarde(nieuwe_waarde):raise ValueError('Voorstel en bewijs zijn niet aan dezelfde waarde gebonden.')
    if soort=='rechtstreeks_bevestigd' and beoordeling['methode']!='rechtstreeks_bevestigd':raise ValueError('Geen directe bevestiging aanwezig.')
    return {'status':'ter_controle','soort':soort,'dataset_hash':hashwaarde(document),'aanbieder_id':aanbieder_id,
            'veld':veld,'vorige':deepcopy(a.get(veld)),'nieuwe':deepcopy(nieuwe_waarde),'beoordeling':deepcopy(beoordeling)}


def neem_voorstel_op(document,p,*,beoordelaar,expliciet=False):
    if not expliciet or not beoordelaar.strip() or p.get('status')!='ter_controle' or p['dataset_hash']!=hashwaarde(document):raise ValueError('Expliciete controle vereist of bron gewijzigd.')
    voorstel(document,p['aanbieder_id'],p['veld'],p['nieuwe'],p['beoordeling'],soort=p['soort'])
    nieuw=deepcopy(document)
    a=next(a for a in nieuw['aanbieders'] if a['id']==p['aanbieder_id']);a[p['veld']]=deepcopy(p['nieuwe'])
    if valideer_document(nieuw):raise ValueError('Nieuwe gegevens voldoen niet aan het schema.')
    nieuw.setdefault('kwaliteitsbeoordelingen',[]).append(deepcopy(p['beoordeling']))
    nieuw.setdefault('kwaliteitshistorie',[]).append({**deepcopy(p),'gecontroleerd_door':beoordelaar,'op':date.today().isoformat()})
    return nieuw
