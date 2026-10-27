"""Alleen lezen: expliciet geselecteerd lokaal runbestand; geen browservrijgave."""
import json,os
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse
from zorgzoeker.bewijs import hashwaarde

def registreer(app,templates,basis):
    @app.get('/beheer/verrijking')
    def review(request:Request):
        path=os.getenv('ZORGZOEKER_VERRIJKING_REVIEW','')
        if not path:return JSONResponse({'fout':'Geen reviewpakket geselecteerd'},status_code=503)
        try:
            p=Path(path)
            if p.stat().st_size>8_000_000:raise ValueError('Te groot')
            pakket=json.loads(p.read_text())
            if pakket['dataset_hash']!=hashwaarde(app.state.document):raise ValueError('Andere bronversie')
            runs=pakket['runs']
            if not isinstance(runs,list):raise ValueError('Ongeldige runs')
            ids={a['id']:a for a in app.state.document['aanbieders']}
            for r in runs:
                if r['aanbieder_id'] not in ids or not isinstance(r.get('bevindingen',[]),list):raise ValueError('Ongeldige bevindingen')
            return templates.TemplateResponse(request,'review_verrijking.html',{**basis(),'runs':runs,'profielen':ids})
        except (OSError,ValueError,KeyError,TypeError):return JSONResponse({'fout':'Reviewpakket ongeldig of hoort bij andere dataset'},status_code=400)
