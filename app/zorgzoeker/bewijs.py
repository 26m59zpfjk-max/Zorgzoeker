"""Waardegebonden, uitsluitend lezende kwaliteitsprojectie."""
from copy import deepcopy
from datetime import date
import hashlib,json


def hashwaarde(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


class Kwaliteitslezing:
    def __init__(self,document):
        from zorgzoeker.kwaliteit import valideer_beoordeling
        self.regels={}
        for b in document.get('kwaliteitsbeoordelingen',[]):
            if valideer_beoordeling(b):raise ValueError('Ongeldige vrijgegeven kwaliteitsbeoordeling')
            self.regels.setdefault((b['aanbieder_id'],b['veld']),[]).append(b)
    def veld(self,a,k):
        v=a.get(k) or {};waarde=v.get('waarde')
        status='ontbrekend' if waarde in (None,'','onbekend',[]) else 'bron_te_controleren'
        rs=self.regels.get((a['id'],k),[])
        passend=[r for r in rs if r['waarde_hash']==hashwaarde(v)]
        b=max(passend,key=lambda r:r['gecontroleerd_op']) if passend else None
        if b:
            status=b['status']
            laatste=[r for r in passend if r['gecontroleerd_op']==b['gecontroleerd_op']]
            if len({r['status'] for r in laatste})>1 or b.get('tegenstrijdigheden'):status='tegenstrijdig_of_verouderd'
            if b['hercontrole_op']<=date.today().isoformat() or (b.get('geldig_tot') and b['geldig_tot']<date.today().isoformat()):status='tegenstrijdig_of_verouderd'
        return {'status':status,'bron_url':v.get('bron_url'),'laatste_controle':b['gecontroleerd_op'] if b else None,
                'hercontrole_op':b['hercontrole_op'] if b else None,'methode':b['methode'] if b else v.get('label','onbekend'),
                'hash_gewijzigd':bool(rs and not passend),'publicatiedatum':b.get('gepubliceerd_op') if b else None}
    def indexdocument(self,document):
        d=deepcopy(document)
        for a in d.get('aanbieders',[]):
            a['_kwaliteit']={k:self.veld(a,k) for k in a if isinstance(a[k],dict) and 'waarde' in a[k]}
            for k in ('expertise','doelgroepen','type_aanbod'):
                if a['_kwaliteit'].get(k,{}).get('status')=='tegenstrijdig_of_verouderd' or a['_kwaliteit'].get(k,{}).get('hash_gewijzigd'):
                    a[k]={**a.get(k,{}),'waarde':[],'label':'onbekend'}
        return d
