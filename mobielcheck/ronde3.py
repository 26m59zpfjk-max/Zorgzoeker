"""Ronde-3 UI-regressies. Alleen een lokale testserver, geen externe navigatie.

CHROME=/pad/naar/chromium python mobielcheck/ronde3.py http://127.0.0.1:8753
Vereist Playwright en een lokale Chromium-installatie; geen downloads.
"""
import os
import sys
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright

BASIS = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8753'
controles = 0


def check(goed, omschrijving):
    global controles
    controles += 1
    assert goed, omschrijving
    print('OK', omschrijving, flush=True)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHROME','/usr/bin/chromium'),headless=True)
    for breedte in (320,390,768,1280):
        page = browser.new_page(viewport={'width':breedte,'height':844})
        # Browser mag geen aanbiedersites bezoeken, ook niet onbedoeld.
        page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(BASIS+'/') else route.abort())
        page.goto(BASIS+'/?q=Sentio')
        kaart = page.locator('.kaart').first
        check(kaart.count()==1, f'{breedte}: Sentio vindbaar')
        check(kaart.locator('.kaart-waarschuwing').first.is_visible() and 'STOP' in kaart.inner_text(),f'{breedte}: stop direct zichtbaar')
        check('Nee — relevante stop' in kaart.inner_text(),f'{breedte}: geen instroom gesuggereerd')
        check(not kaart.locator('details').evaluate('e=>e.open'),f'{breedte}: details standaard dicht')
        check(not kaart.locator('a.bron').first.is_visible(),f'{breedte}: geen herhaalde bronlabels in kern')
        check(kaart.locator('.kaart-kern dt').all_text_contents()==[
            'Contract · geen gemeente geselecteerd','Toewijzingsroute','Bevestigde producten',
            'Leeftijd / toelating','Wachttijd','Nieuwe aanmeldingen'], f'{breedte}: alle essentiële velden')
        check(page.evaluate('document.documentElement.scrollWidth')<=breedte,f'{breedte}: geen horizontale scroll')
        kaart.locator('summary').click()
        check(kaart.locator('a.bron').first.is_visible(),f'{breedte}: bron na uitklappen zichtbaar')
        check('productcodes' in kaart.inner_text().lower() and 'vestigingen' in kaart.inner_text().lower(),f'{breedte}: administratieve details bewaard')
        check('STOP' in kaart.inner_text(),f'{breedte}: waarschuwing blijft na uitklappen')
        check(page.evaluate('document.documentElement.scrollWidth')<=breedte,f'{breedte}: details passen op scherm')
        page.goto(BASIS+'/?'+urlencode({'q':'Apollis Zorg','gemeente':'Nijmegen','productcode':'JW 45A04'}))
        kaart=page.locator('.kaart').first
        check('Via hoofdaannemer (onderaannemer)' in kaart.inner_text(),f'{breedte}: onderaannemer duidelijk')
        check('STOP' in kaart.inner_text(),f'{breedte}: product-/gemeentestop duidelijk')
        check('JW 45A04' in kaart.locator('.kaart-kern').inner_text(),f'{breedte}: alleen bevestigde productcode')
        check('JW 45A55' not in kaart.locator('.kaart-kern').inner_text(),f'{breedte}: aanvullende codes buiten kern')
        kaart.locator('summary').click()
        check('Hoofdaannemer:' in kaart.inner_text(),f'{breedte}: hoofdaannemer in details')
        page.goto(BASIS+'/?alles=1')
        check(page.locator('.kaart').count()==189,f'{breedte}: Toon alle bewaart 189 aanbieders')
        check(page.locator('details[open]').count()==0,f'{breedte}: ook bij Toon alle details dicht')
        check(page.evaluate('document.documentElement.scrollWidth')<=breedte,f'{breedte}: alle kaarten passen')
        page.close()
    # Werkt ook zonder JS: naam, waarschuwing en native details.
    context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
    page=context.new_page()
    page.goto(BASIS+'/?q=Sentio')
    check('STOP' in page.locator('.kaart').inner_text(),'zonder JS: waarschuwing zichtbaar')
    page.locator('.kaart summary').click()
    check(page.locator('.kaart a.bron').first.is_visible(),'zonder JS: details bruikbaar')
    browser.close()
print(f'{controles} browsercontroles geslaagd')
