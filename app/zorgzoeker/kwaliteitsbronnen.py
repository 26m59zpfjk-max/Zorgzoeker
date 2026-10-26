"""Expliciet gestarte, begrensde openbare bronwaarnemingen. Geen crawler/agent.

Bereikbaarheid en naamsignalen zijn GEEN verificatie van een aanbieder of feit.
Geen cookies, browser, logins, mail, POST-verzoeken of automatische uitvoering.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import ipaddress
import socket
from urllib.parse import urlsplit, urljoin
import urllib.request


def openbare_url(url: str) -> bool:
    try:
        u = urlsplit(url)
        return bool(u.scheme in {'https','http'} and u.hostname and not u.username and not u.password
                    and u.port in (None,80,443) and not any(c.isspace() for c in url)
                    and not u.hostname.lower().endswith(('.localhost','.local','.internal'))
                    and u.hostname.lower() != 'localhost')
    except (ValueError,TypeError):
        return False


def controleer_adres(url: str) -> None:
    if not openbare_url(url):
        raise ValueError('Geen openbare http(s)-URL zonder inloggegevens.')
    u=urlsplit(url)
    adressen=socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not adressen or any(not ipaddress.ip_address(a[4][0]).is_global for a in adressen):
        raise ValueError('Privaat, lokaal of gereserveerd doeladres geweigerd.')


class GeenRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class Titel(HTMLParser):
    def __init__(self):
        super().__init__();self.in_title=False;self.titel=[];self.tekst=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript'}:self.skip+=1
        if tag=='title':self.in_title=True
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript'}:self.skip=max(0,self.skip-1)
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.titel.append(data)
        if not self.skip:self.tekst.append(data.strip())


def haal_bron(url: str, *, limiet=4_000_000, timeout=12, cachemap=None) -> dict:
    resultaat={'url':url,'gecontroleerd_op':datetime.now(timezone.utc).isoformat(),
               'status':'niet_gecontroleerd','http_status':None,'eind_url':None,
               'titel':None,'citaat':None,'sha256':None,'publicatiedatum':None,
               'verificatie':'openbare_waarneming_geen_inhoudelijke_verificatie'}
    try:
        opener=urllib.request.build_opener(GeenRedirect())
        doel=url
        for _ in range(5):
            controleer_adres(doel)
            req=urllib.request.Request(doel,headers={'User-Agent':'Zorgzoeker-broncontrole/0.1 (public profile quality review)'})
            try:
                response=opener.open(req,timeout=timeout)
            except urllib.error.HTTPError as e:
                if e.code in (301,302,303,307,308) and e.headers.get('Location'):
                    doel=urljoin(doel,e.headers['Location']);continue
                resultaat.update(status='niet_bereikbaar',http_status=e.code);return resultaat
            with response:
                body=response.read(limiet+1)
                if len(body)>limiet:raise ValueError('Bron te groot; geen onbeperkte download.')
                resultaat.update(http_status=response.status,eind_url=doel,sha256=hashlib.sha256(body).hexdigest(),
                                 status='opgehaald',content_type=response.headers.get('Content-Type',''),
                                 last_modified=response.headers.get('Last-Modified'))
                if cachemap:
                    from pathlib import Path
                    p=Path(cachemap);p.mkdir(parents=True,exist_ok=True)
                    (p/resultaat['sha256']).write_bytes(body)
                if 'html' in resultaat['content_type']:
                    parser=Titel();parser.feed(body.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'))
                    resultaat['titel']=' '.join(' '.join(parser.titel).split())[:200]
                    resultaat['citaat']=' '.join(' '.join(parser.tekst).split())[:240]
                return resultaat
        raise ValueError('Te veel redirects.')
    except (OSError,ValueError,TimeoutError) as e:
        resultaat.update(status='controle_mislukt',fout=type(e).__name__)
        return resultaat


def vergelijk_waarneming(oud: dict | None, nieuw: dict) -> dict:
    gewijzigd=bool(oud and oud.get('sha256') and nieuw.get('sha256') and oud['sha256']!=nieuw['sha256'])
    return {'soort':'openbare_verandering' if gewijzigd else 'vermoeden',
            'hercontrole_nodig':gewijzigd or nieuw.get('status')!='opgehaald',
            'reden':'Broninhoud gewijzigd; veldinhoud moet beoordeeld worden.' if gewijzigd else 'Geen rechtstreeks bevestigde wijziging vastgesteld.',
            'oud_sha256':(oud or {}).get('sha256'),'nieuw_sha256':nieuw.get('sha256')}
