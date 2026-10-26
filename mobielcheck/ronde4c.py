"""Fictieve leeswerkplek-tests; geen model, downloads of externe bronnen."""
import os,sys
from playwright.sync_api import sync_playwright
B=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8757';n=0

def check(ok,s):
 global n
 n+=1;assert ok,s;print('OK',s,flush=True)

with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.getenv('CHROME','/usr/bin/chromium'),headless=True)
 for width in (320,390,1280):
  page=b.new_page(viewport={'width':width,'height':844});page.set_default_timeout(60000)
  urls=[];page.on('request',lambda r:urls.append(r.url))
  page.goto(B+'/werkplek');page.get_by_label('Zorgvraag',exact=True).fill('14-jarige met angst')
  page.get_by_label('Verantwoordelijke gemeente',exact=True).fill('Nijmegen')
  page.get_by_role('button',name='Zoek en controleer',exact=True).click();page.wait_for_load_state('networkidle')
  check(page.locator('#pilot-resultaten .kaart').count()>=3,f'{width} resultaten')
  check(page.locator('#pilot-knop').is_disabled(),f'{width} geen vergelijking met nul')
  page.locator('input[form="pilot-vergelijk"][name="ids"]').nth(0).check()
  check(page.locator('#pilot-knop').is_disabled(),f'{width} geen vergelijking met één')
  page.locator('input[form="pilot-vergelijk"][name="ids"]').nth(1).check()
  page.locator('input[form="pilot-vergelijk"][name="ids"]').nth(2).check()
  ids=page.locator('input[form="pilot-vergelijk"][name="ids"]:checked').evaluate_all('xs=>xs.map(x=>x.value)')
  page.locator('#pilot-knop').click();page.wait_for_load_state('networkidle')
  check(page.locator('#pilot-resultaten .kaart').count()==3,f'{width} drie vergelijken')
  check('bronpeildatum' in page.locator('main').inner_text(),f'{width} peildatum zichtbaar')
  check(page.evaluate('document.documentElement.scrollWidth')<=width,f'{width} vergelijking past')
  page.get_by_role('button',name='Terug naar zoeken met selectie').click();page.wait_for_load_state('networkidle')
  check(page.locator('input[form="pilot-vergelijk"][name="ids"]:checked').evaluate_all('xs=>xs.map(x=>x.value)')==ids,f'{width} selectie behouden')
  check(page.get_by_label('Zorgvraag',exact=True).input_value()=='14-jarige met angst',f'{width} vraag behouden')
  check(page.get_by_label('Verantwoordelijke gemeente',exact=True).input_value()=='Nijmegen',f'{width} gemeente behouden')
  check(page.evaluate('document.documentElement.scrollWidth')<=width,f'{width} zoeken past')
  check(not any('q=' in u or 'jarige' in u for u in urls),f'{width} geen vraag in URL')
  page.goto(B+'/kwaliteit');page.wait_for_load_state('networkidle')
  check(page.evaluate('document.documentElement.scrollWidth')<=width,f'{width} kwaliteit past')
  check('alleen lezen' in page.locator('h1').inner_text(),f'{width} geen beheerwrites')
  page.close()
 page=b.new_page(viewport={'width':1280,'height':900})
 page.goto(B+'/werkplek');page.get_by_label('Zorgvraag',exact=True).focus();page.keyboard.type('14 jaar angst');page.keyboard.press('Tab')
 check(page.get_by_label('Verantwoordelijke gemeente',exact=True).evaluate('e=>e===document.activeElement'),'toetsenbord tabvolgorde')
 page.keyboard.type('Nijmegen');page.keyboard.press('Enter');page.wait_for_load_state('networkidle')
 boxes=page.locator('input[form="pilot-vergelijk"][name="ids"]')
 boxes.nth(0).focus();page.keyboard.press('Space');boxes.nth(1).focus();page.keyboard.press('Space')
 check(page.locator('#pilot-knop').is_enabled(),'toetsenbord twee selecties')
 page.locator('#pilot-knop').focus();page.keyboard.press('Enter');page.wait_for_load_state('networkidle')
 check(page.locator('h1').inner_text()=='Vergelijken','toetsenbord vergelijken')
 page.get_by_role('button',name='Terug naar zoeken met selectie').focus();page.keyboard.press('Enter');page.wait_for_load_state('networkidle')
 check(page.locator('input[form="pilot-vergelijk"][name="ids"]:checked').count()==2,'toetsenbord terug behoudt selectie')
 page.evaluate("document.body.style.zoom='2'")
 check(page.evaluate('document.documentElement.scrollWidth')<=1280,'200 procent CSS-zoom reflow')
 page.close();b.close()
print(n,'controles geslaagd')
