"""Mock/unit-tests bewijzen harde grenzen en UI; geen echte modelkwaliteit."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from zorgzoeker.ai_zoeken import HybrideZoeker,basis_interpretatie,pas_interpretatie_aan,valideer_modelantwoord,diensten
from zorgzoeker.ai_modellen import LokaalTaalmodel
from zorgzoeker.app import maak_app
from zorgzoeker.zoeken import Filters,Index
from zorgzoeker.valideer import valideer_document

ROOT=Path(__file__).resolve().parent/'ai'


@pytest.fixture
def doc():return json.loads((ROOT/'aanbieders.json').read_text())


class ModelMock:
    def __init__(self,*a,**kw):pass
    def interpreteer(self,q,concepten):
        return {'signalen':[{'concept':'angst','citaat':q}], 'uitsluitingen':[]}


class EmbeddingMock:
    def encode(self,teksten,**kw):return [[1.,0.] for _ in teksten]


def interpretatie(q,zoeker,concepten):
    return pas_interpretatie_aan(basis_interpretatie(q,zoeker.index),concepten=concepten)


def test_fixture_is_geldig_en_60_referenties_zijn_bevroren(doc):
    assert not valideer_document(doc)
    vragen=json.loads((ROOT/'vragen.json').read_text());assert len(vragen)>=50
    assert all('beoordeling' in c and 'relevante_diensten' in c for c in vragen)


def test_klachtinferentie_blijft_mogelijk_geen_diagnose(doc):
    i=Index(doc);q='Meisje van 14 wast steeds haar handen.'
    r=valideer_modelantwoord(q,{'signalen':[{'concept':'dwang','citaat':'wast steeds haar handen'}],'uitsluitingen':[]},i)
    assert r['leeftijden']==[14]
    assert r['signalen'][0]['status']=='mogelijk' and not r['bevestigd']
    with pytest.raises(ValueError):HybrideZoeker(doc).zoek(q,r)
    for antw in [{'aanbieder':'FICTIEF','signalen':[],'uitsluitingen':[]},{'signalen':[{'concept':'dwang','citaat':'niet in de vraag'}],'uitsluitingen':[]}]:
        with pytest.raises(ValueError):valideer_modelantwoord(q,antw,i)


def test_model_negatie_en_leeftijd_niet_omzeilen(doc):
    q='Kind van 14 met angst, geen medicatie';i=Index(doc)
    r=valideer_modelantwoord(q,{'signalen':[{'concept':'medicatie','citaat':'medicatie'}], 'uitsluitingen':[{'concept':'angst','citaat':q}]},i)
    assert r['leeftijden']==[14]
    assert {s['concept'] for s in r['signalen']}=={'angst'}
    assert {s['concept'] for s in r['uitsluitingen']}=={'medicatie'}


def test_harde_grenzen_blijven_bij_extreme_embeddings(doc):
    z=HybrideZoeker(doc,ModelMock(),EmbeddingMock());q='Kind van 14 met angst'
    r=interpretatie(q,z,['angst']);resultaat=z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']
    assert {x['aanbieder_id'] for x in resultaat}=={'angst','stop','onder'}
    stop=next(x for x in resultaat if x['aanbieder_id']=='stop');assert stop['stop'] and stop['beschikbaar'].startswith('nee')
    onder=next(x for x in resultaat if x['aanbieder_id']=='onder');assert onder['contract']['routes'][0]['hoofdaannemer']
    assert all(x['bronbewijs'] and x['bronbewijs'][0]['citaat'] for x in resultaat)
    assert not z.zoek(q,r,Filters(gemeente='Nijmegen',productcode='JW 45A99'))['resultaten']
    assert not z.zoek(q,r,Filters(gemeente='Nijmegen',gecontracteerd='ja',op_datum='2027-01-01'))['resultaten']


@pytest.mark.parametrize('q,verwacht',[('Kind van 3 met gedragsproblemen',set()),('Kinderen van 6 en 14 met angst',{'angst','stop','onder'}),('18-jarige met angst',{'volwassen'})])
def test_leeftijd_en_meerdere_kinderen(doc,q,verwacht):
    z=HybrideZoeker(doc,ModelMock(),EmbeddingMock());r=pas_interpretatie_aan(basis_interpretatie(q,z.index))
    assert {x['aanbieder_id'] for x in z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']}==verwacht


def test_niet_bevestigde_dienstexpertise_wordt_niet_geerfd(doc):
    doc['aanbieders'][0]['diensten'][0].pop('expertise')
    assert 'angst' not in {d['aanbieder_id'] for d in diensten(doc)}
    p=doc['aanbieders'][1];p['website']['label']='afgeleid';p['website']['toelichting']='FICTIEF afgeleid'
    assert 'dwang' not in {d['aanbieder_id'] for d in diensten(doc)}


def test_geen_expertise_uit_naam_of_productcode(doc):
    p=doc['aanbieders'][0];p['expertise']['waarde']=['Speltherapie'];p['diensten'][0]['expertise']=deepcopy(p['expertise']);p['naam']['waarde']='FICTIEF angst'
    p['productcodes']['waarde'][0]['omschrijving']='Angstbehandeling'
    z=HybrideZoeker(doc,ModelMock(),EmbeddingMock());q='Kind van 14 met angst';r=interpretatie(q,z,['angst'])
    assert 'angst' not in {x['aanbieder_id'] for x in z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']}


def test_negatie_specifieke_zorgvorm_en_ontbrekend_bewijs(doc):
    z=HybrideZoeker(doc,ModelMock(),EmbeddingMock())
    q='Kind van 12 met autisme zoekt logeeropvang';r=pas_interpretatie_aan(basis_interpretatie(q,z.index))
    assert [x['aanbieder_id'] for x in z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']]==['respijt']
    q='Kind van 12 met autisme en ADHD';r=pas_interpretatie_aan(basis_interpretatie(q,z.index))
    rs=z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']
    assert rs[0]['aanbieder_id']=='assadhd' and not rs[0]['ontbreekt']
    assert all(x['ontbreekt'] for x in rs[1:])


def test_maximum_wacht_en_extra_toelatingsvoorwaarden(doc):
    z=HybrideZoeker(doc,ModelMock(),EmbeddingMock());q='Kind van 14 met angst maximaal twee weken';r=pas_interpretatie_aan(basis_interpretatie(q,z.index))
    assert not z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']


def test_onbeschikbaar_model_eerlijk_fallback(doc):
    class Kapot:
        def interpreteer(self,*a):raise OSError('FICTIEF fout')
    z=HybrideZoeker(doc,Kapot());q='Kind van 14 met angst';r=z.interpreteer(q)
    assert r['backend']=='regel_fallback'
    res=z.zoek(q,pas_interpretatie_aan(r),Filters(gemeente='Nijmegen'))
    assert res['backend']=='regel_fallback' and res['kosten_eur']==0


@pytest.mark.parametrize('url',['https://api.example.org','http://localhost:8765','http://127.0.0.1:8765/ander','http://u:p@127.0.0.1','http://169.254.169.254'])
def test_geen_externe_of_credential_endpoints(url):
    with pytest.raises(ValueError):LokaalTaalmodel(url)


def test_standaard_uitgeschakeld_en_niet_zomaar_activeerbaar(monkeypatch):
    monkeypatch.delenv('ZORGZOEKER_AI_AAN',raising=False);monkeypatch.delenv('ZORGZOEKER_AI_FICTIEVE_TESTS',raising=False)
    c=TestClient(maak_app(ROOT/'aanbieders.json'))
    assert c.get('/ai').status_code==404
    assert c.post('/api/ai/interpreteer',json={'q':'FICTIEF','fictief':True}).status_code==404
    monkeypatch.setenv('ZORGZOEKER_AI_AAN','1')
    assert c.get('/ai').status_code==404


def test_ui_en_api_bevestiging_correctie_privacy_en_bronbewijs(monkeypatch):
    import zorgzoeker.ai_web as web
    monkeypatch.setenv('ZORGZOEKER_AI_AAN','1');monkeypatch.setenv('ZORGZOEKER_AI_FICTIEVE_TESTS','1')
    monkeypatch.setattr(web,'LokaalTaalmodel',ModelMock)
    c=TestClient(maak_app(ROOT/'aanbieders.json'));q='Kind van 14 met angst'
    assert c.post('/api/ai/interpreteer',json={'q':q}).status_code==400
    assert c.post('/api/ai/interpreteer',content=b'x'*9000).status_code==400
    r=c.post('/api/ai/interpreteer',json={'q':q,'fictief':True}).json()['interpretatie']
    assert r and not r['bevestigd']
    payload={'actie':'zoek','q':q,'fictief':True,'interpretatie':r,'gemeente':'Nijmegen'}
    assert c.post('/api/ai/zoek',json=payload).status_code==400
    response=c.post('/api/ai/zoek',json={**payload,'bevestigd':True}).json()
    assert response['zoekresultaat'] and any(x.get('stop') for x in response['zoekresultaat']['resultaten'])
    assert c.post('/api/ai/zoek',json={**payload,'bevestigd':True,'leeftijden':[999]}).status_code==400
    html=c.post('/ai',data={'q':q,'fictief':'1'}).text
    assert 'Zo is de hulpvraag begrepen' in html and 'bevestigd' in html and 'Uitgesloten' in html
    assert c.get('/').status_code==200


def test_alleen_explicitiet_aangepaste_interpretatie_geen_stille_ai_leeftijd(doc):
    z=HybrideZoeker(doc);r=basis_interpretatie('Kind van 14 met angst',z.index)
    aangepast=pas_interpretatie_aan(r,leeftijden=[18],concepten=['angst'])
    assert aangepast['leeftijden']==[18] and r['leeftijden']==[14]
    assert {x['aanbieder_id'] for x in z.zoek('Kind van 14 met angst',aangepast,Filters(gemeente='Nijmegen'))['resultaten']}=={'volwassen'}


def test_misvormde_interpretaties_worden_geweigerd(doc):
    r=basis_interpretatie('Kind van 14 met angst',Index(doc))
    for key,value in [('signalen',['angst']),('signalen',[{'concept':[]}]),('leeftijden',[float('nan')])]:
        with pytest.raises(ValueError):pas_interpretatie_aan({**r,key:value})


def test_aanbiederniveau_is_geen_bevestigde_dienstscope(doc):
    p=doc['aanbieders'][0];p.pop('diensten')
    z=HybrideZoeker(doc);q='Kind van 14 met angst';r=interpretatie(q,z,['angst'])
    rs=z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']
    assert not next(x for x in rs if x['aanbieder_id']=='angst')['dienstscope_bevestigd']


def test_brongebonden_gestructureerde_toelatingsuitsluiting(doc):
    p=doc['aanbieders'][0]
    p['toelatingsregels']=[{'soort':'geslacht','waarde':'meisjes','label':'geverifieerd','bron_url':'https://example.org/toelating','opgehaald_op':'2026-10-25'}]
    z=HybrideZoeker(doc);q='Jongen van 14 met angst';r=interpretatie(q,z,['angst'])
    assert 'angst' not in {x['aanbieder_id'] for x in z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']}
    q='Meisje van 14 met angst';r=interpretatie(q,z,['angst'])
    assert 'angst' in {x['aanbieder_id'] for x in z.zoek(q,r,Filters(gemeente='Nijmegen'))['resultaten']}
