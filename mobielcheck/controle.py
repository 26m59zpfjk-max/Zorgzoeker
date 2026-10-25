"""Mobiele controle van Zorgzoeker (390x844) plus desktop (1280x800).

Gebruik: app/.venv/bin/python mobielcheck/controle.py [basis-url]
Gebruikt Playwright met de lokaal geïnstalleerde Chrome (geen download).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASIS = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8741"
MAP = Path(__file__).parent / "screenshots"
MAP.mkdir(parents=True, exist_ok=True)
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
fouten: list[str] = []


def check(voorwaarde: bool, tekst: str) -> None:
    print(("OK   " if voorwaarde else "FOUT ") + tekst)
    if not voorwaarde:
        fouten.append(tekst)


def breedte(pagina) -> int:
    return pagina.evaluate("document.documentElement.scrollWidth")


def hoogtes(pagina, selector: str) -> list[tuple[float, float]]:
    return pagina.eval_on_selector_all(
        selector,
        "els => els.filter(e => e.offsetParent !== null).map(e => {const r = e.getBoundingClientRect(); return [Math.round(r.width*10)/10, Math.round(r.height*10)/10];})",
    )


def tikdoel(pagina, selector: str, naam: str) -> None:
    maten = hoogtes(pagina, selector)
    if not maten:
        check(False, f"tikdoel {naam}: geen zichtbare elementen ({selector})")
        return
    min_h = min(h for _, h in maten)
    min_w = min(w for w, _ in maten)
    check(min_h >= 44 and min_w >= 44, f"tikdoel {naam}: {len(maten)} st., min {min_w}x{min_h} px")


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME, headless=True)
    mobiel = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pagina = mobiel.new_page()

    pagina.goto(f"{BASIS}/?q={quote('autisme en angst')}")
    aantal = pagina.locator(".kaarten > li").count()
    check(aantal > 0, f"zoekpagina: {aantal} resultaatkaarten")
    sw = breedte(pagina)
    check(sw <= 390, f"zoekpagina scrollWidth = {sw} (≤ 390)")
    fs = pagina.evaluate("parseFloat(getComputedStyle(document.body).fontSize)")
    fsi = pagina.evaluate("parseFloat(getComputedStyle(document.querySelector('#q')).fontSize)")
    check(fs >= 16 and fsi >= 16, f"basistekst {fs}px, zoekveld {fsi}px (≥ 16)")
    check(pagina.locator(".kaart details.meer").count() == aantal, "elke kaart heeft een uitklapblok")
    check(not pagina.locator(".kaart details.meer").first.evaluate("e => e.open"), "uitklapblok standaard dicht op mobiel")

    balk = pagina.locator("#vergelijk")
    check(not balk.is_visible(), "vergelijkbalk verborgen vóór aanvinken")
    pagina.screenshot(path=str(MAP / "mobiel-zoek-boven.png"))

    tikdoel(pagina, ".kies", "vergelijk-label")
    tikdoel(pagina, ".kaart a.bron", "bron-links (zichtbaar)")
    tikdoel(pagina, ".filters select", "filters")
    tikdoel(pagina, ".wis a", "Wis zoekvraag en filters")
    tikdoel(pagina, ".meer > summary", "uitklap-samenvatting")

    pagina.locator(".kies").nth(0).click()
    check(balk.is_visible(), "vergelijkbalk zichtbaar na 1 vinkje")
    pos = balk.evaluate("e => getComputedStyle(e).position")
    r = balk.bounding_box()
    onder = r["y"] + r["height"]
    check(pos == "fixed" and abs(onder - 844) <= 1, f"vergelijkbalk position={pos}, onderkant op {onder:.0f} px van 844")
    pagina.locator(".kies").nth(1).click()
    pagina.locator(".kies").nth(2).click()
    check("3 geselecteerd" in balk.inner_text(), "teller toont 3 geselecteerd")
    pagina.mouse.wheel(0, 300)
    pagina.wait_for_timeout(300)
    r2 = balk.bounding_box()
    check(abs(r2["y"] - r["y"]) <= 1, "balk blijft vast bij scrollen")
    pagina.screenshot(path=str(MAP / "mobiel-zoek-balk.png"))

    # Uitgeklapte kaart
    pagina.locator(".kaart details.meer > summary").first.click()
    tikdoel(pagina, ".kaart a.bron", "bron-links (na uitklappen)")
    sw = breedte(pagina)
    check(sw <= 390, f"zoekpagina uitgeklapt scrollWidth = {sw}")
    pagina.locator(".kaarten > li").first.screenshot(path=str(MAP / "mobiel-kaart-uitgeklapt.png"))

    # Laatste kaart niet bedekt
    pagina.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    pagina.wait_for_timeout(300)
    laatste = pagina.locator(".kaarten > li").last.bounding_box()
    balk_y = balk.bounding_box()["y"]
    check(laatste["y"] + laatste["height"] <= balk_y, f"laatste kaart eindigt op {laatste['y'] + laatste['height']:.0f} px, balk begint op {balk_y:.0f} px")

    with pagina.expect_navigation():
        balk.locator("button").click()
    check("/vergelijken" in pagina.url, "vergelijkpagina geopend via balk")
    sw = breedte(pagina)
    check(sw <= 390, f"vergelijkpagina (3 aanbieders) scrollWidth = {sw}")
    check(not pagina.locator(".vergelijktabel").is_visible(), "tabel verborgen op mobiel")
    check(pagina.locator(".vm-blok").first.is_visible(), "blokken per kenmerk zichtbaar")
    tikdoel(pagina, ".terug a", "Terug naar zoeken")
    tikdoel(pagina, ".vergelijk-mobiel a.bron", "bron-links vergelijkpagina")
    pagina.screenshot(path=str(MAP / "mobiel-vergelijk.png"))
    pagina.screenshot(path=str(MAP / "mobiel-vergelijk-volledig.png"), full_page=True)

    # Startpagina
    pagina.goto(BASIS + "/")
    sw = breedte(pagina)
    check(sw <= 390, f"startpagina scrollWidth = {sw}")
    pagina.goto(BASIS + "/?alles=1")
    sw = breedte(pagina)
    check(sw <= 390, f"alle aanbieders scrollWidth = {sw}")

    # Desktop
    desk = browser.new_context(viewport={"width": 1280, "height": 800})
    d = desk.new_page()
    d.goto(f"{BASIS}/?q={quote('autisme en angst')}")
    sw = breedte(d)
    check(sw <= 1280, f"desktop zoekpagina scrollWidth = {sw}")
    check(d.locator(".kaart details.meer").first.evaluate("e => e.open"), "desktop: details standaard open")
    d.screenshot(path=str(MAP / "desktop-zoek.png"))
    ids = d.eval_on_selector_all('input[name="ids"]', "els => els.slice(0,2).map(e => e.value)")
    d.goto(f"{BASIS}/vergelijken?ids={quote(ids[0])}&ids={quote(ids[1])}")
    check(d.locator(".vergelijktabel").is_visible(), "desktop: vergelijktabel zichtbaar")
    check(not d.locator(".vergelijk-mobiel").is_visible(), "desktop: mobiele variant verborgen")
    sw = breedte(d)
    check(sw <= 1280, f"desktop vergelijkpagina (2) scrollWidth = {sw}")
    d.screenshot(path=str(MAP / "desktop-vergelijk.png"))

    # Mobiel met 2 aanbieders
    pagina.goto(f"{BASIS}/vergelijken?ids={quote(ids[0])}&ids={quote(ids[1])}")
    sw = breedte(pagina)
    check(sw <= 390, f"vergelijkpagina (2 aanbieders) scrollWidth = {sw}")
    browser.close()

print()
print("RESULTAAT:", "alles in orde" if not fouten else f"{len(fouten)} fout(en)")
sys.exit(1 if fouten else 0)
