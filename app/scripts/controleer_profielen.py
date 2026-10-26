"""Offline kwaliteitsrapport + CSV. Optionele expliciet gestarte openbare GET-controle.

Geen cron, bronmutatie, bericht of automatische verificatie. Uitvoer in nieuwe map.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zorgzoeker.kwaliteit import analyseer
from zorgzoeker.kwaliteitsbronnen import haal_bron,openbare_url


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset',type=Path)
    parser.add_argument('--uitvoer',type=Path,required=True,help='Nieuwe map, nooit overschrijven')
    parser.add_argument('--beoordelingen',type=Path)
    parser.add_argument('--waarnemingen',type=Path)
    parser.add_argument('--haal-openbare-bronnen-op',action='store_true')
    args=parser.parse_args()
    if args.uitvoer.exists():parser.error('Uitvoermap bestaat al.')
    doc=json.loads(args.dataset.read_text());reviews=json.loads(args.beoordelingen.read_text()) if args.beoordelingen else doc.get('kwaliteitsbeoordelingen',[])
    waarnemingen=json.loads(args.waarnemingen.read_text()) if args.waarnemingen else []
    args.uitvoer.mkdir(parents=True)
    if args.haal_openbare_bronnen_op:
        urls=set()
        for a in doc['aanbieders']:
            for k,v in a.items():
                if isinstance(v,dict):
                    for url in ([v.get('waarde'),v.get('bron_url')] if k=='website' else [v.get('bron_url')]):
                        if openbare_url(url):urls.add(url)
        for k in ('bron_url','gemeenten_bron'):
            if openbare_url((doc.get('contractregister') or {}).get(k)):urls.add(doc['contractregister'][k])
        def fetch(url):return haal_bron(url,cachemap=args.uitvoer/'broncache')
        with ThreadPoolExecutor(max_workers=4) as pool:
            waarnemingen=list(pool.map(fetch,sorted(urls)))
        (args.uitvoer/'waarnemingen.json').write_text(json.dumps(waarnemingen,ensure_ascii=False,indent=2)+'\n')
    rapport=analyseer(doc,beoordelingen=reviews,waarnemingen=waarnemingen)
    (args.uitvoer/'rapport.json').write_text(json.dumps(rapport,ensure_ascii=False,indent=2)+'\n')
    with (args.uitvoer/'problemen.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['aanbieder_id','naam','veld','code','prioriteit','toelichting'],lineterminator='\n');writer.writeheader()
        for p in rapport['problemen']:
            # CSV-formule-injectie bij openen in spreadsheets voorkomen.
            writer.writerow({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in p.items()})
    s=rapport['samenvatting']
    (args.uitvoer/'overzicht.md').write_text(f"# Profielkwaliteit {rapport['gegenereerd_op']}\n\n{s['aanbieders']} profielen; {s['kern_voldoende']} volledig onderbouwde kernprofielen; {s['problemen']} controlepunten.\n\n{s['afgeleide_websites']} afgeleide websitelinks vereisen identiteitscontrole. Bereikbaarheid is geen verificatie.\n\nZie rapport.json voor veldstatussen en problemen.csv voor de werklijst. Brondata zijn niet aangepast.\n")
    print(json.dumps(s,ensure_ascii=False))


if __name__=='__main__':main()
