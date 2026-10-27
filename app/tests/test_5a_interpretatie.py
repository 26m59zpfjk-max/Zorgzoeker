"""Fictieve 5A-regressies: lokale interpretatie en positieve/negatieve matches."""
import pytest
from zorgzoeker.zoeken import analyseer_vraag
from tests.test_betrouwbaarheid import aanbieder, index_van


@pytest.mark.parametrize('vraag,concepten,uitsluitingen', [
    ('geen medicatie angst', ['angst'], ['medicatie']),
    ('angst zonder medicatie en trauma', ['angst', 'trauma'], ['medicatie']),
    ('geen EMDR of medicatie, wel trauma', ['trauma'], ['emdr', 'medicatie']),
    ('EMDR niet gewenst en trauma', ['trauma'], ['emdr']),
    ('niet alleen angst maar ook trauma', ['angst', 'trauma'], []),
    ('geen autisme vastgesteld, wel angst', ['angst'], []),
])
def test_negatie_scope(vraag, concepten, uitsluitingen):
    a = analyseer_vraag(vraag, {}, set())
    assert a.concepten == concepten
    assert a.uitgesloten == uitsluitingen


@pytest.mark.parametrize('vraag', ['geen medicatie angst', 'angst zonder medicatie en trauma'])
def test_negatie_vindt_gesprek_en_weert_medicatie(vraag):
    i = index_van(aanbieder('gesprek', expertise=['Angst', 'Trauma']),
                  aanbieder('medicatie', expertise=['Angst', 'Trauma', 'Medicamenteuze behandeling']),
                  aanbieder('irrelevant', expertise=['Autisme']))
    assert [t.id for t in i.zoek(vraag)] == ['gesprek']


@pytest.mark.parametrize('vraag,leeftijden', [
    ('een kind van 6 en een kind van 14 met angst', [6, 14]),
    ('twee kinderen, 6 en 14 jaar, angst', [6, 14]),
    ('kinderen 6 en 14 met angst', [6, 14]),
    ('dochter van 17,5 en zoon van 14 met angst', [17.5, 14]),
    ('6-jarige en 14-jarige met angst', [6, 14]),
    ('14jr angst', [14]),
])
def test_alle_persoonsleeftijden_en_harde_uitsluiting(vraag, leeftijden):
    a = analyseer_vraag(vraag, {}, set())
    assert a.leeftijden == leeftijden
    i = index_van(aanbieder('breed', leeftijd='Kinderen 0-18 jaar'),
                  aanbieder('ouder', leeftijd='Jongeren vanaf 16 jaar'))
    assert [t.id for t in i.zoek(vraag)] == ['breed']


def test_leeftijdsbereik_is_geen_twee_kinderen():
    a = analyseer_vraag('kinderen 6 tot 14 jaar met angst', {}, set())
    assert a.leeftijdsband == (6, 14)
    assert a.leeftijden == []


def test_fragmenten_zijn_letterlijk_en_vermoeden_blijft_vermoeden():
    q = 'Jongere met ASS en vermoedelijke ADHD'
    a = analyseer_vraag(q, {}, set())
    assert a.concepten == ['ass', 'adhd']
    assert all(q[f['begin']:f['einde']] == f['tekst'] for f in a.interpretatiefragmenten)
    assert next(f for f in a.interpretatiefragmenten if f['begrip'] == 'adhd')['zekerheid'] == 'mogelijk'
