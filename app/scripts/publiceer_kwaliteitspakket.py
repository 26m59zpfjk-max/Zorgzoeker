"""Maak expliciet een gebonden leesmanifest; brondata nooit overschrijven."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zorgzoeker.bewijs import hashwaarde,Kwaliteitslezing
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',type=Path);p.add_argument('beoordelingen',type=Path);p.add_argument('--uitvoer',type=Path,required=True);p.add_argument('--expliciet-vrijgegeven',action='store_true');a=p.parse_args()
 if not a.expliciet_vrijgegeven:p.error('Expliciete vrijgave vereist')
 d=json.loads(a.dataset.read_text());b=json.loads(a.beoordelingen.read_text());lezing=Kwaliteitslezing({**d,'kwaliteitsbeoordelingen':b});ids={x['id']:x for x in d['aanbieders']}
 if any(r['aanbieder_id'] not in ids or r['waarde_hash']!=hashwaarde(ids[r['aanbieder_id']].get(r['veld'],{})) for r in b):p.error('Beoordeling hoort niet bij deze veldwaarde')
 with a.uitvoer.open('x') as f:json.dump({'dataset_hash':hashwaarde(d),'beoordelingen':b},f,ensure_ascii=False,indent=2);f.write('\n')
