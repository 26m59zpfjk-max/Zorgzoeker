"""Echte lokale model-/browserproef op de FICTIEVE AI-dataset.

Start de optionele testserver, lokaal model en embeddings handmatig. Geen downloads.
Gebruik: CHROME=/pad/chromium python mobielcheck/ai_pilot.py BASIS_URL UIT_MAP
Dit script is geen mock en vereist een werkend lokaal taalmodel.
"""
import os,sys
from pathlib import Path
from playwright.sync_api import sync_playwright

basis=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8754'
uit=Path(sys.argv[2]) if len(sys.argv)>2 else Path('/tmp/zorgzoeker-ai-browser')
uit.mkdir(parents=True,exist_ok=True);aantal=0


def check(v,tekst):
    global aantal
    aantal+=1;assert v,tekst;print('OK',tekst,flush=True)


with sync_playwright() as p:
    b=p.chromium.launch(executable_path=os.environ.get('CHROME','/usr/bin/chromium'),headless=True)
    for breedte in (390,1280):
        page=b.new_page(viewport={'width':breedte,'height':844});page.set_default_timeout(60000)
        urls=[];page.on('request',lambda r:urls.append(r.url))
        page.goto(basis+'/ai')
        check('alleen fictieve casussen' in page.locator('main').inner_text(),f'{breedte}: privacygrens zichtbaar')
        page.locator('#ai-vraag').fill('Puber van 15 heeft angstklachten.')
        page.locator('input[name="fictief"]').check()
        page.get_by_role('button',name='Toon interpretatie').click()
        page.wait_for_selector('#ai-interpretatie')
        check('lokaal_taalmodel' in page.locator('#ai-interpretatie').inner_text(),f'{breedte}: echt lokaal model gebruikt')
        check(page.locator('#ai-resultaten').count()==0,f'{breedte}: geen resultaten zonder interpretatiecontrole')
        check(page.locator('select[name="uitsluitingen"]').is_visible(),f'{breedte}: uitsluitingen zichtbaar en aanpasbaar')
        page.locator('input[name="leeftijden"]').fill('14')
        page.locator('select[name="concepten"]').select_option(['angst'])
        page.locator('select[name="uitsluitingen"]').select_option(['medicatie'])
        page.locator('input[name="gemeente"]').fill('Nijmegen')
        page.locator('input[name="bevestigd"]').check()
        page.get_by_role('button',name='Zoek met deze interpretatie').click()
        page.wait_for_selector('#ai-resultaten')
        tekst=page.locator('#ai-resultaten').inner_text()
        check('FICTIEF - stop' in tekst and 'STOP' in tekst,f'{breedte}: relevante stop vindbaar en gewaarschuwd')
        check('FICTIEF - volwassen' not in tekst,f'{breedte}: leeftijdsuitsluiting')
        check('FICTIEF - buiten' not in tekst,f'{breedte}: gemeentelijke dekking')
        check(page.locator('#ai-resultaten details').count()==3,f'{breedte}: drie afzonderlijke brongebonden diensten')
        page.locator('#ai-resultaten summary').first.click()
        check(page.locator('#ai-resultaten a.bron').first.is_visible(),f'{breedte}: herleidbare bron na uitklappen')
        check(page.evaluate('document.documentElement.scrollWidth')<=breedte,f'{breedte}: geen horizontale scroll')
        page.screenshot(path=str(uit/f'ai-{breedte}.png'),full_page=True)
        page.locator('input[name="leeftijden"]').fill('18')
        page.locator('input[name="gemeente"]').fill('Nijmegen')
        page.locator('input[name="bevestigd"]').check()
        page.get_by_role('button',name='Zoek met deze interpretatie').click()
        page.wait_for_selector('#ai-resultaten')
        check('FICTIEF - volwassen' in page.locator('#ai-resultaten').inner_text(),f'{breedte}: expliciete leeftijdscorrectie werkt')
        check(page.locator('#ai-resultaten .kaart').count()==1,f'{breedte}: minderjarigenaanbod uitgesloten bij 18')
        check(all('Kind%20van' not in u and 'q=' not in u for u in urls),f'{breedte}: zorgvraag niet in URL')
        page.close()
    b.close()
print(aantal,'AI-browsercontroles geslaagd')
