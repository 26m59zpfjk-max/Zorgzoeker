"""Controleer de opgeslagen routes opnieuw tegen de exacte openbare ROB-werkmap.

Schrijft alleen losse veldbeoordelingen, geen dataset. Bewijst de snapshot,
geen contractperiode, beschikbaarheid of officiële website.
"""
import argparse
from copy import deepcopy
from datetime import date,timedelta
import hashlib,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from importeer_contracten import importeer
from zorgzoeker.kwaliteit import hashwaarde


def controleer(document,pad):
    register=document['contractregister'];bron=Path(pad)
    if hashlib.sha256(bron.read_bytes()).hexdigest()!=register['sha256']:raise ValueError('Werkmap wijkt af; eerst nieuw contractvoorstel beoordelen.')
    nieuw=importeer(bron,deepcopy(document))['contractregister']
    if nieuw['regels']!=register['regels']:raise ValueError('Routevergelijking wijkt af.')
    beoordelingen=[]
    for a in document['aanbieders']:
        regels=[r for r in register['regels'] if r['aanbieder_id']==a['id']]
        if not regels:continue
        citaat='; '.join(f"{r['productcode']} {b['tabblad']} rij {b['rij']}" for r in regels for b in r['bewijs'])
        for k in ('naam','productcodes','gecontracteerd_regio'):
            # Een complete veldbeoordeling alleen als ALLE opgegeven producten teruggevonden zijn.
            if k=='productcodes' and {p['code'] for p in a[k]['waarde']}!={r['productcode'] for r in regels}:continue
            beoordelingen.append({'aanbieder_id':a['id'],'veld':k,'waarde_hash':hashwaarde(a[k]),
                'bron':'ROB Totaaloverzicht; exacte naam/product/hoofdaannemer/bronrij-vergelijking; SHA256 '+register['sha256'],
                'bron_url':register['bron_url'],'gepubliceerd_op':register['peildatum'],'geldig_van':None,'geldig_tot':None,
                'gecontroleerd_op':date.today().isoformat(),'hercontrole_op':(date.today()+timedelta(days=7)).isoformat(),
                'beoordelaar':'deterministische ROB-bronrijcontrole, geen website-identiteitscontrole',
                'methode':'openbare_bron_gecontroleerd','status':'geverifieerd','citaat':citaat,
                'tegenstrijdigheden':[]})
    return beoordelingen


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('werkmap',type=Path);p.add_argument('--uitvoer',type=Path,required=True);a=p.parse_args()
    beoordelingen=controleer(json.loads(a.dataset.read_text()),a.werkmap)
    with a.uitvoer.open('x') as f:json.dump(beoordelingen,f,ensure_ascii=False,indent=2);f.write('\n')
    print(f'{len(beoordelingen)} veldbeoordelingen; alleen bron-snapshot bevestigd.')
