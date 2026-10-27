"""Fictieve 5G scenario's; toestandgebaseerd, geen sleeps of clientdata."""
from playwright.sync_api import sync_playwright,expect
from pathlib import Path
import sys,json,os
B=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8795'
OUT=Path(os.getenv('ZORGZOEKER_SCREENSHOTS','/tmp/zorgzoeker-5g-browser'));OUT.mkdir(parents=True,exist_ok=True)
metrics={};checks=0
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=os.getenv('CHROME','/usr/bin/chromium'),headless=True)
 for w in (320,390,768,1440):
  page=browser.new_page(viewport={'width':w,'height':900})
  def zoek(q,g='Berg en Dal'):
   page.goto(B+'/werkplek');page.get_by_role('textbox',name='Zorgvraag',exact=True).fill(q);page.get_by_label('Verantwoordelijke gemeente',exact=True).fill(g)
   with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/zoeken')) as response:page.get_by_role('button',name='Zoek en controleer',exact=True).click()
   assert response.value.status==200
  zoek('14 jaar angst');expect(page.locator('.z-card').first).to_be_visible()
  rect=page.locator('.z-card').first.bounding_box();metrics[w]={'eerste_kaart_y':round(rect['y']),'kaartrhoogte':round(rect['height'])}
  assert rect['y']<=650,(w,rect)
  assert page.evaluate('document.documentElement.scrollWidth')<=w
  page.screenshot(path=str(OUT/f'zoeken-{w}.png'))
  boxes=page.locator('input[form="pilot-vergelijk"][name="ids"]');boxes.nth(0).check();boxes.nth(1).check()
  page.get_by_role('button',name='Bekijk aanbieder →').first.click();expect(page.locator('h1')).to_contain_text('Aanbieder')
  page.get_by_role('button',name='Terug naar zoeken met selectie').click();expect(page.locator('input[form="pilot-vergelijk"][name="ids"]:checked')).to_have_count(2)
  page.locator('#pilot-knop').click();expect(page.locator('h1')).to_contain_text('Vergelijk');assert page.evaluate('document.documentElement.scrollWidth')<=w
  page.screenshot(path=str(OUT/f'vergelijken-{w}.png'))
  zoek('angst maximaal 20 weken');expect(page.locator('.z-card').first).to_be_visible();txt=page.locator('main').inner_text();assert 'Geen resultaten' not in txt and 'Geen kandidaten' not in txt
  zoek('autisme 8 jaar Arnhem','');expect(page.locator('.gemeente-context')).to_contain_text('nog kiezen');assert page.get_by_label('Verantwoordelijke gemeente',exact=True).input_value()==''
  zoek('kinderen van 6 en 14 met angst');page.get_by_role('button',name='Eén gezamenlijke aanbieder',exact=True).click();expect(page.locator('.z-chips')).to_contain_text('6 en 14 jaar');assert '6.0 en 14.0' not in page.locator('main').inner_text()
  assert 'q=' not in page.url;checks+=10;page.close()
 browser.close()
print(json.dumps({'checks':checks,'metrics':metrics},indent=2));(OUT/'metingen.json').write_text(json.dumps(metrics,indent=2))
