"""Waardegebonden, uitsluitend lezende kwaliteitsprojectie."""
from copy import deepcopy
from datetime import date
import hashlib,json


def hashwaarde(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def beoordeel_veld(a, k, regels=(), vandaag=None):
    """Eén conservatief oordeel per bronveld, zonder brondata te veranderen.

    Herkomst, inhoudelijke controle en actualiteit zijn afzonderlijke dimensies.
    Een legacy-label of bereikbare website geldt niet als inhoudelijke review.
    """
    from zorgzoeker.kwaliteitsbronnen import openbare_url
    from zorgzoeker.valideer import peildatum_veld, wachttijd_ouderdom
    from zorgzoeker.config import max_wachttijd_dagen
    import re

    vandaag = vandaag or date.today()
    nu = vandaag.isoformat()
    v = a.get(k) or {}
    waarde = v.get('waarde')
    ontbreekt = waarde in (None, '', 'onbekend', [])
    rs = [r for r in regels if r['aanbieder_id'] == a['id'] and r['veld'] == k]
    passend = [r for r in rs if r['waarde_hash'] == hashwaarde(v)]
    laatste_datum = max((r['gecontroleerd_op'] for r in passend), default=None)
    laatste = [r for r in passend if r['gecontroleerd_op'] == laatste_datum]
    # Stabiele keuze voor metadata; geen invoervolgorde-afhankelijk positief oordeel.
    b = min(laatste, key=lambda r: json.dumps(r, sort_keys=True)) if laatste else None
    status = 'ontbrekend' if ontbreekt else 'bron_te_controleren'
    redenen = []
    actualiteit = 'Geldigheid onbekend'
    if b and not ontbreekt:
        status = b['status']
        if len({r['status'] for r in laatste}) > 1 or any(r.get('tegenstrijdigheden') for r in laatste):
            status = 'tegenstrijdig_of_verouderd'
            redenen.append('Tegenstrijdige inhoudelijke beoordelingen.')
        if any(r['hercontrole_op'] <= nu or (r.get('geldig_tot') and r['geldig_tot'] < nu) for r in laatste):
            status = 'tegenstrijdig_of_verouderd'
            actualiteit = 'Hercontrole nodig'
            redenen.append('Hercontrole/geldigheid verstreken.')
        elif any(r['gecontroleerd_op'] > nu for r in laatste):
            if status == 'geverifieerd':
                status = 'bron_te_controleren'
            actualiteit = 'Nog niet gecontroleerd op beoordelingsdatum'
            redenen.append('Controle vond na de beoordelingsdatum plaats.')
        elif any(r.get('geldig_van') and r['geldig_van'] > nu for r in laatste):
            if status == 'geverifieerd':
                status = 'bron_te_controleren'
            actualiteit = 'Nog niet geldig'
            redenen.append('Beoordeling geldt pas vanaf een toekomstige datum.')
        elif b.get('geldig_van') and b.get('geldig_tot'):
            actualiteit = 'Binnen vastgelegde periode'
    if rs and not passend:
        redenen.append('Veldwaarde gewijzigd sinds de beoordeling; opnieuw controleren.')
    if not ontbreekt and not openbare_url(v.get('bron_url')):
        status = 'tegenstrijdig_of_verouderd'
        redenen.append('Geen bruikbare bron.')
    if k == 'website' and not ontbreekt and not openbare_url(waarde):
        status = 'tegenstrijdig_of_verouderd'
        redenen.append('Website is geen veilige openbare http(s)-URL.')
    peil = peildatum_veld(v)
    oud = wachttijd_ouderdom(v, vandaag) if k == 'wachttijd' else None
    if k == 'wachttijd' and not ontbreekt:
        if oud is not None and (oud > max_wachttijd_dagen() or oud < 0):
            status = 'tegenstrijdig_of_verouderd'
            actualiteit = 'Hercontrole nodig'
            redenen.append('Wachttijdpublicatie verouderd of peildatum ligt in de toekomst.')
        elif oud is None:
            actualiteit = 'Geldigheid onbekend'
        elif actualiteit == 'Geldigheid onbekend':
            actualiteit = 'Binnen publicatiebeleid; niet actueel bevestigd'
    if k == 'doelgroepen' and isinstance(waarde, list):
        for t in waarde:
            m = re.search(r'\b(\d+)\s*(?:-|tot|t/m)\s*(\d+)', str(t))
            if m and int(m[1]) > int(m[2]):
                status = 'tegenstrijdig_of_verouderd'
                redenen.append('Leeftijdsgrenzen staan omgekeerd.')
    methode = b['methode'] if b else ('afgeleid' if v.get('label') == 'afgeleid' else 'onbekend')
    herkomst = ('Rechtstreeks bevestigd' if methode == 'rechtstreeks_bevestigd' else
                'Afgeleid' if methode == 'afgeleid' else
                'Openbare bron' if openbare_url(v.get('bron_url')) else 'Onbekend')
    controle = {'geverifieerd': 'Inhoud gecontroleerd', 'bron_te_controleren': 'Nog controleren',
                'tegenstrijdig_of_verouderd': 'Tegenstrijdig of hercontrole nodig', 'ontbrekend': 'Ontbreekt'}[status]
    return {'status': status, 'herkomst': herkomst, 'controle': controle, 'actualiteit': actualiteit,
            'bron_url': v.get('bron_url'), 'bron': b.get('bron') if b else None,
            'laatste_controle': b['gecontroleerd_op'] if b else None,
            'hercontrole_op': b['hercontrole_op'] if b else None,
            'methode': methode, 'hash_gewijzigd': bool(rs and not passend),
            'publicatiedatum': b.get('gepubliceerd_op') if b else peil,
            'gepubliceerd_op': b.get('gepubliceerd_op') if b else peil,
            'geldig_van': b.get('geldig_van') if b else None, 'geldig_tot': b.get('geldig_tot') if b else None,
            'beoordelaar': b.get('beoordelaar') if b else None,
            'tegenstrijdigheden': list(dict.fromkeys(t for r in laatste for t in r.get('tegenstrijdigheden', []))),
            'waarde_hash': hashwaarde(v), 'legacy_label': v.get('label', 'onbekend'),
            'laatste_ophaal': v.get('opgehaald_op'), 'hercontrole_nodig': status != 'geverifieerd',
            'redenen': redenen}


class Kwaliteitslezing:
    def __init__(self, document, vandaag=None):
        from zorgzoeker.kwaliteit import valideer_beoordeling
        self.vandaag = vandaag
        self.regels = {}
        for b in document.get('kwaliteitsbeoordelingen', []):
            if valideer_beoordeling(b, vandaag):
                raise ValueError('Ongeldige vrijgegeven kwaliteitsbeoordeling')
            self.regels.setdefault((b['aanbieder_id'], b['veld']), []).append(b)

    def veld(self, a, k, vandaag=None):
        return beoordeel_veld(a, k, self.regels.get((a['id'], k), []), vandaag or self.vandaag)

    def indexdocument(self,document):
        d=deepcopy(document)
        for a in d.get('aanbieders',[]):
            a['_kwaliteit']={k:self.veld(a,k) for k in a if isinstance(a[k],dict) and 'waarde' in a[k]}
            for k in ('expertise','doelgroepen','type_aanbod'):
                if a['_kwaliteit'].get(k,{}).get('status')=='tegenstrijdig_of_verouderd' or a['_kwaliteit'].get(k,{}).get('hash_gewijzigd'):
                    a[k]={**a.get(k,{}),'waarde':[],'label':'onbekend'}
        return d
