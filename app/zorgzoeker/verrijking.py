"""Begrensde openbare bronanalyse. Nooit schrijven naar actieve aanbiedersdata."""
from __future__ import annotations
import argparse,hashlib,json,re,time,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone,date
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin,urldefrag
from urllib.robotparser import RobotFileParser
from zorgzoeker.kwaliteitsbronnen import controleer_adres,GeenRedirect
from zorgzoeker.bewijs import hashwaarde
from zorgzoeker.synoniemen import concept_frases

AGENT='ZorgzoekerBroncontrole/1.0'
VELDEN={'expertise','doelgroepen','type_aanbod','werkgebied','vestigingen','toelatingsvoorwaarden','uitsluitingscriteria','aanmeldprocedure'}
class BronFout(ValueError):pass

def origin(url):
    u=urlsplit(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise BronFout('Alleen openbare HTTPS-bronnen zonder login')
    return 'https://'+u.hostname.lower()

class Pagina(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.blocks=[];self.current=[];self.links=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','nav','footer'):self.skip+=1
        if tag=='a':self.links.extend(v for k,v in attrs if k=='href')
        if tag in ('p','li','h1','h2','h3','div','section','br'):self.flush()
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','nav','footer'):self.skip=max(0,self.skip-1)
        if tag in ('p','li','h1','h2','h3','div','section'):self.flush()
    def handle_data(self,data):
        if not self.skip:self.current.append(data)
    def flush(self):
        s=' '.join(' '.join(self.current).split());self.current=[]
        if s:self.blocks.append(s)

def gevoelige_tekst(s):
    return bool(re.search(r'@|\b(?:06[\s-]?\d{8}|BSN|geboren op|mijn cliënt|ervaringsverhaal|onze medewerkers|ons team|mijn naam|ik ben|mevrouw|meneer|geboortedatum)\b',s,re.I))

def extraheer(body,url,aanbieder_id,op=None):
    p=Pagina();p.feed(body);p.flush();findings=[]
    for text in p.blocks:
        if not 12<=len(text)<=650 or gevoelige_tekst(text):continue
        # Uitsluitend expliciete uitspraken, niet losse navigatietermen of diagnoses infereren.
        if re.search(r'\b(?:geen|niet|uitsluit|uitsluitend|alleen|vanaf|tot en met|ouder dan|jonger dan)\b',text,re.I):
            veld='toelatingsvoorwaarden'
        elif re.search(r'\b\d{1,2}\s*(?:-|–|tot|t/m|jaar)\b',text,re.I):veld='doelgroepen'
        elif re.search(r'\b(?:behandeling|begeleiding|ambulant|verblijf|pleegzorg|dagbehandeling)\b',text,re.I):veld='type_aanbod'
        elif re.search(r'\b(?:werkgebied|locaties|gevestigd|regio)\b',text,re.I):veld='werkgebied'
        elif re.search(r'\b(?:aanmelden|aanmelding|verwijzen|verwijzing)\b',text,re.I):veld='aanmeldprocedure'
        else:veld='expertise'
        concepts=sorted({cid for frase,cid in concept_frases() if re.search(r'\b'+re.escape(frase)+r'\b',text,re.I)})
        if veld=='expertise' and not concepts:continue
        f={'aanbieder_id':aanbieder_id,'veld':veld,'citaat':text,'bron_url':url,'verzameld_op':op or datetime.now(timezone.utc).isoformat(),
           'bron_hash':hashlib.sha256(body.encode()).hexdigest(),'methode':'letterlijke_tekstextractie','taxonomie':concepts,
           'scope':'niet_vastgesteld','status':'ter_controle','soort':'vermoeden'}
        f['id']=hashwaarde({k:v for k,v in f.items() if k!='verzameld_op'});findings.append(f)
    return list({f['id']:f for f in findings}.values())

class Verzamelaar:
    def __init__(self,transport=None,clock=time.monotonic,pause=time.sleep):
        self.transport=transport or self._http;self.clock=clock;self.pause=pause;self.last={};self.robots={};self.cache={};self.requests=0;self.blocked=set()
    def _http(self,url,headers):
        controleer_adres(url)
        req=urllib.request.Request(url,headers={'User-Agent':AGENT,**headers})
        try:
            with urllib.request.build_opener(GeenRedirect()).open(req,timeout=12) as r:
                body=r.read(2_000_001)
                if len(body)>2_000_000:raise BronFout('Bron te groot')
                return r.status,dict(r.headers),body
        except urllib.error.HTTPError as e:return e.code,dict(e.headers),b''
    def request(self,url,allowed):
        current=url
        for _ in range(4):
            host=origin(current)
            if host in self.blocked:raise BronFout('Domein geblokkeerd voor deze run; Retry-After respecteren')
            if host not in allowed:raise BronFout('Redirect/domein buiten toegelaten scope')
            controleer_adres(current) if self.transport==self._http else None
            previous=self.last.get(host)
            if previous is not None:self.pause(max(0,3-(self.clock()-previous)))
            headers={}
            if current in self.cache:
                cached=self.cache[current]
                if cached[1].get('Etag'):headers['If-None-Match']=cached[1]['Etag']
                if cached[1].get('Last-Modified'):headers['If-Modified-Since']=cached[1]['Last-Modified']
            self.last[host]=self.clock();self.requests+=1
            status,h,body=self.transport(current,headers)
            h={k.title():v for k,v in h.items()}
            if status in (301,302,303,307,308):current=urljoin(current,h.get('Location',''));continue
            if status==304 and current in self.cache:return current,self.cache[current]
            if status in (403,429,503):
                self.blocked.add(host)
                raise BronFout('Toegang/limiet geweigerd; run stopt, geen retry. '+str(status)+' Retry-After='+h.get('Retry-After','onbekend'))
            if status!=200:raise BronFout('HTTP '+str(status))
            self.cache[current]=(status,h,body);return current,(status,h,body)
        raise BronFout('Te veel redirects')
    def toegelaten(self,url,allowed):
        host=origin(url)
        if host not in self.robots:
            _,(_,headers,data)=self.request(host+'/robots.txt',allowed)
            if not any(t in headers.get('Content-Type','').lower() for t in ('text/','application/octet-stream')):raise BronFout('Robots niet leesbaar')
            if 'text/html' in headers.get('Content-Type','').lower() or re.search(br'<(?:!doctype|html|body)\b',data,re.I):raise BronFout('HTML in plaats van robots.txt; toegang niet vastgesteld')
            robot=RobotFileParser();robot.parse(data.decode('utf-8',errors='replace').splitlines());self.robots[host]=robot
        return self.robots[host].can_fetch(AGENT,url)
    def run(self,provider,identiteit,max_paginas=20,inventarisatie=False):
        pid=provider['id'];url=identiteit['website'];allowed={origin(url)}
        if not inventarisatie:
            if not identiteit.get('expliciet_vrijgegeven') or not identiteit.get('beoordelaar') or not identiteit.get('bewijs_url'):raise BronFout('Website-identiteit nog niet expliciet vrijgegeven')
            if identiteit.get('aanbieder_id')!=pid:raise BronFout('Identiteit hoort bij andere aanbieder')
            if identiteit.get('naam_hash')!=hashwaarde(provider.get('naam',{})):raise BronFout('Naam gewijzigd of identiteitsbinding ontbreekt')
            try:controle=date.fromisoformat(identiteit['gecontroleerd_op'])
            except (KeyError,TypeError,ValueError):raise BronFout('Identiteitscontroledatum ontbreekt')
            if controle>date.today():raise BronFout('Identiteitscontrole ligt in toekomst')
            if origin(identiteit['bewijs_url'])==origin(url):raise BronFout('Onafhankelijke identiteitsbron vereist')
        if identiteit.get('toegangsvoorwaarden')!='toegestaan':raise BronFout('Toegangsvoorwaarden nog beoordelen')
        todo=[url];seen=set();bevindingen=[];issues=[];pages=[]
        while todo and len(seen)<min(20,max(1,max_paginas)):
            u=todo.pop(0);u=urldefrag(u)[0]
            if u in seen or urlsplit(u).query:continue
            if origin(u) not in allowed:continue
            seen.add(u)
            try:
                if not self.toegelaten(u,allowed):raise BronFout('Robots weigert deze pagina')
                final,(_,headers,raw)=self.request(u,allowed)
                if 'text/html' not in headers.get('Content-Type','').lower():
                    issues.append({'url':u,'reden':'Niet-HTML bron: handmatige controle nodig'});continue
                text=raw.decode('utf-8',errors='replace');p=Pagina();p.feed(text);p.flush()
                pages.append({'url':final,'sha256':hashlib.sha256(raw).hexdigest(),'status':'opgehaald'})
                if inventarisatie:break  # Identiteitsverkenning schrijft geen inhoudelijke profielbevindingen.
                fragments=extraheer(text,final,pid)
                fragments.sort(key=lambda b:b['veld']!='toelatingsvoorwaarden')
                if len(fragments)>25:issues.append({'url':u,'reden':'Meer dan 25 fragmenten; handmatige volledigheidscontrole nodig'})
                for b in fragments[:25]:
                    oud=provider.get(b['veld'],{})
                    b.update(profiel_hash=hashwaarde(provider),bestaande_waarde_hash=hashwaarde(oud),
                        vergelijking='mogelijke_tegenspraak' if re.search(r'\b(?:geen|niet|uitsluit)\b',b['citaat'],re.I) else 'bronaanwijzing_te_beoordelen',
                        bestaande_waarde=oud.get('waarde') if isinstance(oud,dict) else None)
                    bevindingen.append(b)
                for link in p.links:
                    v=urljoin(final,link)
                    if re.search(r'jeugd|kind|aanbod|hulp|behandel|begeleid|doelgroep|voor-wie|locatie|werkgebied|aanmeld|uitsluit',urlsplit(v).path,re.I) and not re.search(r'team|medewerker|verhaal|vacature|nieuws|blog',v,re.I):todo.append(v)
            except (ValueError,OSError) as e:
                issues.append({'url':u,'reden':str(e)[:240]});break
        if len(bevindingen)>100:issues.append({'reden':'Meer dan 100 fragmenten; aanvulling vereist handmatige controle'})
        bevindingen.sort(key=lambda b:b['veld']!='toelatingsvoorwaarden')
        self.cache.clear()  # Geen onbeperkte HTMLretentie tussen aanbieders.
        return {'aanbieder_id':pid,'identiteit':identiteit,'dataset_profiel_hash':hashwaarde(provider),'status':'identiteit_ter_controle' if inventarisatie else 'ter_controle',
                'paginas':pages,'bevindingen':list({b['id']:b for b in bevindingen[:100]}.values()),'problemen':issues,
                'aantal_verzoeken':self.requests,'gepubliceerd':False}

def voorstel_uit_bevinding(document,bevinding,*,beoordelaar,expliciet=False,nieuwe_waarde=None,beoordeling=None):
    from zorgzoeker.kwaliteit import voorstel
    if not expliciet or not beoordelaar.strip():raise ValueError('Inhoudelijke review vereist')
    if bevinding['veld'] not in VELDEN:raise ValueError('Geen toegelaten verrijkingsveld')
    if not isinstance(beoordeling,dict) or beoordeling.get('citaat')!=bevinding['citaat'] or beoordeling.get('bron_url')!=bevinding['bron_url']:raise ValueError('Review moet dit bronfragment onderbouwen')
    a=next(x for x in document['aanbieders'] if x['id']==bevinding['aanbieder_id'])
    if bevinding.get('profiel_hash')!=hashwaarde(a):raise ValueError('Profiel inmiddels gewijzigd')
    return voorstel(document,a['id'],bevinding['veld'],nieuwe_waarde,beoordeling,soort='openbare_verandering')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('identiteiten',type=Path);p.add_argument('--uitvoer',type=Path,required=True);p.add_argument('--inventariseer',action='store_true');p.add_argument('--max-aanbieders',type=int,default=12)
    a=p.parse_args();d=json.loads(a.dataset.read_text());ids=json.loads(a.identiteiten.read_text());resultaten=[]
    if a.uitvoer.exists():p.error('Uitvoer bestaat al; bronbestanden niet overschrijven')
    verzamelaar=Verzamelaar()
    for i in ids[:max(0,min(12,a.max_aanbieders))]:
        provider=next(x for x in d['aanbieders'] if x['id']==i['aanbieder_id'])
        try:resultaten.append(verzamelaar.run(provider,i,inventarisatie=a.inventariseer))
        except (ValueError,OSError) as e:resultaten.append({'aanbieder_id':provider['id'],'gepubliceerd':False,'bevindingen':[],'problemen':[{'reden':str(e)}]})
    with a.uitvoer.open('x') as f:json.dump({'dataset_hash':hashwaarde(d),'runs':resultaten},f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
