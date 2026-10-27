import json
from copy import deepcopy
import pytest
from zorgzoeker.verrijking import Verzamelaar,BronFout,extraheer,origin,voorstel_uit_bevinding


def ident(**kw):
    from datetime import date
    from zorgzoeker.bewijs import hashwaarde
    return {'naam_hash':hashwaarde({}),'gecontroleerd_op':date.today().isoformat(),'aanbieder_id':'fictief','website':'https://example.org/','expliciet_vrijgegeven':True,'beoordelaar':'FICTIEF reviewer','bewijs_url':'https://register.example.org/id','toegangsvoorwaarden':'toegestaan',**kw}
def test_extractie_bewaart_ontkenning_en_bron():
    h='<p>Wij behandelen angst bij jongeren.</p><p>Geen behandeling voor kinderen jonger dan 12 jaar.</p><p>Medewerker Jan: jan@example.org</p>'
    r=extraheer(h,'https://example.org/','fictief')
    assert len(r)==2 and r[1]['veld']=='toelatingsvoorwaarden'
    assert r[1]['citaat']=='Geen behandeling voor kinderen jonger dan 12 jaar.'
    assert all(x['bron_hash'] and x['scope']=='niet_vastgesteld' and x['status']=='ter_controle' for x in r)
    assert extraheer(h,'https://example.org/','fictief')[0]['id']==r[0]['id']

@pytest.mark.parametrize('url',['http://example.org','https://a:b@example.org','https://example.org:8443'])
def test_weiger_onveilige_url(url):
    with pytest.raises(BronFout):origin(url)

@pytest.mark.parametrize('override',[{'expliciet_vrijgegeven':False},{'aanbieder_id':'anders'},{'toegangsvoorwaarden':'onbekend'}])
def test_identiteit_poort_geen_verzoeken(override):
    def fout(*a):raise AssertionError('Geen netwerk voor ongecontroleerde identiteit')
    with pytest.raises(BronFout):Verzamelaar(transport=fout).run({'id':'fictief'},ident(**override))

@pytest.mark.parametrize('robots,status',[('User-agent: *\nDisallow: /',200),('',403),('',429)])
def test_robots_en_weigeringen_stoppen(robots,status):
    calls=[]
    def http(url,h):calls.append(url);return status,{'Content-Type':'text/plain'},robots.encode()
    r=Verzamelaar(transport=http,pause=lambda _:None).run({'id':'fictief'},ident())
    assert not r['bevindingen'] and r['problemen'] and len(calls)==1


def test_domein_scope_budget_throttle_en_geen_mutatie():
    calls=[];pauses=[];p={'id':'fictief','expertise':{'waarde':[]}};old=deepcopy(p)
    def http(url,h):
        calls.append(url)
        if url.endswith('robots.txt'):return 200,{'Content-Type':'text/plain'},b'User-agent: *\nAllow: /'
        return 200,{'Content-Type':'text/html'},b'<p>Wij begeleiden jongeren met angst.</p><a href="/jeugd">jeugd</a><a href="https://elsewhere.org/jeugd">extern</a><a href="/team/jeugd">team</a>'
    r=Verzamelaar(transport=http,clock=lambda:10,pause=pauses.append).run(p,ident(),max_paginas=2)
    assert len(r['paginas'])==2 and r['bevindingen'] and not r['gepubliceerd'] and p==old
    assert len(calls)==3 and all(x==3 for x in pauses)
    assert all('elsewhere' not in c and '/team/' not in c for c in calls)


def test_redirect_niet_naar_andere_host():
    def http(url,h):return 302,{'Location':'https://127.0.0.1/secret'},b''
    with pytest.raises(BronFout):Verzamelaar(transport=http).request('https://example.org/',{'https://example.org'})


def test_geen_automatische_voorstellen():
    with pytest.raises(ValueError):voorstel_uit_bevinding({}, {},beoordelaar='',expliciet=False)


def test_inventarisatie_verrijkt_niet():
    def http(url,h):return (200,{'Content-Type':'text/plain'},b'User-agent: *\nAllow: /') if url.endswith('robots.txt') else (200,{'Content-Type':'text/html'},b'<p>Wij behandelen angst bij kinderen.</p>')
    r=Verzamelaar(transport=http,pause=lambda _:None).run({'id':'fictief'},ident(expliciet_vrijgegeven=False),inventarisatie=True)
    assert r['paginas'] and not r['bevindingen'] and r['status']=='identiteit_ter_controle'


def test_retry_after_blokkeert_ook_volgende_aanbieder_op_domein():
    calls=[]
    def http(url,h):calls.append(url);return 429,{'Retry-After':'3600'},b''
    v=Verzamelaar(transport=http,pause=lambda _:None)
    for n in range(2):
        r=v.run({'id':'fictief'},ident())
        assert r['problemen'] and not r['bevindingen']
    assert len(calls)==1

@pytest.mark.parametrize('change',[{'naam_hash':'gewijzigd'},{'gecontroleerd_op':'2099-01-01'},{'bewijs_url':'https://example.org/ons-team'}])
def test_verouderde_of_onafhankelijke_identiteit_ontbreekt(change):
    with pytest.raises(BronFout):Verzamelaar(transport=lambda *a: (_ for _ in ()).throw(AssertionError('Geen netwerk'))).run({'id':'fictief'},ident(**change))


def test_gecontroleerd_fragment_wordt_voorstel_geen_publicatie(fixture_pad):
    from pathlib import Path
    from zorgzoeker.bewijs import hashwaarde
    from tests.test_kwaliteit import beoordeling
    from tests.test_4c import document
    d=document();p=d['aanbieders'][0]
    f=extraheer('<p>Wij behandelen angst bij jongeren.</p>','https://example.org/jeugd',p['id'])[0]
    nieuw={**p['expertise'],'waarde':['Angst']};b=beoordeling(d,k='expertise');b.update(citaat=f['citaat'],bron_url=f['bron_url'],waarde_hash=hashwaarde(nieuw))
    f['profiel_hash']=hashwaarde(p)
    v=voorstel_uit_bevinding(d,f,beoordelaar='FICTIEF reviewer',expliciet=True,nieuwe_waarde=nieuw,beoordeling=b)
    assert v['status']=='ter_controle' and d['aanbieders'][0]==p
    f['profiel_hash']='gewijzigd'
    with pytest.raises(ValueError):voorstel_uit_bevinding(d,f,beoordelaar='FICTIEF',expliciet=True,nieuwe_waarde=nieuw,beoordeling=b)


def test_conditioneel_verzoek_etag_en_304():
    headers=[]
    def http(url,h):
        headers.append(h)
        return (200,{'ETag':'"v1"','Content-Type':'text/html'},b'<p>openbaar</p>') if len(headers)==1 else (304,{},b'')
    v=Verzamelaar(transport=http,pause=lambda _:None)
    first=v.request('https://example.org/',{'https://example.org'})
    second=v.request('https://example.org/',{'https://example.org'})
    assert first==second and headers[1]['If-None-Match']=='"v1"'
