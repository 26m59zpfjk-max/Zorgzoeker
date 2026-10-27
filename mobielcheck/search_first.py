"""Fictieve POST-klikstroom: zoeken, detail, terug en vergelijken."""
from playwright.sync_api import sync_playwright,expect
from pathlib import Path
import sys,os
B=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8792';n=0
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.getenv('CHROME','/usr/bin/chromium'),headless=True)
 for width in (320,390,1440):
  page=b.new_page(viewport={'width':width,'height':1000});page.goto(B+'/werkplek')
  page.get_by_role('textbox',name='Zorgvraag',exact=True).fill('14 jaar angst');page.get_by_label('Verantwoordelijke gemeente',exact=True).fill('Nijmegen');page.get_by_role('button',name='Zoek en controleer',exact=True).click();expect(page.locator('.z-card').first).to_be_visible()
  assert page.evaluate('document.documentElement.scrollWidth')<=width
  boxes=page.locator('input[form="pilot-vergelijk"][name="ids"]');boxes.nth(0).check();boxes.nth(1).check()
  page.get_by_role('button',name='Bekijk aanbieder →').first.click();expect(page.locator('h1')).to_contain_text('Aanbieder')
  page.get_by_role('button',name='Terug naar zoeken met selectie').click();expect(page.locator('input[form="pilot-vergelijk"][name="ids"]:checked')).to_have_count(2)
  page.locator('#pilot-knop').click();expect(page.locator('h1')).to_contain_text('Vergelijken');assert page.evaluate('document.documentElement.scrollWidth')<=width
  assert 'q=' not in page.url
  n+=7;page.close()
 b.close()
print(n,'browsercontroles geslaagd')
